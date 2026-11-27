"""Run untrusted code in a Microsandbox microVM.

Containment properties this module enforces (see README "Containment model"):
- Process isolation: code runs in its own microVM, never in this process.
- Secret hygiene: the sandbox is created with no `env`, so host secrets are not injected.
- Resource limits: CPU, memory, a hard lifetime cap, and a per-exec timeout.
- Lifecycle: every sandbox is destroyed in `finally`, and created as `ephemeral`.
"""

from dataclasses import dataclass
from uuid import uuid4

from microsandbox import (
    Action,
    Destination,
    ExecTimeoutError,
    Network,
    NetworkPolicy,
    Protocol,
    Rule,
    Sandbox,
)


@dataclass(frozen=True)
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SandboxRunner:
    def __init__(
        self,
        *,
        image: str = "python",
        cpus: int = 1,
        memory_mib: int = 512,
        max_duration_s: int = 60,
        exec_timeout_s: float = 30.0,
        egress_allow: tuple[str, int] | None = None,
    ) -> None:
        """egress_allow=(ip, tcp_port) switches the sandbox to deny-all egress except that one endpoint.

        Used by the memory demo so the worker can reach only the proxy. None keeps the default network.
        """
        self.image = image
        self.cpus = cpus
        self.memory_mib = memory_mib
        self.max_duration_s = max_duration_s
        self.exec_timeout_s = exec_timeout_s
        self.egress_allow = egress_allow

    def _network(self) -> Network | None:
        if self.egress_allow is None:
            return None
        ip, port = self.egress_allow
        policy = NetworkPolicy(
            default_egress=Action.DENY,
            rules=(Rule.allow(destination=Destination.ip(ip), protocol=Protocol.TCP, port=port),),
        )
        return Network(policy=policy)

    async def run_python(self, code: str) -> ExecResult:
        name = f"run-{uuid4().hex[:12]}"
        options = {"network": self._network()} if self.egress_allow else {}
        sandbox = await Sandbox.create(
            name,
            image=self.image,
            cpus=self.cpus,
            memory=self.memory_mib,
            max_duration=self.max_duration_s,
            ephemeral=True,
            replace=True,
            **options,
        )
        try:
            output = await sandbox.exec(
                "python", ["-c", code], timeout=self.exec_timeout_s
            )
            return ExecResult(
                stdout=output.stdout_text,
                stderr=output.stderr_text,
                exit_code=output.exit_code,
            )
        except ExecTimeoutError:
            return ExecResult(
                stdout="",
                stderr=f"execution exceeded {self.exec_timeout_s}s and was killed",
                exit_code=-1,
                timed_out=True,
            )
        finally:
            await sandbox.destroy()

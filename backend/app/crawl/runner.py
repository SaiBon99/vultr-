"""Sandbox runners. The real one starts one Docker container per run; tests use a local subprocess.

Both speak the same framing: one JSON object per line on the agent's stdin and stdout.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.crawl.errors import CrawlError

CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
SANDBOX_USER = "65534:65534"  # nobody:nogroup, regardless of the image's USER
PIDS_LIMIT = 64
TMPFS = "/tmp:rw,noexec,nosuid,nodev,size=16m"
LABEL = "memory-quarantine.crawl=1"
STDERR_LIMIT = 64 * 1024  # bytes of sandbox stderr kept in the run log (cut after redaction)
STDERR_SLACK = 1024  # extra bytes read so a secret across the 64 KB mark is still redacted whole
STDERR_GRACE_S = 1.0  # how long to wait for stderr EOF after the process exits


@dataclass(frozen=True)
class Limits:
    memory_mb: int
    cpus: int
    timeout_s: int

    @classmethod
    def from_settings(cls, settings: Settings) -> Limits:
        return cls(
            memory_mb=settings.SANDBOX_MAX_MEMORY_MB,
            cpus=settings.SANDBOX_MAX_CPUS,
            timeout_s=settings.SANDBOX_TIMEOUT_S,
        )


class ProcessRun:
    """One running agent process. send/receive are line-framed JSON; cleanup is idempotent."""

    LINE_LIMIT = 1_000_000  # bytes per message line
    image_id: str | None = None

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self.proc = proc
        self.spoke = False  # the agent wrote at least one line
        self._stderr = bytearray()
        self.stderr_truncated = False
        # Drained for the whole run so a noisy sandbox can never block on a full pipe.
        self._stderr_task = (
            asyncio.create_task(self._drain_stderr()) if proc.stderr is not None else None
        )

    async def _drain_stderr(self) -> None:
        assert self.proc.stderr is not None
        while chunk := await self.proc.stderr.read(65536):
            room = STDERR_LIMIT + STDERR_SLACK - len(self._stderr)
            if len(chunk) > room:
                self.stderr_truncated = True
            self._stderr += chunk[: max(room, 0)]

    async def send(self, message: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message, ensure_ascii=False).encode() + b"\n")
        await self.proc.stdin.drain()

    async def receive(self) -> bytes:
        """Next line, or b"" at end of stream. Over-long lines raise ValueError."""
        assert self.proc.stdout is not None
        line = await self.proc.stdout.readline()
        if line:
            self.spoke = True
        return line

    async def wait(self) -> int:
        return await self.proc.wait()

    async def sandbox_ids(self) -> tuple[str, str]:
        raise NotImplementedError

    async def stderr_text(self) -> tuple[str, bool]:
        """Captured stderr (at most STDERR_LIMIT + STDERR_SLACK bytes), and whether more was cut."""
        await self._stop_stderr()
        return self._stderr.decode("utf-8", errors="replace"), self.stderr_truncated

    async def _stop_stderr(self) -> None:
        """Let the drain reach EOF (bounded by STDERR_GRACE_S), then cancel it. Idempotent."""
        task = self._stderr_task
        if task is None or task.done():
            return
        if self.proc.returncode is not None:
            with contextlib.suppress(TimeoutError, Exception):
                await asyncio.wait_for(asyncio.shield(task), STDERR_GRACE_S)
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def cleanup(self) -> None:
        if self.proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.proc.kill()
            await self.proc.wait()
        await self._stop_stderr()


class Runner(Protocol):
    limits: Limits

    async def start(self) -> ProcessRun: ...


class DockerRun(ProcessRun):
    def __init__(self, proc, *, name: str, cidfile: Path, image_id: str, workdir: Path) -> None:
        super().__init__(proc)
        self.name = name
        self.cidfile = cidfile
        self.image_id = image_id
        self.workdir = workdir

    async def sandbox_ids(self) -> tuple[str, str]:
        try:
            container_id = self.cidfile.read_text().strip()
        except OSError:
            container_id = ""
        if not CONTAINER_ID.match(container_id):
            raise CrawlError(502, "sandbox_failed", "sandbox container id is unavailable")
        return container_id, self.image_id

    async def cleanup(self) -> None:
        """Kill and force-remove the container (by name, so it works before the cidfile exists)."""
        await _docker("rm", "-f", self.name)
        await super().cleanup()
        shutil.rmtree(self.workdir, ignore_errors=True)


class DockerRunner:
    def __init__(self, settings: Settings, command: tuple[str, ...] = ()) -> None:
        self.limits = Limits.from_settings(settings)
        self.image = settings.CRAWL_SANDBOX_IMAGE
        self.command = command  # picks the agent script in the shared image; empty: the default

    def argv(self, *, image_id: str, name: str, cidfile: Path) -> list[str]:
        """The full `docker run` command. No -e, --env-file, -v or --mount: nothing from host."""
        mem = f"{self.limits.memory_mb}m"
        return [
            "docker", "run", "-i", "--rm",
            "--name", name,
            "--cidfile", str(cidfile),
            "--label", LABEL,
            "--network", "none",
            "--read-only",
            "--tmpfs", TMPFS,
            "--user", SANDBOX_USER,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", mem,
            "--memory-swap", mem,
            "--cpus", str(self.limits.cpus),
            "--pids-limit", str(PIDS_LIMIT),
            image_id,
            *self.command,
        ]  # fmt: skip

    async def start(self) -> DockerRun:
        if shutil.which("docker") is None:
            raise CrawlError(502, "sandbox_failed", "Docker is not installed on this host")
        code, out, err = await _docker("image", "inspect", "--format", "{{.Id}}", self.image)
        if code != 0:
            if "no such image" not in err.lower():
                raise CrawlError(
                    502, "sandbox_failed", "Docker daemon is not running or not reachable"
                )
            raise CrawlError(
                502,
                "sandbox_failed",
                f"Docker image {self.image} not found; run infra/scripts/setup_crawl_sandbox.sh",
            )
        image_id = out.strip()
        if not IMAGE_ID.match(image_id):
            raise CrawlError(502, "sandbox_failed", "Docker returned an unexpected image id")
        workdir = Path(tempfile.mkdtemp(prefix="crawl-"))
        name = f"crawl-{uuid.uuid4().hex[:16]}"
        cidfile = workdir / "cid"
        proc = await asyncio.create_subprocess_exec(
            *self.argv(image_id=image_id, name=name, cidfile=cidfile),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=ProcessRun.LINE_LIMIT,
        )
        return DockerRun(proc, name=name, cidfile=cidfile, image_id=image_id, workdir=workdir)


async def _docker(*args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")

"""Containment tests: run real microVM sandboxes. Needs /dev/kvm and the msb CLI.

Run on the VM with:  pytest -m integration
These are skipped automatically when /dev/kvm is missing.
"""

import asyncio
import os
import socket
import time
from pathlib import Path

import pytest

from backend.app.sandbox import SandboxRunner

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.path.exists("/dev/kvm"), reason="requires /dev/kvm"),
]


@pytest.fixture
def runner() -> SandboxRunner:
    return SandboxRunner(cpus=1, memory_mib=512, max_duration_s=60, exec_timeout_s=20.0)


async def test_code_runs_in_a_separate_kernel(runner):
    result = await runner.run_python("import os; print(os.uname().nodename)")

    assert result.ok, result.stderr
    assert result.stdout.strip() != socket.gethostname()


async def test_host_secrets_are_not_visible_inside_sandbox(runner, monkeypatch):
    canary = "canary-secret-7f3a"
    monkeypatch.setenv("VULTR_INFERENCE_API_KEY", canary)

    result = await runner.run_python("import os; print('\\n'.join(sorted(os.environ)))")

    assert result.ok, result.stderr
    assert canary not in result.stdout
    assert "VULTR_INFERENCE_API_KEY" not in result.stdout


async def test_infinite_loop_is_killed_by_timeout():
    runner = SandboxRunner(cpus=1, memory_mib=512, max_duration_s=60, exec_timeout_s=5.0)
    started = time.monotonic()

    result = await runner.run_python("while True:\n    pass\n")

    assert result.timed_out is True
    assert result.ok is False
    assert time.monotonic() - started < 45


async def test_memory_cap_stops_runaway_allocation(runner):
    code = "b = bytearray(b'x') * (1024 ** 3)\nprint(len(b))\n"

    result = await runner.run_python(code)

    assert result.ok is False


async def test_destructive_command_cannot_touch_host(runner, tmp_path: Path):
    host_canary = tmp_path / "host-canary.txt"
    host_canary.write_text("untouched")

    result = await runner.run_python(
        "import os\nos.system('rm -rf / --no-preserve-root')\nprint('ran')\n"
    )

    assert host_canary.read_text() == "untouched"
    assert result is not None


async def test_sibling_sandboxes_cannot_reach_each_other():
    from microsandbox import Sandbox

    server = await Sandbox.create("sib-server", image="python", cpus=1, memory=256,
                                  max_duration=120, ephemeral=True, replace=True)
    client = await Sandbox.create("sib-client", image="python", cpus=1, memory=256,
                                  max_duration=120, ephemeral=True, replace=True)
    try:
        await server.exec(
            "bash",
            ["-c", "(setsid nohup python3 -m http.server 9000 >/tmp/srv.log 2>&1 </dev/null &); sleep 1"],
            timeout=20.0,
        )
        ip = (await server.exec("hostname", ["-I"], timeout=10.0)).stdout_text.split()[0]

        probe = await client.exec(
            "python",
            ["-c", (
                "import socket,sys\n"
                f"s=socket.socket(); s.settimeout(3)\n"
                f"try:\n    s.connect(('{ip}', 9000)); print('REACHED')\n"
                "except OSError as e:\n    print('BLOCKED', e)\n"
            )],
            timeout=20.0,
        )
        assert "BLOCKED" in probe.stdout_text, probe.stdout_text + probe.stderr_text
    finally:
        await asyncio.gather(server.destroy(), client.destroy(), return_exceptions=True)

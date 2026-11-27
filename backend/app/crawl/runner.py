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

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self.proc = proc
        self.spoke = False  # the agent wrote at least one line

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

    async def cleanup(self) -> None:
        if self.proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.proc.kill()
            await self.proc.wait()


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
    def __init__(self, settings: Settings) -> None:
        self.limits = Limits.from_settings(settings)
        self.image = settings.CRAWL_SANDBOX_IMAGE

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
            stderr=asyncio.subprocess.DEVNULL,
            limit=ProcessRun.LINE_LIMIT,
        )
        return DockerRun(proc, name=name, cidfile=cidfile, image_id=image_id, workdir=workdir)


async def _docker(*args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")

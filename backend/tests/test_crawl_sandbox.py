"""Ticket 05: the real Docker runner's containment, the time limit, cleanup and concurrency."""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.crawl.runner import DockerRunner, Limits
from tests.test_crawl import PAGE_URL, REVIEW, schema_errors, stand_in

pytest_plugins = ["tests.test_crawl"]


def flag_values(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag]


def test_docker_run_configuration_is_contained(crawl_settings):
    """Offline containment proof: the exact `docker run` the real runner would execute."""
    runner = DockerRunner(crawl_settings)
    image_id = "sha256:" + "a" * 64
    argv = runner.argv(image_id=image_id, name="crawl-x", cidfile=Path("/tmp/x/cid"))

    assert argv[:3] == ["docker", "run", "-i"] and argv[-1] == image_id
    assert "--rm" in argv
    assert flag_values(argv, "--network") == ["none"]
    assert "--read-only" in argv
    assert flag_values(argv, "--tmpfs") == ["/tmp:rw,noexec,nosuid,nodev,size=16m"]
    assert flag_values(argv, "--user") == ["65534:65534"]
    assert flag_values(argv, "--cap-drop") == ["ALL"]
    assert flag_values(argv, "--security-opt") == ["no-new-privileges"]
    assert flag_values(argv, "--memory") == ["512m"]
    assert flag_values(argv, "--memory-swap") == ["512m"]
    assert flag_values(argv, "--cpus") == ["1"]
    assert flag_values(argv, "--pids-limit") == ["64"]
    for forbidden in (
        "-e",
        "--env",
        "--env-file",
        "-v",
        "--volume",
        "--mount",
        "--privileged",
        "--cap-add",
        "--device",
        "--pid",
        "--ipc",
        "--add-host",
        "-p",
        "--publish",
    ):
        assert forbidden not in argv, forbidden  # fmt: skip
    assert not any(a.startswith(("--env", "--volume", "--mount", "--network=")) for a in argv)
    assert crawl_settings.VULTR_INFERENCE_API_KEY.get_secret_value() not in " ".join(argv)
    assert runner.limits == Limits(memory_mb=512, cpus=1, timeout_s=30)


def test_limits_come_from_sandbox_settings(crawl_settings):
    crawl_settings.SANDBOX_MAX_MEMORY_MB = 256
    crawl_settings.SANDBOX_MAX_CPUS = 2
    crawl_settings.SANDBOX_TIMEOUT_S = 20
    runner = DockerRunner(crawl_settings)
    argv = runner.argv(image_id="sha256:" + "a" * 64, name="n", cidfile=Path("/c"))
    assert flag_values(argv, "--memory") == ["256m"] == flag_values(argv, "--memory-swap")
    assert flag_values(argv, "--cpus") == ["2"]
    assert runner.limits.timeout_s == 20


def test_run_over_time_limit_is_killed_removed_and_504(misbehaving, runner):
    runner.limits = Limits(memory_mb=512, cpus=1, timeout_s=1)
    r = misbehaving(stand_in("time.sleep(60)"))
    assert r.status_code == 504 and r.json()["code"] == "timeout"
    assert runner.cleanups == 1


@pytest.mark.parametrize("script", [None, stand_in("time.sleep(60)"), "import sys; sys.exit(3)"])
def test_sandbox_is_cleaned_up_after_every_run(crawl_app, runner, script):
    runner.limits = Limits(memory_mb=512, cpus=1, timeout_s=1)
    runner.script = script
    TestClient(crawl_app).post("/crawl", json={"url": PAGE_URL}, headers=REVIEW)
    assert runner.starts == runner.cleanups == 1


async def test_third_concurrent_run_is_sandbox_busy(crawl_app, runner):
    runner.limits = Limits(memory_mb=512, cpus=1, timeout_s=1)
    runner.script = stand_in("time.sleep(60)")
    transport = httpx.ASGITransport(app=crawl_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        rs = await asyncio.gather(
            *(client.post("/crawl", json={"url": PAGE_URL}, headers=REVIEW) for _ in range(3))
        )
        assert sorted(r.status_code for r in rs) == [503, 504, 504]
        busy = next(r for r in rs if r.status_code == 503)
        assert busy.json()["code"] == "sandbox_busy"
        assert runner.starts == 2
        runner.script = None  # slots are given back
        assert (
            await client.post("/crawl", json={"url": PAGE_URL}, headers=REVIEW)
        ).status_code == 200


def test_missing_docker_names_docker(crawl_app, crawl_settings, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    crawl_app.state.crawl_runner = DockerRunner(crawl_settings)
    r = TestClient(crawl_app).post("/crawl", json={"url": PAGE_URL}, headers=REVIEW)
    assert r.status_code == 502 and r.json()["code"] == "sandbox_failed"
    assert "Docker" in r.json()["detail"]


@pytest.mark.docker
def test_missing_image_names_the_setup_script(crawl_app, crawl_settings):
    if not _docker_ok():
        pytest.skip("Docker daemon not available")
    crawl_settings.CRAWL_SANDBOX_IMAGE = "memory-quarantine-crawler:does-not-exist"
    crawl_app.state.crawl_runner = DockerRunner(crawl_settings)
    r = TestClient(crawl_app).post("/crawl", json={"url": PAGE_URL}, headers=REVIEW)
    assert r.status_code == 502 and r.json()["code"] == "sandbox_failed"
    assert "setup_crawl_sandbox.sh" in r.json()["detail"]


def _docker_ok(image: str | None = None) -> bool:
    if shutil.which("docker") is None:
        return False
    args = ["docker", "image", "inspect", image] if image else ["docker", "info"]
    return subprocess.run(args, capture_output=True).returncode == 0


@pytest.mark.docker
def test_real_container_run_end_to_end(crawl_app, crawl_settings):
    if not _docker_ok(crawl_settings.CRAWL_SANDBOX_IMAGE):
        pytest.skip("Docker or the sandbox image is not available")
    crawl_app.state.crawl_runner = DockerRunner(crawl_settings)
    r = TestClient(crawl_app).post("/crawl", json={"url": PAGE_URL}, headers=REVIEW)
    assert r.status_code == 200, r.text
    body = r.json()
    assert schema_errors(body, "CrawlResult") == []
    image = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", crawl_settings.CRAWL_SANDBOX_IMAGE],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    assert body["sandbox"]["image_id"] == image
    gone = subprocess.run(
        ["docker", "ps", "-aq", "--no-trunc", "--filter", f"id={body['sandbox']['container_id']}"],
        capture_output=True, text=True,
    )  # fmt: skip
    assert gone.stdout.strip() == ""
    leftovers = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "label=memory-quarantine.crawl=1"],
        capture_output=True, text=True,
    )  # fmt: skip
    assert leftovers.stdout.strip() == ""
    assert json.dumps(body).find(crawl_settings.VULTR_INFERENCE_API_KEY.get_secret_value()) == -1

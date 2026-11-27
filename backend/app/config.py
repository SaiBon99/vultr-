"""Settings loaded from environment variables (and an optional .env file at the repo root)."""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    inference_api_key: str
    inference_base_url: str
    inference_model: str
    sandbox_image: str
    sandbox_cpus: int
    sandbox_memory_mib: int
    sandbox_max_duration_s: int
    sandbox_exec_timeout_s: float
    max_attempts: int
    # Memory quarantine (spec.md). Only the proxy holds database_url; the sandbox never does.
    database_url: str = ""
    judge_model: str = ""
    gate_mode: str = "gated"  # "gated" or "naive" (demo baseline that bypasses the gate)
    proxy_base_url: str = "http://localhost:8000"  # URL the sandbox uses to reach the proxy
    allowed_domains: frozenset[str] = frozenset({"roastery-co.example"})
    review_token: str = ""  # required for reviewer and demo routes (/ui, /audit, /demo/runs)


def load_settings() -> Settings:
    _load_dotenv(REPO_ROOT / ".env")
    return Settings(
        inference_api_key=os.environ.get("VULTR_INFERENCE_API_KEY", ""),
        inference_base_url=os.environ.get(
            "VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1"
        ),
        inference_model=os.environ.get("VULTR_INFERENCE_MODEL", ""),
        sandbox_image=os.environ.get("SANDBOX_IMAGE", "python"),
        sandbox_cpus=int(os.environ.get("SANDBOX_CPUS", "1")),
        sandbox_memory_mib=int(os.environ.get("SANDBOX_MEMORY_MIB", "512")),
        sandbox_max_duration_s=int(os.environ.get("SANDBOX_MAX_DURATION_S", "60")),
        sandbox_exec_timeout_s=float(os.environ.get("SANDBOX_EXEC_TIMEOUT_S", "30")),
        max_attempts=int(os.environ.get("MAX_ATTEMPTS", "3")),
        database_url=os.environ.get("DATABASE_URL", ""),
        judge_model=os.environ.get("VULTR_JUDGE_MODEL", ""),
        gate_mode=os.environ.get("GATE_MODE", "gated"),
        proxy_base_url=os.environ.get("PROXY_BASE_URL", "http://localhost:8000"),
        allowed_domains=frozenset(
            d.strip() for d in os.environ.get("ALLOWED_DOMAINS", "roastery-co.example").split(",") if d.strip()
        ),
        review_token=os.environ.get("REVIEW_TOKEN", ""),
    )

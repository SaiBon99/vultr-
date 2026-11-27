"""Settings from environment. Names follow docs/Execution Plan.md."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Absolute paths so the cwd (backend/, repo root, systemd WorkingDirectory) does not matter.
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / "infra" / ".env", REPO_ROOT / "backend" / ".env"), extra="ignore"
    )

    HOST_SECRET: SecretStr = SecretStr("")
    REVIEWER_TOKEN: SecretStr = SecretStr("")

    DATABASE_URL_PROXY: SecretStr = SecretStr("")
    DATABASE_URL_READER: SecretStr = SecretStr("")

    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY: SecretStr = SecretStr("")
    S3_SECRET_KEY: SecretStr = SecretStr("")
    S3_BUCKET: str = "quarantine-receipts"
    S3_REGION: str = "us-east-1"

    VULTR_INFERENCE_BASE_URL: str = "https://api.vultrinference.com/v1"
    VULTR_INFERENCE_API_KEY: SecretStr = SecretStr("")
    JUDGE_MODEL: str = "qwen3.8-27b"
    EMBED_MODEL: str = "qwen3-embedding-4b"
    EMBED_DIMENSIONS: int = 1024

    CRAWLER_MODEL: str = "qwen3.8-27b"
    CRAWL_MAX_BYTES: int = 2_000_000
    CRAWL_SANDBOX_IMAGE: str = "memory-quarantine-crawler:latest"
    SANDBOX_MAX_MEMORY_MB: int = 512
    SANDBOX_MAX_CPUS: int = 1
    SANDBOX_TIMEOUT_S: int = 30

    CHAT_MODEL: str = ""  # empty: use CRAWLER_MODEL
    CHAT_TIMEOUT_S: int = Field(default=90, ge=1)
    CHAT_MAX_STEPS: int = Field(default=8, ge=1)

    DEMO_ALLOW_NAIVE: bool = False
    EGRESS_ALLOWLIST: str = ""
    RECEIPT_SIGNING_KEY_PATH: str = ""

    @property
    def chat_model(self) -> str:
        return self.CHAT_MODEL.strip() or self.CRAWLER_MODEL

    @property
    def log_secrets(self) -> list[str]:
        """Values redacted from run logs before upload."""
        secrets = (
            self.VULTR_INFERENCE_API_KEY,
            self.HOST_SECRET,
            self.REVIEWER_TOKEN,
            self.S3_ACCESS_KEY,
            self.S3_SECRET_KEY,
        )
        return [v for s in secrets if (v := s.get_secret_value())]

    @property
    def egress_allowlist(self) -> list[str]:
        return [d.strip() for d in self.EGRESS_ALLOWLIST.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

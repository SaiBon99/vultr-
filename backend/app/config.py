"""Settings from environment. Names follow docs/Execution Plan.md."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    DEMO_ALLOW_NAIVE: bool = False
    EGRESS_ALLOWLIST: str = ""
    RECEIPT_SIGNING_KEY_PATH: str = ""

    @property
    def egress_allowlist(self) -> list[str]:
        return [d.strip() for d in self.EGRESS_ALLOWLIST.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

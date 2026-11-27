"""Tiny env loader: infra/.env (if present) fills missing os.environ keys; local defaults match docker-compose."""
import os
from pathlib import Path

INFRA = Path(__file__).resolve().parent.parent


def load_env() -> None:
    f = INFRA / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get(name: str, default: str = "") -> str:
    return os.environ.get(name) or default


def admin_url() -> str:
    if get("DATABASE_URL_ADMIN"):
        return get("DATABASE_URL_ADMIN")
    return "postgresql://{u}:{p}@{h}:{port}/{d}".format(
        u=get("POSTGRES_USER", "postgres"), p=get("POSTGRES_PASSWORD", "postgres"),
        h=get("POSTGRES_HOST", "localhost"), port=get("POSTGRES_PORT", "5432"),
        d=get("POSTGRES_DB", "quarantine"))


def proxy_url() -> str:
    return get("DATABASE_URL_PROXY") or "postgresql://quarantine_proxy:{}@{}:{}/{}".format(
        get("PROXY_DB_PASSWORD", "proxy_local_pw"), get("POSTGRES_HOST", "localhost"),
        get("POSTGRES_PORT", "5432"), get("POSTGRES_DB", "quarantine"))


def reader_url() -> str:
    return get("DATABASE_URL_READER") or "postgresql://memory_reader:{}@{}:{}/{}".format(
        get("READER_DB_PASSWORD", "reader_local_pw"), get("POSTGRES_HOST", "localhost"),
        get("POSTGRES_PORT", "5432"), get("POSTGRES_DB", "quarantine"))

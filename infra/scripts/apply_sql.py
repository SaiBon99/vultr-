"""Apply sql/001_init.sql and set app role passwords. Works on local PG and Vultr Managed PG. Idempotent.

Uses DATABASE_URL_ADMIN, else POSTGRES_* (see .env.example). Passwords: PROXY_DB_PASSWORD, READER_DB_PASSWORD.
Run: uv run --no-project --with "psycopg[binary]" python infra/scripts/apply_sql.py
"""
import sys

import psycopg
from psycopg import sql

import _env

_env.load_env()


def main() -> int:
    init = (_env.INFRA / "sql" / "001_init.sql").read_text(encoding="utf-8")
    proxy_pw = _env.get("PROXY_DB_PASSWORD", "proxy_local_pw")
    reader_pw = _env.get("READER_DB_PASSWORD", "reader_local_pw")
    with psycopg.connect(_env.admin_url(), autocommit=True) as conn:
        conn.execute(init)
        for role, pw in (("quarantine_proxy", proxy_pw), ("memory_reader", reader_pw)):
            conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(pw)))
    print("applied 001_init.sql and role logins")
    return 0


if __name__ == "__main__":
    sys.exit(main())

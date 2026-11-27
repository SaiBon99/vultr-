"""Truncate demo data (schema, roles and grants stay). Requires --yes.

Audit trigger only blocks UPDATE/DELETE; TRUNCATE is allowed for the admin role.
Run: uv run --no-project --with "psycopg[binary]" python infra/scripts/reset_demo.py --yes
"""
import argparse
import sys

import psycopg

import _env

_env.load_env()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="confirm destructive reset")
    if not ap.parse_args().yes:
        print("refusing: pass --yes to truncate sessions, memories, quarantine_queue, audit_events", file=sys.stderr)
        return 2
    with psycopg.connect(_env.admin_url(), autocommit=True) as conn:
        conn.execute("TRUNCATE audit_events, quarantine_queue, memories, sessions RESTART IDENTITY")
    print("demo tables truncated")
    return 0


if __name__ == "__main__":
    sys.exit(main())

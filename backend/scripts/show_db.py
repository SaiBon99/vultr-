"""Print what is in the memory database: row counts, then the newest rows of each table.

Read-only. Uses DATABASE_URL_PROXY from infra/.env. Times are Swedish time (Europe/Stockholm).
Run from backend/:  uv run python scripts/show_db.py [rows per table, default 10]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from app.config import Settings  # noqa: E402

TIME = "to_char(created_at AT TIME ZONE 'Europe/Stockholm', 'YYYY-MM-DD HH24:MI:SS')"
TABLES = {
    "sessions": f"SELECT {TIME}, left(id::text, 8), gate_mode, tainted, write_count,"
    " external_sources->-1->>'source_ref' FROM sessions",
    "memories": f"SELECT {TIME}, source, source_ref, left(content, 70) FROM memories",
    "quarantine_queue": f"SELECT {TIME}, status, verdict, risk_score, rule_flags, judge_status,"
    " judge_note->>'risk_level', judge_note->>'recommended_action', source_ref,"
    " left(content, 70) FROM quarantine_queue",
    "audit_events": f"SELECT {TIME}, seq, event_type, left(event_hash, 20) FROM audit_events",
}
HEADERS = {
    "sessions": "time | session | gate_mode | tainted | writes | last page read",
    "memories": "time | source | source_ref | content",
    "quarantine_queue": "time | status | verdict | risk | flags | judge | judge risk | judge says"
    " | source_ref | content",
    "audit_events": "time | seq | event | hash",
}


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    url = Settings().DATABASE_URL_PROXY.get_secret_value()
    if not url:
        print("DATABASE_URL_PROXY is not set in infra/.env", file=sys.stderr)
        return 2
    with psycopg.connect(url, connect_timeout=10) as conn:
        for table, query in TABLES.items():
            count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"\n=== {table}: {count} rows (newest {min(limit, count)}) ===")
            if count:
                print("   ", HEADERS[table])
            for row in conn.execute(f"{query} ORDER BY created_at DESC LIMIT %s", (limit,)):
                print("   ", " | ".join("" if v is None else str(v) for v in row))
    return 0


if __name__ == "__main__":
    sys.exit(main())

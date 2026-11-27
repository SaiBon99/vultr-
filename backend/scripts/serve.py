"""Run the API with an event loop psycopg async supports on every OS.

Windows' default ProactorEventLoop is incompatible with psycopg async, so plain
`uvicorn app.main:app` fails to connect to Postgres there. Linux (the VX1 VM) is unaffected.
Run: uv run python scripts/serve.py [--port 8000]  (no --reload; use uvicorn on Linux)
"""

import argparse
import asyncio
import selectors
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = uvicorn.Server(
        uvicorn.Config(
            "app.main:app",
            host=args.host,
            port=args.port,
        )
    )
    if sys.platform == "win32":
        asyncio.run(
            server.serve(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()

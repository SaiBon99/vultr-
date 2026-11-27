"""Shopping chat agent. Runs inside the sandbox container with no network. Standard library only.

It reaches the outside only through the host broker, one JSON object per line
(protocol: backend/app/chat/service.py):
  stdin  {"type": "task", "message", "history"}
  stdout {"type": "model", "page_title", "page_text"}   ask for a model turn (page fields are null
                                                         unless a page was just read)
  stdin  {"type": "model_result", "turn"}               turn is {"reply"} or {"tool", "args"}
  stdout {"type": "tool", "tool", "args"}               exactly the turn the host just validated
  stdin  {"type": "fetch_result", ...}                  after a browse; the page body, parsed here
  stdin  {"type": "tool_result", "status", ...}         after any other tool, or a failed browse
  stdout {"type": "result", "reply"}                    the reply from the last model_result
The agent holds no credentials and no history beyond the task. Page text is untrusted: it is
extracted here, inside the sandbox, and handed to the host only to be fed to the model as data.
Any unexpected input ends the agent with exit code 1 and no result line.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

# python -I does not put the script directory on sys.path; the extractor lives next door.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawl_agent import extract  # noqa: E402


def extract_text(body: str, content_type: str) -> tuple[str, str]:
    title, text, _links = extract(body, content_type)
    return title, text

MAX_TURNS = 64  # hard stop; the host enforces the real step cap


def _send(stdout, message: dict[str, Any]) -> None:
    stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    stdout.flush()


def _expect(stdin, *kinds: str) -> dict[str, Any]:
    line = stdin.readline()
    message = json.loads(line) if line else None
    if not isinstance(message, dict) or message.get("type") not in kinds:
        raise SystemExit(1)
    return message


def main(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    _expect(stdin, "task")  # the host keeps the conversation; the task only starts the run
    page_title: str | None = None
    page_text: str | None = None
    for _ in range(MAX_TURNS):
        _send(stdout, {"type": "model", "page_title": page_title, "page_text": page_text})
        page_title = page_text = None
        turn = _expect(stdin, "model_result").get("turn")
        if not isinstance(turn, dict):
            raise SystemExit(1)
        if "reply" in turn:
            _send(stdout, {"type": "result", "reply": turn["reply"]})
            return 0
        _send(stdout, {"type": "tool", "tool": turn.get("tool"), "args": turn.get("args")})
        answer = _expect(stdin, "fetch_result", "tool_result")
        if answer["type"] == "fetch_result":
            page_title, page_text = extract_text(
                str(answer.get("body", "")), str(answer.get("content_type", ""))
            )
    raise SystemExit(1)


if __name__ == "__main__":
    sys.exit(main())

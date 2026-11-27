"""One-page crawler agent. Runs inside the sandbox container with no network. Standard library only.

It reaches the outside only through the host broker, one JSON object per line
(protocol: backend/app/crawl/service.py):
  stdin  {"type": "task", "url"}          stdout {"type": "fetch", "url"}
  stdin  {"type": "fetch_result", ...}    stdout {"type": "model", "page_title", "page_text"}
  stdin  {"type": "model_result", ...}    stdout {"type": "result", <model_result unchanged>}
The agent holds no credentials. Parsing the untrusted page happens here, inside the sandbox.
Any unexpected input ends the agent with exit code 1 and no result line.
"""

from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from typing import Any

PAGE_CHARS = 20_000


class _PageText(HTMLParser):
    _SKIP = frozenset({"script", "style", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip:
            self.text_parts.append(data)


def extract_text(body: str, content_type: str) -> tuple[str, str]:
    if "html" not in content_type.lower():
        return "", " ".join(body.split())[:PAGE_CHARS]
    parser = _PageText()
    parser.feed(body)
    parser.close()
    title = " ".join("".join(parser.title_parts).split())
    text = " ".join(" ".join(parser.text_parts).split())
    return title[:300], text[:PAGE_CHARS]


def _send(stdout, message: dict[str, Any]) -> None:
    stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    stdout.flush()


def _expect(stdin, kind: str) -> dict[str, Any]:
    line = stdin.readline()
    message = json.loads(line) if line else None
    if not isinstance(message, dict) or message.get("type") != kind:
        raise SystemExit(1)
    return message


def main(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    task = _expect(stdin, "task")
    _send(stdout, {"type": "fetch", "url": task["url"]})
    page = _expect(stdin, "fetch_result")
    title, text = extract_text(str(page.get("body", "")), str(page.get("content_type", "")))
    _send(stdout, {"type": "model", "page_title": title, "page_text": text})
    reply = _expect(stdin, "model_result")
    _send(
        stdout,
        {
            "type": "result",
            "title": reply.get("title"),
            "summary": reply.get("summary"),
            "key_points": reply.get("key_points"),
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

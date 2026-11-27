"""Parse-only crawler agent. Runs inside the sandbox container with no network. Standard library only.

The host drives every fetch and every model call. The agent only parses bytes the host hands it
and returns text and links. One JSON object per line (protocol: backend/app/crawl/service.py):
  stdin  {"type": "parse", "url", "content_type", "body"}
  stdout {"type": "parsed", "page_title", "page_text", "links": [{"href", "text"}]}
  stdin  {"type": "end"}                                  exit 0
It holds no credentials and cannot reach the network. Any unexpected input exits with code 1.
"""

from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from typing import Any

PAGE_CHARS = 20_000
MAX_LINKS = 200
LINK_HREF_CHARS = 2048
LINK_TEXT_CHARS = 200


class _PageText(HTMLParser):
    _SKIP = frozenset({"script", "style", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self._skip = 0
        self._in_title = False
        self._href: str | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a" and self._href is None and len(self.links) < MAX_LINKS:
            href = dict(attrs).get("href")
            if href:
                self._href = href[:LINK_HREF_CHARS]
                self._anchor_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            text = " ".join(" ".join(self._anchor_parts).split())[:LINK_TEXT_CHARS]
            self.links.append({"href": self._href, "text": text})
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
            return
        if not self._skip:
            self.text_parts.append(data)
            if self._href is not None:
                self._anchor_parts.append(data)


def extract(body: str, content_type: str) -> tuple[str, str, list[dict[str, str]]]:
    if "html" not in content_type.lower():
        return "", " ".join(body.split())[:PAGE_CHARS], []
    parser = _PageText()
    parser.feed(body)
    parser.close()
    title = " ".join("".join(parser.title_parts).split())[:300]
    text = " ".join(" ".join(parser.text_parts).split())[:PAGE_CHARS]
    return title, text, parser.links


def _send(stdout, message: dict[str, Any]) -> None:
    stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    stdout.flush()


def main(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    while True:
        line = stdin.readline()
        if not line:
            return 1  # host went away without "end"
        try:
            message = json.loads(line)
        except ValueError:
            return 1
        if not isinstance(message, dict):
            return 1
        kind = message.get("type")
        if kind == "end":
            return 0
        if kind != "parse":
            return 1
        title, text, links = extract(str(message.get("body", "")), str(message.get("content_type", "")))
        _send(stdout, {"type": "parsed", "page_title": title, "page_text": text, "links": links})


if __name__ == "__main__":
    sys.exit(main())

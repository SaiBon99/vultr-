"""Host-side page fetch for the sandboxed agent.

Guarded hops, redirect cap, byte cap, content-type check, one host log line per fetch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlsplit

import httpx

from app.crawl.errors import CrawlError
from app.crawl.guard import PublicTargetGuard, Target, UnsafeTarget

log = logging.getLogger("app.crawl")

MAX_REDIRECTS = 3
HOP_TIMEOUT_S = 10.0
USER_AGENT = "memory-quarantine-crawler/0.2"
ROBOTS_UA = "memory-quarantine-crawler"  # the product token robots.txt rules are matched against
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/")


@dataclass(frozen=True)
class Page:
    final_url: str
    status: int
    content_type: str
    text: str
    size: int


async def fetch_page(target: Target, guard: PublicTargetGuard, max_bytes: int) -> Page:
    """GET one page. Every hop is a vetted Target; redirects are followed by hand."""
    first_url = target.url
    # trust_env=False: no HTTP(S)_PROXY or netrc from the host environment.
    async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            hop = await _hop(client, target, guard, max_bytes)
            if isinstance(hop, Page):
                log.info(
                    "crawl fetch url=%s final_url=%s status=%s bytes=%s",
                    _short(first_url),
                    _short(hop.final_url),
                    hop.status,
                    hop.size,
                )
                return hop
            target = hop
    _log_failure(first_url, "redirect cap")
    raise CrawlError(502, "fetch_failed", f"more than {MAX_REDIRECTS} redirects")


async def load_robots(origin: str, guard: PublicTargetGuard, max_bytes: int) -> RobotFileParser:
    """robots.txt for one origin ("scheme://host[:port]"). Missing, refused or unreachable means
    no rules: parse([]) marks the file as read with nothing disallowed."""
    rp = RobotFileParser()
    try:
        target = await guard.check(f"{origin}/robots.txt")
        page = await fetch_page(target, guard, max_bytes)
        rp.parse(page.text.splitlines())
    except (UnsafeTarget, CrawlError):
        rp.parse([])
    return rp


async def _hop(
    client: httpx.AsyncClient, target: Target, guard: PublicTargetGuard, max_bytes: int
) -> Page | Target:
    dial_host, dial_port = guard.dial(target)
    url = httpx.URL(target.url).copy_with(host=dial_host, port=dial_port)
    netloc = urlsplit(target.url).netloc
    request = client.build_request(
        "GET",
        url,
        headers={"Host": netloc, "User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"},
        extensions={"sni_hostname": target.host, "timeout": _timeout()},
    )
    try:
        response = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        _log_failure(target.url, type(exc).__name__)
        raise CrawlError(502, "fetch_failed", "could not connect to the page") from exc
    try:
        if response.status_code in REDIRECT_CODES and "location" in response.headers:
            next_url = urljoin(target.url, response.headers["location"])
            try:
                return await guard.check(next_url)
            except UnsafeTarget as exc:
                _log_failure(target.url, "redirect refused")
                raise CrawlError(
                    502, "fetch_failed", "redirect to a non-public target was refused"
                ) from exc
        if not 200 <= response.status_code < 300:
            _log_failure(target.url, f"status {response.status_code}")
            raise CrawlError(502, "fetch_failed", f"page returned HTTP {response.status_code}")
        ctype = response.headers.get("content-type", "")
        if not ctype.lower().startswith(TEXT_TYPES):
            _log_failure(target.url, "unsupported content")
            raise CrawlError(502, "unsupported_content", "page is not HTML or text")
        body = await _read_capped(response, max_bytes, target.url)
    finally:
        await response.aclose()
    return Page(
        final_url=target.url,
        status=response.status_code,
        content_type=ctype,
        text=body.decode(response.charset_encoding or "utf-8", errors="replace"),
        size=len(body),
    )


async def _read_capped(response: httpx.Response, max_bytes: int, url: str) -> bytes:
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        _log_failure(url, "too large")
        raise CrawlError(502, "page_too_large", f"page is larger than {max_bytes} bytes")
    chunks: list[bytes] = []
    size = 0
    try:
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > max_bytes:
                _log_failure(url, "too large")
                raise CrawlError(502, "page_too_large", f"page is larger than {max_bytes} bytes")
            chunks.append(chunk)
    except httpx.HTTPError as exc:
        _log_failure(url, type(exc).__name__)
        raise CrawlError(502, "fetch_failed", "page download failed") from exc
    return b"".join(chunks)


def _timeout() -> dict[str, float]:
    return {
        "connect": HOP_TIMEOUT_S,
        "read": HOP_TIMEOUT_S,
        "write": HOP_TIMEOUT_S,
        "pool": HOP_TIMEOUT_S,
    }


def _log_failure(url: str, reason: str) -> None:
    log.info("crawl fetch url=%s failed=%s", _short(url), reason)


def _short(url: str) -> str:
    return url[:300]

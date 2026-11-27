"""The broker: orchestrates one crawl across one sandbox and several host-side model roles.

Roles: the sandboxed parser (no network, no credentials, parses the bytes it is handed); the
planner (model, picks which offered links to visit); the reader (model, one call per page); the
synthesiser (model, writes the reviewer summary). The host does every fetch and every model call.

Protocol with the sandbox (one JSON object per line):
  host  -> agent  {"type": "parse", "url": str, "content_type": str, "body": str}
  agent -> host   {"type": "parsed", "page_title": str, "page_text": str, "links": [{"href", "text"}]}
  host  -> agent  {"type": "end"}
Any other message ends the run with 502 agent_crash. The host never sends the inference key, and
the sandbox never sees a URL it did not get from the host.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import uuid4

from app.config import Settings
from app.crawl import model as llm
from app.crawl.errors import CrawlError
from app.crawl.fetch import ROBOTS_UA, Page, fetch_page, load_robots
from app.crawl.guard import PublicTargetGuard, Target, UnsafeTarget
from app.crawl.runner import Limits, ProcessRun, Runner
from app.models import CrawlLimits, CrawlPage, CrawlResult, CrawlSandbox, CrawlUsage
from app.runlog import RunLog, upload_run_log
from app.storage import ObjectStore

MAX_CONCURRENT_RUNS = 2  # D8
PAGE_TEXT_CHARS = 20_000
MODEL_DEADLINE_MARGIN_S = 0.5
MAX_LINKS_FROM_AGENT = 200


class Slots:
    """At most MAX_CONCURRENT_RUNS runs; the next one is refused, never queued (D8)."""

    def __init__(self) -> None:
        self.free = MAX_CONCURRENT_RUNS

    def take(self) -> None:
        if self.free <= 0:
            raise CrawlError(
                503, "sandbox_busy", f"{MAX_CONCURRENT_RUNS} crawl runs are already in progress"
            )
        self.free -= 1

    def give(self) -> None:
        self.free += 1


def _origin(url: str) -> tuple[str, str, int]:
    """scheme, host, port with defaults filled in. ValueError on an unparseable port."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    port = parts.port or (443 if scheme == "https" else 80)
    return scheme, (parts.hostname or "").lower(), port


def _clean(url: str) -> str:
    """Canonical form for dedupe: lower-case scheme and host, no fragment."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def _denied_origins(settings: Settings) -> frozenset[tuple[str, str, int]]:
    """Origins the crawler must never fetch (this host's own API, for example)."""
    out = set()
    for entry in settings.CRAWL_DENY_ORIGINS.split(","):
        if entry.strip():
            with contextlib.suppress(ValueError):
                out.add(_origin(entry.strip()))
    return frozenset(out)


async def crawl(
    url: str,
    *,
    settings: Settings,
    guard: PublicTargetGuard,
    runner: Runner,
    slots: Slots,
    store: ObjectStore | None = None,
) -> CrawlResult:
    if not settings.VULTR_INFERENCE_API_KEY.get_secret_value():
        raise CrawlError(
            503, "inference_not_configured", "Inference is not configured on this host"
        )
    denied = _denied_origins(settings)
    try:
        target = await guard.check(url)
        if _origin(target.url) in denied:
            raise UnsafeTarget("origin is not allowed")
    except UnsafeTarget as exc:
        raise CrawlError(422, "unsafe_target", str(exc)) from exc

    limits = Limits(
        memory_mb=runner.limits.memory_mb,
        cpus=runner.limits.cpus,
        timeout_s=settings.CRAWL_TIMEOUT_S,
    )
    slots.take()
    # From here on every run gets a run_id and a transcript, whatever the outcome.
    run_id = str(uuid4())
    runlog = RunLog(run_id, "crawl", None, limits)
    run: ProcessRun | None = None
    crawl_state: _Crawl | None = None
    summary: llm.Summary | None = None
    container_id: str | None = None
    image_id: str | None = None
    http_status, error_code = 500, None  # anything not caught below is an internal error
    started = time.monotonic()
    try:
        try:
            async with asyncio.timeout(limits.timeout_s):
                run = await runner.start()  # the clock covers start, every fetch and model call
                runlog.start(run.image_id)
                crawl_state = _Crawl(
                    run, target, settings, guard, started + limits.timeout_s, runlog, denied
                )
                summary = await crawl_state.execute()
                container_id, image_id = await run.sandbox_ids()
        except TimeoutError as exc:
            raise CrawlError(
                504, "timeout", f"crawl hit the {limits.timeout_s} s limit and was killed"
            ) from exc
        http_status = 200
    except CrawlError as exc:
        http_status, error_code = exc.status_code, exc.code
        exc.run_id = run_id
        raise
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if run is not None and container_id is None:
            container_id = await _container_id(run)  # read before cleanup removes the cidfile
        try:
            if run is not None:
                await run.cleanup()
        finally:
            slots.give()
        # After the container is gone and outside the sandbox clock; never changes the response.
        stderr, stderr_truncated = await run.stderr_text() if run is not None else ("", False)
        runlog.finish(
            status="ok" if http_status == 200 else "error",
            http_status=http_status,
            error_code=error_code,
            exit_code=run.proc.returncode if run is not None else None,
            container_id=container_id,
            elapsed_ms=elapsed_ms,
            stderr=stderr,
            stderr_truncated=stderr_truncated,
        )
        log_uri = await upload_run_log(store, runlog, settings.log_secrets)

    assert crawl_state is not None and crawl_state.seed_page is not None
    assert summary is not None and container_id is not None and image_id is not None
    usage = crawl_state.usage
    return CrawlResult(
        url=url,
        final_url=crawl_state.seed_page.final_url,
        title=summary.title,
        summary=summary.summary,
        key_points=summary.key_points,
        model=summary.model,
        inference_id=summary.inference_id,
        usage=CrawlUsage(**usage) if usage else None,
        elapsed_ms=elapsed_ms,
        sandbox=CrawlSandbox(
            runtime="docker",
            container_id=container_id,
            image_id=image_id,
            network="none",
            limits=CrawlLimits(**dataclasses.asdict(limits)),
        ),
        run_id=run_id,
        log_uri=log_uri,
        pages=crawl_state.pages,
    )


async def _container_id(run: ProcessRun) -> str | None:
    try:
        return (await run.sandbox_ids())[0]
    except Exception:  # not started, or no cidfile yet: the transcript just has no id
        return None


@dataclass(frozen=True)
class _Parsed:
    title: str
    text: str
    links: list[dict[str, str]]


class _Crawl:
    """One run: seed page, then the planner's picks (same origin, budgeted), then the summary."""

    def __init__(
        self,
        run: ProcessRun,
        target: Target,
        settings: Settings,
        guard: PublicTargetGuard,
        deadline: float,
        runlog: RunLog,
        denied: frozenset[tuple[str, str, int]],
    ) -> None:
        self.run = run
        self.target = target
        self.settings = settings
        self.guard = guard
        self.deadline = deadline
        self.runlog = runlog
        self.denied = denied
        self.seed_origin = _origin(target.url)
        self.naive = settings.CRAWL_PROMPT_MODE == "naive" and settings.DEMO_ALLOW_NAIVE
        self.seed_page: Page | None = None
        self.pages: list[CrawlPage] = []
        self.notes: list[dict[str, Any]] = []
        self.visited: set[str] = set()
        self.robots: dict[str, RobotFileParser] = {}
        self.usage: dict[str, int] | None = None

    async def execute(self) -> llm.Summary:
        if self.naive:
            self.runlog.host("prompt", mode="naive")
        seed_page = await self._fetch(self.target)  # a failed seed fails the run
        self.seed_page = seed_page
        self.visited.add(_clean(seed_page.final_url))
        seed = await self._parse(seed_page)
        self.pages.append(
            CrawlPage(
                url=self.target.url,
                final_url=seed_page.final_url,
                status="ok",
                title=seed.title or None,
            )
        )
        await self._read(seed_page.final_url, seed)

        budget = self.settings.CRAWL_MAX_PAGES - 1
        candidates = self._candidates(seed.links, seed_page.final_url)
        if candidates and budget > 0:
            picks = await self._plan(seed_page.final_url, seed, candidates, budget)
            for index in picks:
                await self._visit(candidates[index]["url"])

        summary = await self._synthesise()
        await self._finish()
        return summary

    def _candidates(self, links: list[dict[str, str]], base: str) -> list[dict[str, str]]:
        """Links the planner may choose from: http(s), no credentials, same origin, not denied."""
        seen = set(self.visited)
        out: list[dict[str, str]] = []
        for link in links:
            try:
                absolute = urljoin(base, link["href"])
                parts = urlsplit(absolute)
                origin = _origin(absolute)
            except ValueError:
                continue
            if parts.scheme not in ("http", "https") or not parts.hostname:
                continue
            if parts.username is not None or parts.password is not None:
                continue
            if origin != self.seed_origin or origin in self.denied:
                continue
            clean = _clean(absolute)
            if clean in seen:
                continue
            seen.add(clean)
            out.append({"url": clean, "text": link["text"]})
            if len(out) == self.settings.CRAWL_MAX_LINKS:
                break
        return out

    async def _plan(
        self, url: str, parsed: _Parsed, candidates: list[dict[str, str]], budget: int
    ) -> list[int]:
        called = time.monotonic()
        picks, comp = await llm.plan_links(
            self.settings,
            url=url,
            page_title=parsed.title,
            page_text=parsed.text,
            candidates=candidates,
            limit=budget,
            timeout_s=self._model_timeout(),
            naive=self.naive,
        )
        self._account("plan", comp, called)
        return picks

    async def _visit(self, url: str) -> None:
        """One linked page. Its failures are recorded and the run goes on; agent errors do not."""
        try:
            target = await self.guard.check(url)
        except UnsafeTarget as exc:
            self.pages.append(CrawlPage(url=url, final_url=None, status="skipped", error=str(exc)))
            return
        robots = await self._robots(target)
        if not robots.can_fetch(ROBOTS_UA, url):
            self.pages.append(
                CrawlPage(url=url, final_url=None, status="skipped", error="robots_disallowed")
            )
            return
        try:
            page = await self._fetch(target)
        except CrawlError as exc:
            self.pages.append(CrawlPage(url=url, final_url=None, status="failed", error=exc.code))
            return
        key = _clean(page.final_url)
        if key in self.visited:
            self.pages.append(CrawlPage(url=url, final_url=page.final_url, status="skipped", error="duplicate"))
            return
        self.visited.add(key)
        parsed = await self._parse(page)
        self.pages.append(
            CrawlPage(url=url, final_url=page.final_url, status="ok", title=parsed.title or None)
        )
        await self._read(page.final_url, parsed)

    async def _read(self, url: str, parsed: _Parsed) -> None:
        called = time.monotonic()
        note, comp = await llm.read_page(
            self.settings,
            url=url,
            page_title=parsed.title,
            page_text=parsed.text,
            timeout_s=self._model_timeout(),
            naive=self.naive,
        )
        self._account("read", comp, called)
        self.notes.append({"url": url, "title": note.title, "facts": note.facts})

    async def _synthesise(self) -> llm.Summary:
        called = time.monotonic()
        summary, comp = await llm.synthesise(
            self.settings, notes=self.notes, timeout_s=self._model_timeout(), naive=self.naive
        )
        self._account("synthesise", comp, called)
        return summary

    def _account(self, role: str, comp: llm.Completion, called: float) -> None:
        """Never the prompt or the reply: only what identifies and prices the call."""
        self.usage = llm.add_usage(self.usage, comp.usage)
        self.runlog.host(
            "model",
            role=role,
            model=comp.model,
            inference_id=comp.inference_id,
            usage=comp.usage,
            latency_ms=_ms_since(called),
        )

    def _model_timeout(self) -> float:
        # Ends just before the run deadline, so a slow model is inference_failed, not 504.
        return self.deadline - time.monotonic() - MODEL_DEADLINE_MARGIN_S

    async def _robots(self, target: Target) -> RobotFileParser:
        parts = urlsplit(target.url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            self.robots[origin] = await load_robots(origin, self.guard, self.settings.CRAWL_MAX_BYTES)
        return self.robots[origin]

    async def _fetch(self, target: Target) -> Page:
        try:
            page = await fetch_page(target, self.guard, self.settings.CRAWL_MAX_BYTES)
        except CrawlError as exc:
            self.runlog.host("fetch", url=target.url, error_code=exc.code)
            raise
        self.runlog.host(
            "fetch",
            final_url=page.final_url,
            status=page.status,
            bytes=page.size,
            content_type=page.content_type,
        )
        return page

    async def _parse(self, page: Page) -> _Parsed:
        await self._send(
            {
                "type": "parse",
                "url": page.final_url,
                "content_type": page.content_type,
                "body": page.text,
            }
        )
        message = await self._next()
        title, text, links = message.get("page_title"), message.get("page_text"), message.get("links")
        if (
            message.get("type") != "parsed"
            or not isinstance(title, str)
            or not isinstance(text, str)
            or not isinstance(links, list)
        ):
            raise _crash("agent parse reply is malformed")
        clean: list[dict[str, str]] = []
        for link in links[:MAX_LINKS_FROM_AGENT]:
            if not isinstance(link, dict) or not isinstance(link.get("href"), str):
                raise _crash("agent parse reply is malformed")
            if not isinstance(link.get("text"), str):
                raise _crash("agent parse reply is malformed")
            clean.append({"href": link["href"], "text": link["text"]})
        return _Parsed(title=title[:300], text=text[:PAGE_TEXT_CHARS], links=clean)

    async def _finish(self) -> None:
        message = {"type": "end"}
        self.runlog.sent(message)
        with contextlib.suppress(OSError):  # the agent may already have exited; cleanup handles it
            await self.run.send(message)

    async def _send(self, message: dict[str, Any]) -> None:
        self.runlog.sent(message)
        try:
            await self.run.send(message)
        except OSError as exc:  # BrokenPipeError / ConnectionResetError: the agent is gone
            raise await self._gone() from exc

    async def _gone(self) -> CrawlError:
        code = await self.run.wait()
        if code != 0 and not self.run.spoke:
            return CrawlError(502, "sandbox_failed", f"sandbox exited with code {code}")
        return _crash("agent exited without a result")

    async def _next(self) -> dict[str, Any]:
        try:
            line = await self.run.receive()
        except ValueError as exc:  # line over LINE_LIMIT
            raise _crash("agent message is too long") from exc
        if not line:
            raise await self._gone()
        try:
            message = json.loads(line)
        except ValueError:
            message = None
        if not isinstance(message, dict):
            self.runlog.received(line, None)
            raise _crash("agent sent a malformed message")
        self.runlog.received(line, message)
        return message


def _ms_since(t: float) -> int:
    return int((time.monotonic() - t) * 1000)


def _crash(detail: str) -> CrawlError:
    return CrawlError(502, "agent_crash", detail)

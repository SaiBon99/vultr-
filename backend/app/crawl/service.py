"""The broker: runs one agent in one sandbox and answers its two requests, fetch and model.

Protocol (one JSON object per line):
  host  -> agent  {"type": "task", "url": str}
  agent -> host   {"type": "fetch", "url": <the task url>}
  host  -> agent  {"type": "fetch_result", "final_url", "content_type", "body"}
  agent -> host   {"type": "model", "page_title": str, "page_text": str}
  host  -> agent  {"type": "model_result", "title", "summary", "key_points"}
  agent -> host   {"type": "result", "title", "summary", "key_points"}  (must equal model_result)
Each request is allowed once and in this order. Anything else ends the run with 502 agent_crash.
The host never sends the inference key, and failures are never reported back to the agent: the
run is killed and the error returned to the caller.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from typing import Any

from app.config import Settings
from app.crawl.errors import CrawlError
from app.crawl.fetch import Page, fetch_page
from app.crawl.guard import PublicTargetGuard, Target, UnsafeTarget
from app.crawl.model import Summary, summarise
from app.crawl.runner import ProcessRun, Runner
from app.models import CrawlLimits, CrawlResult, CrawlSandbox, CrawlUsage

MAX_CONCURRENT_RUNS = 2  # D8
PAGE_TEXT_CHARS = 20_000
MODEL_DEADLINE_MARGIN_S = 0.5


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


async def crawl(
    url: str, *, settings: Settings, guard: PublicTargetGuard, runner: Runner, slots: Slots
) -> CrawlResult:
    if not settings.VULTR_INFERENCE_API_KEY.get_secret_value():
        raise CrawlError(
            503, "inference_not_configured", "Inference is not configured on this host"
        )
    try:
        target = await guard.check(url)
    except UnsafeTarget as exc:
        raise CrawlError(422, "unsafe_target", str(exc)) from exc

    slots.take()
    run: ProcessRun | None = None
    try:
        started = time.monotonic()
        try:
            async with asyncio.timeout(runner.limits.timeout_s):
                run = await runner.start()  # the clock covers container start, fetch and model
                broker = _Broker(run, target, settings, guard, started + runner.limits.timeout_s)
                await broker.serve()
                container_id, image_id = await run.sandbox_ids()
        except TimeoutError as exc:
            raise CrawlError(
                504, "timeout", f"sandbox hit the {runner.limits.timeout_s} s limit and was killed"
            ) from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)
    finally:
        try:
            if run is not None:
                await run.cleanup()
        finally:
            slots.give()

    assert broker.page is not None and broker.summary is not None and broker.result is not None
    title, summary, key_points = broker.result
    s = broker.summary
    return CrawlResult(
        url=url,
        final_url=broker.page.final_url,
        title=title,
        summary=summary,
        key_points=key_points,
        model=s.model,
        inference_id=s.inference_id,
        usage=CrawlUsage(**s.usage) if s.usage else None,
        elapsed_ms=elapsed_ms,
        sandbox=CrawlSandbox(
            runtime="docker",
            container_id=container_id,
            image_id=image_id,
            network="none",
            limits=CrawlLimits(**dataclasses.asdict(runner.limits)),
        ),
    )


class _Broker:
    def __init__(
        self,
        run: ProcessRun,
        target: Target,
        settings: Settings,
        guard: PublicTargetGuard,
        deadline: float,
    ) -> None:
        self.run = run
        self.target = target
        self.settings = settings
        self.guard = guard
        self.deadline = deadline
        self.page: Page | None = None
        self.summary: Summary | None = None
        self.result: tuple[str, str, list[str]] | None = None

    async def serve(self) -> None:
        await self._send({"type": "task", "url": self.target.url})
        while self.result is None:
            message = await self._next()
            kind = message.get("type")
            if kind == "fetch" and self.page is None and message.get("url") == self.target.url:
                await self._fetch()
            elif kind == "model" and self.page is not None and self.summary is None:
                await self._model(message)
            elif kind == "result" and self.summary is not None:
                self.result = self._check_result(message)
            else:
                raise _crash("agent sent an unexpected message")

    def _check_result(self, message: dict[str, Any]) -> tuple[str, str, list[str]]:
        """The agent may only hand back the summary the host validated, unchanged."""
        assert self.summary is not None
        expected = (self.summary.title, self.summary.summary, self.summary.key_points)
        got = (message.get("title"), message.get("summary"), message.get("key_points"))
        if got != expected:
            raise _crash("agent result differs from the validated summary")
        return expected

    async def _send(self, message: dict[str, Any]) -> None:
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
        except ValueError as exc:
            raise _crash("agent sent a malformed message") from exc
        if not isinstance(message, dict):
            raise _crash("agent sent a malformed message")
        return message

    async def _fetch(self) -> None:
        self.page = await fetch_page(self.target, self.guard, self.settings.CRAWL_MAX_BYTES)
        await self._send(
            {
                "type": "fetch_result",
                "final_url": self.page.final_url,
                "content_type": self.page.content_type,
                "body": self.page.text,
            }
        )

    async def _model(self, message: dict[str, Any]) -> None:
        title, text = message.get("page_title"), message.get("page_text")
        if not isinstance(title, str) or not isinstance(text, str):
            raise _crash("agent model request is malformed")
        assert self.page is not None
        self.summary = await summarise(
            self.settings,
            url=self.page.final_url,
            page_title=title[:300],
            page_text=text[:PAGE_TEXT_CHARS],
            # Ends just before the run deadline, so a slow model is inference_failed, not 504.
            timeout_s=self.deadline - time.monotonic() - MODEL_DEADLINE_MARGIN_S,
        )
        await self._send(
            {
                "type": "model_result",
                "title": self.summary.title,
                "summary": self.summary.summary,
                "key_points": self.summary.key_points,
            }
        )


def _crash(detail: str) -> CrawlError:
    return CrawlError(502, "agent_crash", detail)

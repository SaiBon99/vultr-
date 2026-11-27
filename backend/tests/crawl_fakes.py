"""Offline doubles for POST /crawl: local page and model servers, fake DNS, a subprocess runner.

The runner runs the real sandbox agent as a local subprocess with an empty environment, so the
broker protocol is exercised end to end without Docker. The guard is the real PublicTargetGuard
with a fake resolver; only the dial step is redirected to the local page server.
"""

from __future__ import annotations

import contextlib
import json
import secrets
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.crawl.guard import PublicTargetGuard, Target
from app.crawl.runner import Limits, ProcessRun

AGENT = Path(__file__).resolve().parents[1] / "sandbox" / "crawl_agent.py"
PUBLIC_IP = "93.184.216.34"


class LocalServer:
    """Threaded HTTP server on 127.0.0.1. routes: path -> (status, headers, body bytes)."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[int, dict[str, str], bytes]] = {}
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.requests.append(
                    {"path": self.path, "headers": dict(self.headers), "body": body}
                )
                status, headers, payload = outer.routes.get(
                    self.path, (404, {"Content-Type": "text/plain"}, b"not found")
                )
                if callable(payload):
                    payload = payload(body)
                self.send_response(status)
                for k, v in headers.items():
                    if v is not None:  # None: omit the header (Content-Length None = read to EOF)
                        self.send_header(k, v)
                if "Content-Length" not in headers:
                    self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                # The client may stop reading at its byte cap.
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    self.wfile.write(payload)

            do_GET = do_POST = _serve

            def log_message(self, *args) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(
            target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        ).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def chat_reply(content: str, *, completion_id: str | None = "cmpl-test-1", usage=None) -> bytes:
    body: dict = {
        "object": "chat.completion",
        "model": "qwen3.8-27b",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }
    if completion_id is not None:
        body["id"] = completion_id
    if usage is not None:
        body["usage"] = usage
    return json.dumps(body).encode()


class FakeResolver:
    """getaddrinfo-shaped. names: host -> list of IP strings."""

    def __init__(self, names: dict[str, list[str]]) -> None:
        self.names = names

    def __call__(self, host, port, *args, **kwargs):
        if host not in self.names:
            raise socket.gaierror("unknown host")
        out = []
        for ip in self.names[host]:
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            sockaddr = (ip, port, 0, 0) if fam == socket.AF_INET6 else (ip, port)
            out.append((fam, socket.SOCK_STREAM, 6, "", sockaddr))
        return out


class FakeGuard(PublicTargetGuard):
    """Real rules, fake DNS. Every vetted address dials the local page server instead."""

    def __init__(self, names: dict[str, list[str]], page_port: int) -> None:
        super().__init__(resolver=FakeResolver(names))
        self.page_port = page_port
        self.dialed: list[str] = []

    def dial(self, target: Target) -> tuple[str, int]:
        self.dialed.append(target.ip)
        return "127.0.0.1", self.page_port


class RecordingRun(ProcessRun):
    def __init__(self, proc, container_id: str, image_id: str, sent: list[bytes], runner) -> None:
        super().__init__(proc)
        self._ids = (container_id, image_id)
        self.image_id = image_id
        self._sent = sent
        self._runner = runner

    async def send(self, message: dict) -> None:
        self._sent.append(json.dumps(message).encode())
        await super().send(message)

    async def sandbox_ids(self) -> tuple[str, str]:
        return self._ids

    async def cleanup(self) -> None:
        self._runner.cleanups += 1
        await super().cleanup()


class FakeRunner:
    """Runs the real agent (or a stand-in script) as a local subprocess with no environment."""

    def __init__(self, limits: Limits, script: str | None = None) -> None:
        self.limits = limits
        self.script = script
        self.starts = 0
        self.cleanups = 0
        self.sent: list[bytes] = []

    async def start(self) -> RecordingRun:
        import asyncio

        self.starts += 1
        argv = [sys.executable, "-I"]
        argv += ["-c", self.script] if self.script else [str(AGENT)]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={},
            limit=ProcessRun.LINE_LIMIT,
        )
        return RecordingRun(
            proc, secrets.token_hex(32), "sha256:" + secrets.token_hex(32), self.sent, self
        )

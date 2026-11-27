"""Integration: a sandbox with egress_allow reaches only the proxy endpoint. Needs /dev/kvm and msb.

Set TEST_HOST_IP to an address the sandbox can reach on this host (on the VX1 VM: its public IP).
"""

import asyncio
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from backend.app.sandbox import SandboxRunner

pytestmark = pytest.mark.integration

HOST_IP = os.environ.get("TEST_HOST_IP", "")


class _Ok(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server naming
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # silence test output
        pass


@pytest.fixture
def proxy_server():
    server = ThreadingHTTPServer(("0.0.0.0", 0), _Ok)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


def _probe(url: str) -> str:
    return (
        "import urllib.request, sys\n"
        "try:\n"
        f"    urllib.request.urlopen({url!r}, timeout=8)\n"
        "    print('REACHED')\n"
        "except Exception as e:\n"
        "    print('BLOCKED', type(e).__name__)\n"
    )


@pytest.mark.skipif(not HOST_IP, reason="set TEST_HOST_IP to this host's address")
async def test_allowed_endpoint_is_reachable_and_everything_else_is_not(proxy_server):
    runner = SandboxRunner(egress_allow=(HOST_IP, proxy_server), exec_timeout_s=90, max_duration_s=120)

    allowed = await runner.run_python(_probe(f"http://{HOST_IP}:{proxy_server}/"))
    denied_public = await runner.run_python(_probe("http://1.1.1.1/"))
    denied_other_port = await runner.run_python(_probe(f"http://{HOST_IP}:{proxy_server + 1}/"))

    assert allowed.stdout.strip() == "REACHED", allowed.stderr
    assert denied_public.stdout.strip().startswith("BLOCKED"), denied_public.stdout
    assert denied_other_port.stdout.strip().startswith("BLOCKED"), denied_other_port.stdout

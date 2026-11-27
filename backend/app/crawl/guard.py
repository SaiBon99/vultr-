"""Public-target guard: only public http(s) hosts, checked before the run and on every redirect hop.

`check` resolves the host once and returns the vetted address; the fetch dials that
address (`dial`), so a second DNS answer cannot point the request inward
(no check-then-resolve gap).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

Resolver = Callable[..., Any]


class UnsafeTarget(Exception):
    """The URL is not a public http(s) target. The message is safe to return."""


@dataclass(frozen=True)
class Target:
    url: str
    scheme: str
    host: str  # as written in the URL, without brackets
    port: int
    ip: str  # vetted public address the fetch dials


def is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])  # ValueError on malformed input
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped or ip.sixtofour
        if mapped is not None:
            ip = mapped
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


class PublicTargetGuard:
    def __init__(self, resolver: Resolver = socket.getaddrinfo) -> None:
        self._resolver = resolver

    async def check(self, url: str) -> Target:
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as exc:
            raise UnsafeTarget("URL cannot be parsed") from exc
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            raise UnsafeTarget("only http and https URLs are allowed")
        if not parts.hostname:
            raise UnsafeTarget("URL has no host")
        if parts.username is not None or parts.password is not None:
            raise UnsafeTarget("URLs with credentials are not allowed")
        host = parts.hostname
        port = port or (443 if scheme == "https" else 80)
        addresses = await self._addresses(host, port)
        try:
            all_public = bool(addresses) and all(is_public_ip(a) for a in addresses)
        except ValueError:
            all_public = False
        if not all_public:
            raise UnsafeTarget("target does not resolve to public addresses only")
        return Target(url=url, scheme=scheme, host=host, port=port, ip=addresses[0])

    async def _addresses(self, host: str, port: int) -> list[str]:
        try:
            ipaddress.ip_address(host.split("%")[0])
            return [host]
        except ValueError:
            pass
        try:
            infos = await asyncio.to_thread(self._resolver, host, port, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as exc:
            raise UnsafeTarget("host does not resolve") from exc
        seen: list[str] = []
        for info in infos:
            addr = str(info[4][0])
            if addr not in seen:
                seen.append(addr)
        return seen

    def dial(self, target: Target) -> tuple[str, int]:
        """Address and port the fetch connects to. Tests override this to reach a local server."""
        return target.ip, target.port

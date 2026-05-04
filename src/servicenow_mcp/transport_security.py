"""Shared HTTP-transport security primitives.

Hosts the SecurityMiddleware ASGI middleware and helper functions used
by every HTTP-based MCP transport in this codebase. Lives here (not in
a transport-specific module) because the security contract is identical
across transports — bearer token, Host/Origin allowlist, ``/health``
bypass — and we don't want it to drift if a new transport is added.

Originally landed in ``server_sse.py`` as part of the upstream
``fix/sse-auth-hardening`` branch (commit ``c77861e``); extracted here
when the SSE transport was retired in favor of Streamable HTTP.

The five defenses provided by SecurityMiddleware are transport-agnostic
and apply equally to any future HTTP-based MCP transport:

- Loopback bind by default (the CLI helpers below refuse to bind a
  non-loopback address without ``--allow-remote`` AND ``MCP_AUTH_TOKEN``).
- Bearer-token gate validated with ``hmac.compare_digest`` (constant
  time, no timing leak).
- ``Host`` header allowlist  → 421 Misdirected Request (DNS-rebinding
  defense — the most important defense for local-network MCP servers).
- ``Origin`` header allowlist → 403 Forbidden (CSRF defense for any
  browser-originated cross-site request).
- Pure ASGI middleware, *not* Starlette ``BaseHTTPMiddleware`` —
  ``BaseHTTPMiddleware`` buffers responses and silently breaks streaming.
  The pure-ASGI form keeps SSE/Streamable HTTP responses unbuffered.

The ``/health`` path bypasses the bearer-token check (so platform
liveness probes work without a token) but still goes through the Host
allowlist (the DNS-rebinding defense applies to every endpoint).
"""

from __future__ import annotations

import hmac
import os
import secrets
import sys
from typing import Iterable, List, Optional, Set

from starlette.datastructures import Headers


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "0:0:0:0:0:0:0:1"}
_TRUTHY = {"1", "true", "yes", "on"}


def is_loopback_host(host: str) -> bool:
    """Return True if ``host`` is one of the standard loopback addresses."""
    return host.lower().strip() in _LOOPBACK_HOSTS


def resolve_auth_token(*, allow_remote: bool, transport_name: str = "servicenow-mcp") -> str:
    """Read MCP_AUTH_TOKEN, autogenerate on loopback, or fail on remote.

    Args:
        allow_remote: True if the server has been told to bind to a
            non-loopback address (via --allow-remote or MCP_ALLOW_REMOTE).
            When True, MCP_AUTH_TOKEN must be set explicitly — auto-
            generation is refused for safety.
        transport_name: Logged in the auto-generated-token message so the
            operator knows which transport printed it.

    Returns:
        The bearer token MCP clients must present in the
        ``Authorization: Bearer <token>`` header.

    Raises:
        SystemExit: If allow_remote=True and MCP_AUTH_TOKEN is unset.
    """
    tok = os.getenv("MCP_AUTH_TOKEN", "").strip()
    if tok:
        return tok
    if allow_remote:
        raise SystemExit("MCP_AUTH_TOKEN must be set when --allow-remote is used")
    tok = secrets.token_urlsafe(32)
    print(f"[{transport_name}] generated auth token: {tok}", file=sys.stderr, flush=True)
    return tok


def build_allowed_hosts(
    host: str,
    port: int,
    extra: Optional[Iterable[str]] = None,
) -> Set[str]:
    """Build the Host-header allowlist for SecurityMiddleware.

    Always includes the standard loopback variants (with and without
    port). Adds the bound host:port when not loopback. Optionally adds
    operator-provided extra entries (e.g. via MCP_ALLOWED_HOSTS).

    Returned set is lowercase.
    """
    base = {
        "127.0.0.1",
        f"127.0.0.1:{port}",
        "localhost",
        f"localhost:{port}",
        "[::1]",
        f"[::1]:{port}",
    }
    if not is_loopback_host(host):
        base.add(host)
        base.add(f"{host}:{port}")
    if extra:
        for entry in extra:
            entry = entry.strip()
            if entry:
                base.add(entry)
    return {h.lower() for h in base}


def build_allowed_origins(allowed_hosts: Set[str]) -> Set[str]:
    """Build the Origin-header allowlist for SecurityMiddleware.

    For each host in the Host allowlist, accept both ``http://`` and
    ``https://`` origins. We don't try to be smarter than this — the
    Host allowlist is the primary defense, Origin is a CSRF backstop.
    """
    origins: Set[str] = set()
    for host in allowed_hosts:
        origins.add(f"http://{host}")
        origins.add(f"https://{host}")
    return origins


async def _send_text(
    send,
    status: int,
    body: bytes,
    *,
    extra_headers: Optional[List] = None,
):
    """ASGI-protocol helper: send a plain-text response in one shot."""
    headers = [(b"content-type", b"text/plain; charset=utf-8")]
    if extra_headers:
        headers.extend(extra_headers)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class SecurityMiddleware:
    """ASGI middleware: bearer-token auth + Host/Origin allowlist + /health bypass.

    Pure ASGI (not Starlette ``BaseHTTPMiddleware``) so streaming
    responses stay unbuffered. Don't switch to ``BaseHTTPMiddleware`` —
    it'll silently break Streamable HTTP just like it broke SSE.
    """

    def __init__(
        self,
        app,
        *,
        token: str,
        allowed_hosts: Set[str],
        allowed_origins: Set[str],
    ):
        self.app = app
        self._token = token.encode("utf-8")
        self._allowed_hosts = {h.lower() for h in allowed_hosts}
        self._allowed_origins = {o.lower() for o in allowed_origins}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # /health is a liveness probe — bypasses bearer auth so platform
        # health checks (Cloud Run, K8s liveness probes, ALB target-group
        # checks, Docker HEALTHCHECK) work without provisioning the token.
        # Returns only "OK" — no instance state, no tool surface, nothing
        # exfiltratable. Host/Origin allowlist still applies to defend
        # against DNS rebinding.
        is_health_probe = (
            scope.get("method") == "GET" and scope.get("path") == "/health"
        )

        headers = Headers(scope=scope)

        host = headers.get("host", "").lower().strip()
        if host not in self._allowed_hosts:
            await _send_text(send, 421, b"Misdirected Request: Host not in allowlist")
            return

        origin = headers.get("origin")
        if origin is not None:
            if origin.lower().strip() not in self._allowed_origins:
                await _send_text(send, 403, b"Forbidden: Origin not in allowlist")
                return

        if is_health_probe:
            # Allow the request through without bearer-token enforcement.
            await self.app(scope, receive, send)
            return

        auth = headers.get("authorization", "")
        scheme, _, value = auth.partition(" ")
        if (
            scheme.lower() != "bearer"
            or not value
            or not hmac.compare_digest(value.encode("utf-8"), self._token)
        ):
            await _send_text(
                send,
                401,
                b"Unauthorized",
                extra_headers=[(b"www-authenticate", b"Bearer")],
            )
            return

        await self.app(scope, receive, send)

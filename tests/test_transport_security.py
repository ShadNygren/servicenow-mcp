"""Comprehensive tests for ``servicenow_mcp.transport_security``.

This is the central security module shared by all HTTP-based MCP
transports. We test it directly (not via a transport-specific module)
because:

- The contract is transport-agnostic — every HTTP transport gets the
  same protections.
- Failures here are security regressions; we want them surfaced before
  any transport-specific test fails.
- Phase 7 retired the SSE transport; the per-transport SSE tests went
  with it. The shared-module tests stay.

Coverage:

- :func:`is_loopback_host` — recognizes the standard loopback variants
  including IPv6 short and long forms; rejects non-loopback.
- :func:`resolve_auth_token` — prefers ``MCP_AUTH_TOKEN`` env, falls back
  to a fresh random token on loopback, refuses to autogenerate on
  remote bind.
- :func:`build_allowed_hosts` — loopback variants always present, the
  bound non-loopback host added when applicable, extras merged,
  result is lowercase.
- :func:`build_allowed_origins` — both http:// and https:// for every
  allowed host.
- :class:`SecurityMiddleware` — bearer-token gate, Host-header gate,
  Origin-header gate, /health bypass behavior, GET-only health bypass,
  pure-ASGI streaming-safe behavior on non-http scopes.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from servicenow_mcp.transport_security import (
    SecurityMiddleware,
    build_allowed_hosts,
    build_allowed_origins,
    is_loopback_host,
    resolve_auth_token,
)


# ---------------------------------------------------------------------------
# is_loopback_host
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "LOCALHOST",  # case-insensitive
        "  127.0.0.1  ",  # whitespace tolerated
        "::1",
        "[::1]",
        "0:0:0:0:0:0:0:1",
    ],
)
def test_is_loopback_host_true(host):
    assert is_loopback_host(host) is True


@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0",
        "10.0.0.1",
        "192.168.1.1",
        "example.com",
        "evil.example.com",
        "127.0.0.2",  # not actually loopback per our allowlist
    ],
)
def test_is_loopback_host_false(host):
    assert is_loopback_host(host) is False


# ---------------------------------------------------------------------------
# resolve_auth_token
# ---------------------------------------------------------------------------


def test_resolve_auth_token_env_wins(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "explicit-token-value")
    assert resolve_auth_token(allow_remote=False) == "explicit-token-value"


def test_resolve_auth_token_env_wins_even_when_remote(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "explicit-token-value")
    assert resolve_auth_token(allow_remote=True) == "explicit-token-value"


def test_resolve_auth_token_blank_env_treated_as_unset(monkeypatch, capsys):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "   ")
    tok = resolve_auth_token(allow_remote=False)
    assert tok != ""
    assert tok != "   "
    assert len(tok) > 30  # Auto-generated tokens are long.
    err = capsys.readouterr().err
    assert "generated auth token" in err


def test_resolve_auth_token_autogen_on_loopback(monkeypatch, capsys):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    tok = resolve_auth_token(allow_remote=False)
    assert isinstance(tok, str)
    assert len(tok) > 30
    err = capsys.readouterr().err
    assert "generated auth token" in err


def test_resolve_auth_token_fail_on_remote(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="MCP_AUTH_TOKEN"):
        resolve_auth_token(allow_remote=True)


def test_resolve_auth_token_transport_name_in_log(monkeypatch, capsys):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    resolve_auth_token(allow_remote=False, transport_name="my-transport")
    err = capsys.readouterr().err
    assert "[my-transport]" in err


# ---------------------------------------------------------------------------
# build_allowed_hosts
# ---------------------------------------------------------------------------


def test_build_allowed_hosts_loopback_defaults():
    """Binding loopback adds the standard loopback set with and without port."""
    hosts = build_allowed_hosts("127.0.0.1", 8080)
    assert "127.0.0.1" in hosts
    assert "127.0.0.1:8080" in hosts
    assert "localhost" in hosts
    assert "localhost:8080" in hosts
    assert "[::1]" in hosts
    assert "[::1]:8080" in hosts
    # Loopback bind: no extra non-loopback host added.
    assert all(not h.startswith("10.") for h in hosts)


def test_build_allowed_hosts_includes_remote_host():
    """Binding a non-loopback host adds it (with and without port) to the set."""
    hosts = build_allowed_hosts("10.0.0.5", 8080)
    assert "10.0.0.5" in hosts
    assert "10.0.0.5:8080" in hosts
    # Loopback variants are still present (the operator may also reach
    # the server via loopback from the host itself).
    assert "127.0.0.1" in hosts
    assert "localhost:8080" in hosts


def test_build_allowed_hosts_extras_appended():
    """Extra entries (e.g. from MCP_ALLOWED_HOSTS env var) are merged in."""
    hosts = build_allowed_hosts("127.0.0.1", 8080, extra=["mcp.internal", "mcp.internal:8080"])
    assert "mcp.internal" in hosts
    assert "mcp.internal:8080" in hosts


def test_build_allowed_hosts_lowercased():
    """All entries are lowercased (Host header comparison is case-insensitive)."""
    hosts = build_allowed_hosts("MyHost.Example.COM", 443, extra=["UPPER.example.com"])
    assert "myhost.example.com" in hosts
    assert "upper.example.com" in hosts
    # No uppercase entries leak through.
    assert all(h == h.lower() for h in hosts)


def test_build_allowed_hosts_strips_blank_extras():
    """Empty/whitespace entries in extras are dropped."""
    hosts = build_allowed_hosts("127.0.0.1", 8080, extra=["", "   ", "real.example.com"])
    assert "real.example.com" in hosts
    assert "" not in hosts
    assert "   " not in hosts


# ---------------------------------------------------------------------------
# build_allowed_origins
# ---------------------------------------------------------------------------


def test_build_allowed_origins_dual_scheme():
    """Both http:// and https:// origins are allowed for every host."""
    hosts = {"localhost:8080", "mcp.internal"}
    origins = build_allowed_origins(hosts)
    assert "http://localhost:8080" in origins
    assert "https://localhost:8080" in origins
    assert "http://mcp.internal" in origins
    assert "https://mcp.internal" in origins


# ---------------------------------------------------------------------------
# SecurityMiddleware — full ASGI integration
# ---------------------------------------------------------------------------

TOKEN = "test-secret-please-ignore"
ALLOWED_HOSTS = {"testserver", "127.0.0.1", "localhost"}
ALLOWED_ORIGINS = {f"http://{h}" for h in ALLOWED_HOSTS} | {f"https://{h}" for h in ALLOWED_HOSTS}


def _stub_app(token=TOKEN, hosts=ALLOWED_HOSTS, origins=ALLOWED_ORIGINS):
    """A Starlette app that exposes /mcp + /messages/ + /health under SecurityMiddleware."""

    async def mcp_ok(request):
        return PlainTextResponse("mcp-ok")

    async def messages_ok(request):
        return PlainTextResponse("messages-ok")

    async def health(request):
        return PlainTextResponse("OK")

    return Starlette(
        routes=[
            Route("/health", endpoint=health),
            Mount("/mcp", routes=[Route("/", endpoint=mcp_ok)]),
            Mount("/messages/", routes=[Route("/", endpoint=messages_ok)]),
        ],
        middleware=[
            Middleware(
                SecurityMiddleware,
                token=token,
                allowed_hosts=hosts,
                allowed_origins=origins,
            ),
        ],
    )


def _bearer(tok=TOKEN):
    return {"Authorization": f"Bearer {tok}"}


# ----- Bearer token gate -----------------------------------------------------


def test_security_no_authorization_header_returns_401():
    client = TestClient(_stub_app())
    r = client.get("/mcp")
    assert r.status_code == 401


def test_security_wrong_scheme_returns_401():
    client = TestClient(_stub_app())
    r = client.get("/mcp", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert r.status_code == 401


def test_security_wrong_token_returns_401():
    client = TestClient(_stub_app())
    r = client.get("/mcp", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401


def test_security_correct_token_passes_through():
    client = TestClient(_stub_app())
    r = client.get("/mcp", headers=_bearer())
    assert r.status_code == 200
    assert r.text == "mcp-ok"


def test_security_401_includes_www_authenticate_bearer():
    """Standards compliance: 401 must include WWW-Authenticate header."""
    client = TestClient(_stub_app())
    r = client.get("/mcp")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").lower().startswith("bearer")


def test_security_token_constant_time_comparison():
    """Tokens of the same length must each individually fail.

    This is a basic smoke test — actual timing-attack resistance comes from
    hmac.compare_digest. We can't easily assert constant-time behavior in a
    unit test, but we can verify both equal-length and different-length
    wrong tokens are rejected, ruling out length-based shortcuts.
    """
    client = TestClient(_stub_app())
    same_len = "x" * len(TOKEN)
    diff_len = "x"
    for wrong in [same_len, diff_len]:
        r = client.get("/mcp", headers={"Authorization": f"Bearer {wrong}"})
        assert r.status_code == 401, f"wrong token {wrong!r} should 401"


# ----- Host allowlist (DNS-rebinding defense) -------------------------------


def test_security_hostile_host_returns_421():
    """DNS-rebinding defense: a Host header not in the allowlist → 421."""
    client = TestClient(_stub_app())
    r = client.get("/mcp", headers={**_bearer(), "Host": "attacker.example.com"})
    assert r.status_code == 421


def test_security_host_allowlist_case_insensitive():
    """Host comparison is case-insensitive (RFC 9110)."""
    client = TestClient(_stub_app(hosts={"TestServer"}))
    r = client.get("/mcp", headers=_bearer())
    assert r.status_code == 200


# ----- Origin allowlist (CSRF defense) --------------------------------------


def test_security_no_origin_header_passes():
    """Non-browser clients don't send Origin; the gate only fires when present."""
    client = TestClient(_stub_app())
    r = client.get("/mcp", headers=_bearer())
    assert r.status_code == 200


def test_security_hostile_origin_returns_403():
    client = TestClient(_stub_app())
    r = client.get(
        "/mcp",
        headers={**_bearer(), "Origin": "https://attacker.example.com"},
    )
    assert r.status_code == 403


def test_security_allowed_origin_passes():
    client = TestClient(_stub_app())
    r = client.get(
        "/mcp",
        headers={**_bearer(), "Origin": "http://localhost"},
    )
    assert r.status_code == 200


# ----- /health bypass -------------------------------------------------------


def test_security_health_bypasses_bearer():
    """GET /health works without an Authorization header."""
    client = TestClient(_stub_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.text == "OK"


def test_security_health_still_enforces_host_allowlist():
    """DNS-rebinding defense applies even on /health."""
    client = TestClient(_stub_app())
    r = client.get("/health", headers={"Host": "attacker.example.com"})
    assert r.status_code == 421


def test_security_health_still_enforces_origin_allowlist():
    """CSRF defense applies even on /health when Origin is present."""
    client = TestClient(_stub_app())
    r = client.get("/health", headers={"Origin": "https://attacker.example.com"})
    assert r.status_code == 403


def test_security_health_post_does_not_bypass():
    """The bypass is GET-only — POST /health must NOT skip the bearer check."""
    client = TestClient(_stub_app())
    r = client.post("/health")
    # Could be 401 (no token), 405 (no POST handler), or anything else —
    # but it must NOT be a 200 with body "OK".
    assert not (r.status_code == 200 and r.text == "OK")


def test_security_health_returns_no_state():
    """Health probes must return only "OK" — no instance state, no version
    info, nothing useful to an attacker who reaches the endpoint."""
    client = TestClient(_stub_app())
    r = client.get("/health")
    assert r.text == "OK"
    assert len(r.content) == 2


# ----- Pure-ASGI / non-http scope handling ----------------------------------


def test_security_passes_non_http_scope_through_unchecked():
    """The middleware only inspects http scopes — websocket/lifespan must
    pass through untouched. (Phase 7's lifespan asynccontextmanager
    relies on this for StreamableHTTPSessionManager startup.)"""
    middleware = SecurityMiddleware(
        app=_marker_app,
        token=TOKEN,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=ALLOWED_ORIGINS,
    )
    captured = []

    async def fake_send(msg):
        captured.append(msg)

    async def fake_receive():
        return {"type": "lifespan.startup"}

    import asyncio

    asyncio.run(middleware({"type": "lifespan"}, fake_receive, fake_send))
    assert captured == [{"type": "lifespan.startup.complete"}]


async def _marker_app(scope, receive, send):
    """Tiny ASGI app that echoes a lifespan startup completion. Used by
    test_security_passes_non_http_scope_through_unchecked above."""
    if scope["type"] == "lifespan":
        await send({"type": "lifespan.startup.complete"})


# ----- Edge cases -----------------------------------------------------------


def test_security_empty_token_string_constructed_safely():
    """An empty token in the middleware constructor doesn't crash —
    but no client can authenticate against it (constant-time compare
    against empty string fails for any non-empty value)."""
    middleware = SecurityMiddleware(
        app=_marker_app,
        token="",  # Don't do this in production.
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=ALLOWED_ORIGINS,
    )
    assert middleware._token == b""


def test_security_messages_endpoint_also_gated():
    """All non-/health routes go through the bearer gate, not just /mcp."""
    client = TestClient(_stub_app())
    # No bearer
    r = client.post("/messages/")
    assert r.status_code == 401
    # With bearer
    r = client.post("/messages/", headers=_bearer())
    # 200 (ok stub) or 405 (no POST route on the inner mount) — anything but 401
    assert r.status_code != 401

"""Integration tests for the SSE transport security middleware.

These tests wire SecurityMiddleware onto a stub Starlette app and assert
end-to-end behavior via TestClient. A final block tests the real
create_starlette_app to confirm middleware short-circuits before the SSE
handler ever runs (defeats the EntruLabs PoC).
"""

from unittest.mock import MagicMock

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from servicenow_mcp.server_sse import SecurityMiddleware, create_starlette_app

TOKEN = "test-token-abc123"
# TestClient sends `Host: testserver` by default; include it in allowlists.
ALLOWED_HOSTS = {"testserver", "127.0.0.1:8080", "localhost:8080", "[::1]:8080"}
ALLOWED_ORIGINS = {f"http://{h}" for h in ALLOWED_HOSTS} | {f"https://{h}" for h in ALLOWED_HOSTS}


def _build_stub_app(token=TOKEN, hosts=ALLOWED_HOSTS, origins=ALLOWED_ORIGINS):
    """A Starlette app whose routes return 200 — used to test middleware in isolation."""

    async def ok(request):
        return PlainTextResponse("ok")

    async def messages_ok(request):
        return PlainTextResponse("messages-ok")

    async def health(request):
        return PlainTextResponse("OK")

    return Starlette(
        routes=[
            Route("/health", endpoint=health),
            Route("/sse", endpoint=ok),
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


# --- Bearer-token auth -----------------------------------------------------


def test_no_authorization_header_returns_401():
    client = TestClient(_build_stub_app())
    r = client.get("/sse")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_wrong_scheme_returns_401():
    client = TestClient(_build_stub_app())
    r = client.get("/sse", headers={"Authorization": "Basic anything"})
    assert r.status_code == 401


def test_wrong_token_returns_401():
    client = TestClient(_build_stub_app())
    r = client.get("/sse", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_correct_token_passes_through():
    client = TestClient(_build_stub_app())
    r = client.get("/sse", headers=_bearer())
    assert r.status_code == 200
    assert r.text == "ok"


def test_token_with_trailing_char_rejected():
    """compare_digest should reject TOKEN+extra (length mismatch path)."""
    client = TestClient(_build_stub_app())
    r = client.get("/sse", headers={"Authorization": f"Bearer {TOKEN}x"})
    assert r.status_code == 401


def test_messages_endpoint_also_gated():
    client = TestClient(_build_stub_app())
    r = client.post("/messages/", json={})
    assert r.status_code == 401
    r = client.post("/messages/", json={}, headers=_bearer())
    assert r.status_code in (200, 405)  # Mount returns 200; method may differ


# --- Host allowlist --------------------------------------------------------


def test_host_evil_domain_returns_421():
    client = TestClient(_build_stub_app())
    r = client.get("/sse", headers={**_bearer(), "Host": "evil.example"})
    assert r.status_code == 421


def test_host_dns_rebinding_subdomain_shape_returns_421():
    """A DNS-rebinding shaped Host (attacker.com pointing at 127.0.0.1) is rejected."""
    client = TestClient(_build_stub_app())
    r = client.get("/sse", headers={**_bearer(), "Host": "127.0.0.1.evil.example"})
    assert r.status_code == 421


def test_host_loopback_variants_accepted():
    client = TestClient(_build_stub_app())
    for h in ("127.0.0.1:8080", "localhost:8080", "[::1]:8080"):
        r = client.get("/sse", headers={**_bearer(), "Host": h})
        assert r.status_code == 200, f"expected 200 for Host={h}, got {r.status_code}"


def test_host_allowlist_is_case_insensitive():
    client = TestClient(_build_stub_app())
    r = client.get("/sse", headers={**_bearer(), "Host": "LOCALHOST:8080"})
    assert r.status_code == 200


def test_custom_host_allowlist_accepted():
    """Operator-supplied extra host (simulates --allowed-host=mcp.internal:8080)."""
    hosts = ALLOWED_HOSTS | {"mcp.internal:8080"}
    origins = {f"http://{h}" for h in hosts} | {f"https://{h}" for h in hosts}
    client = TestClient(_build_stub_app(hosts=hosts, origins=origins))
    r = client.get("/sse", headers={**_bearer(), "Host": "mcp.internal:8080"})
    assert r.status_code == 200


# --- Origin allowlist ------------------------------------------------------


def test_missing_origin_allowed():
    """curl/CLI clients don't send Origin; that path must keep working."""
    client = TestClient(_build_stub_app())
    r = client.get("/sse", headers=_bearer())
    assert r.status_code == 200


def test_allowed_origin_passes():
    client = TestClient(_build_stub_app())
    r = client.get(
        "/sse", headers={**_bearer(), "Origin": "http://127.0.0.1:8080"}
    )
    assert r.status_code == 200


def test_attacker_origin_returns_403():
    client = TestClient(_build_stub_app())
    r = client.get(
        "/sse", headers={**_bearer(), "Origin": "https://attacker.example"}
    )
    assert r.status_code == 403


def test_null_origin_returns_403():
    """Sandboxed iframe / data: documents send Origin: null. Reject."""
    client = TestClient(_build_stub_app())
    r = client.get("/sse", headers={**_bearer(), "Origin": "null"})
    assert r.status_code == 403


# --- Smoke: real create_starlette_app reproduces PoC mitigation ------------


def test_real_create_starlette_app_blocks_unauthenticated():
    """Reproduces EntruLabs PoC §4.3 Step 1: `curl -N http://.../sse` → 401.

    Uses the real create_starlette_app wired to a mock MCP Server. Middleware
    must fire before connect_sse() is reached, so the mock is never invoked.
    """
    mock_server = MagicMock()
    app = create_starlette_app(
        mock_server,
        auth_token=TOKEN,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=ALLOWED_ORIGINS,
    )
    client = TestClient(app)

    r = client.get("/sse")
    assert r.status_code == 401
    assert mock_server.run.call_count == 0
    assert mock_server.create_initialization_options.call_count == 0

    r = client.post("/messages/?session_id=abc123", json={"jsonrpc": "2.0"})
    assert r.status_code == 401


def test_real_create_starlette_app_no_debug_in_default_call():
    """Ensure no caller can re-introduce debug=True silently."""
    mock_server = MagicMock()
    app = create_starlette_app(
        mock_server,
        auth_token=TOKEN,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=ALLOWED_ORIGINS,
    )
    assert app.debug is False


# ---------------------------------------------------------------------------
# /health endpoint — unauthenticated liveness probe (PR #36 / Phase 6)
# ---------------------------------------------------------------------------


def test_health_endpoint_requires_no_authorization():
    """The /health endpoint must work for platform liveness probes that
    don't carry a bearer token (Cloud Run, K8s liveness probes, ALB
    target-group checks, Docker HEALTHCHECK)."""
    client = TestClient(_build_stub_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.text == "OK"


def test_health_endpoint_still_enforces_host_allowlist():
    """DNS-rebinding defense applies even on /health: an attacker
    pointing a hostile hostname at our process must still be 421'd."""
    client = TestClient(_build_stub_app())
    r = client.get("/health", headers={"host": "attacker.example.com"})
    assert r.status_code == 421


def test_health_endpoint_returns_no_instance_state():
    """Health probes return only "OK" — no instance URL, no tool list,
    no version info that could be useful to an attacker."""
    client = TestClient(_build_stub_app())
    r = client.get("/health")
    assert r.text == "OK"
    # Body is exactly the 2-byte string "OK".
    assert len(r.content) == 2


def test_health_endpoint_post_does_not_bypass_auth():
    """The bypass is GET-only. POST /health must still go through the
    full auth chain so the bypass can't be abused as an unauth-POST
    surface."""
    client = TestClient(_build_stub_app())
    r = client.post("/health")
    # Could be 401 (no token), 405 (no POST handler), or any other
    # error — but it must NOT be a 200 with body "OK" because that
    # would mean we bypassed auth on a POST.
    assert not (r.status_code == 200 and r.text == "OK")

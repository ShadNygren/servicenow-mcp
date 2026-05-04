"""Integration tests for the Streamable HTTP transport (server_http.py).

Verifies the same SecurityMiddleware contract as the SSE tests (bearer
token, Host allowlist, Origin allowlist, /health bypass) is enforced
on the new transport.

The streamable-HTTP session manager itself is exercised by the upstream
mcp library's own tests; we only verify the security perimeter here.
"""

from unittest.mock import MagicMock

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from servicenow_mcp.transport_security import SecurityMiddleware


TOKEN = "test-secret-token-please-ignore"
ALLOWED_HOSTS = {"testserver", "127.0.0.1", "localhost"}
ALLOWED_ORIGINS = {f"http://{h}" for h in ALLOWED_HOSTS} | {f"https://{h}" for h in ALLOWED_HOSTS}


def _build_stub_http_app(token=TOKEN, hosts=ALLOWED_HOSTS, origins=ALLOWED_ORIGINS):
    """A Starlette app that mirrors server_http's route shape for middleware testing."""

    async def mcp_ok(request):
        return PlainTextResponse("mcp-ok")

    async def health(request):
        return PlainTextResponse("OK")

    return Starlette(
        routes=[
            Route("/health", endpoint=health),
            Mount("/mcp", routes=[Route("/", endpoint=mcp_ok)]),
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


def test_streamable_http_no_auth_returns_401():
    client = TestClient(_build_stub_http_app())
    r = client.get("/mcp")
    assert r.status_code == 401


def test_streamable_http_correct_token_passes():
    client = TestClient(_build_stub_http_app())
    r = client.get("/mcp", headers=_bearer())
    assert r.status_code == 200
    assert r.text == "mcp-ok"


def test_streamable_http_wrong_token_returns_401():
    client = TestClient(_build_stub_http_app())
    r = client.get("/mcp", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_streamable_http_hostile_host_returns_421():
    client = TestClient(_build_stub_http_app())
    r = client.get("/mcp", headers={**_bearer(), "Host": "attacker.example.com"})
    assert r.status_code == 421


def test_streamable_http_hostile_origin_returns_403():
    client = TestClient(_build_stub_http_app())
    r = client.get(
        "/mcp",
        headers={**_bearer(), "Origin": "https://attacker.example.com"},
    )
    assert r.status_code == 403


def test_streamable_http_health_bypasses_bearer():
    client = TestClient(_build_stub_http_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.text == "OK"


def test_streamable_http_health_still_enforces_host():
    client = TestClient(_build_stub_http_app())
    r = client.get("/health", headers={"Host": "attacker.example.com"})
    assert r.status_code == 421


def test_create_starlette_app_imports_cleanly():
    """Smoke test: the real create_starlette_app from server_http imports
    and runs without crashing on instantiation."""
    from servicenow_mcp.server_http import create_starlette_app

    mock_server = MagicMock()
    app = create_starlette_app(
        mock_server,
        auth_token=TOKEN,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=ALLOWED_ORIGINS,
    )
    assert app.debug is False
    # Verify the routes are wired correctly.
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/health" in paths
    # Mount paths show up via app.routes too.
    mount_paths = {getattr(r, "path", None) for r in app.routes if hasattr(r, "app")}
    assert "/mcp" in mount_paths

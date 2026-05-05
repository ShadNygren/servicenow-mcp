"""Integration tests for the Streamable HTTP transport (server_http.py).

Verifies the same SecurityMiddleware contract as the SSE tests (bearer
token, Host allowlist, Origin allowlist, /health bypass) is enforced
on the new transport.

The streamable-HTTP session manager itself is exercised by the upstream
mcp library's own tests; we only verify the security perimeter here.
"""

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
    """Smoke test: create_starlette_app builds a Starlette app with /health
    plus a root-mounted FastMCP streamable_http_app (which exposes /mcp)."""
    from mcp.server.fastmcp import FastMCP

    from servicenow_mcp.server_http import create_starlette_app

    mcp = FastMCP("test")
    app = create_starlette_app(
        mcp,
        auth_token=TOKEN,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=ALLOWED_ORIGINS,
    )
    assert app.debug is False
    # /health is a top-level route on the outer app.
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/health" in paths
    # FastMCP's streamable_http_app is mounted at the root; /mcp lives inside it.
    mounts = [r for r in app.routes if hasattr(r, "app")]
    assert any(getattr(r, "path", None) == "" for r in mounts), (
        "Expected the FastMCP streamable_http_app to be mounted at the root."
    )
    inner_paths = {
        getattr(rr, "path", None)
        for r in mounts
        for rr in getattr(getattr(r, "app", None), "routes", [])
    }
    assert "/mcp" in inner_paths


def test_lifespan_closes_shared_async_client_on_shutdown():
    """Phase 9.10 — outer app's lifespan closes the shared httpx.AsyncClient.

    When uvicorn stops, the inner FastMCP lifespan tears down the
    StreamableHTTPSessionManager and our outer wrapper additionally
    calls aclose_async_client() so connection-pooled sockets are
    flushed cleanly instead of being dropped on process exit.
    """
    import anyio
    from mcp.server.fastmcp import FastMCP

    from servicenow_mcp.server_http import create_starlette_app
    from servicenow_mcp.utils import async_http

    async_http.reset_async_client()

    mcp = FastMCP("test")
    app = create_starlette_app(
        mcp,
        auth_token=TOKEN,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=ALLOWED_ORIGINS,
    )

    async def exercise_lifespan():
        # Manually drive the Starlette lifespan protocol.
        scope = {"type": "lifespan"}
        startup_msgs = []
        shutdown_msgs = []

        async def receive():
            if not startup_msgs:
                startup_msgs.append(True)
                return {"type": "lifespan.startup"}
            shutdown_msgs.append(True)
            return {"type": "lifespan.shutdown"}

        sent = []

        async def send(msg):
            sent.append(msg)

        # Create the shared client via direct call — simulates a tool having used it.
        await async_http.get_async_client()
        assert async_http._client is not None  # type: ignore[attr-defined]

        await app(scope, receive, send)
        # After lifespan completes, the shared client should have been closed.
        assert async_http._client is None  # type: ignore[attr-defined]

    anyio.run(exercise_lifespan)

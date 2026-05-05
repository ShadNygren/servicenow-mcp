"""Tests for AuthManager async paths (Phase 9.1)."""

import pytest
import respx

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils import async_http
from servicenow_mcp.utils.config import (
    ApiKeyConfig,
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    OAuthConfig,
)


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    async_http.reset_async_client()
    yield
    async_http.reset_async_client()


# ---------------------------------------------------------------------------
# Basic auth — no I/O; sync and async paths must produce identical headers.
# ---------------------------------------------------------------------------

async def test_get_headers_async_basic_auth_matches_sync() -> None:
    cfg = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(username="alice", password="hunter2"),
    )
    mgr = AuthManager(cfg, instance_url="https://snow.example.com")

    sync_headers = mgr.get_headers()
    async_headers = await mgr.get_headers_async()

    assert sync_headers == async_headers
    assert sync_headers["Authorization"].startswith("Basic ")


async def test_get_headers_async_api_key() -> None:
    cfg = AuthConfig(
        type=AuthType.API_KEY,
        api_key=ApiKeyConfig(api_key="my-api-key", header_name="X-ServiceNow-API-Key"),
    )
    mgr = AuthManager(cfg, instance_url="https://snow.example.com")

    headers = await mgr.get_headers_async()
    assert headers["X-ServiceNow-API-Key"] == "my-api-key"
    assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# OAuth — async path uses httpx.AsyncClient; mocked via respx.
# ---------------------------------------------------------------------------

async def test_get_headers_async_oauth_client_credentials_success() -> None:
    """Happy path: client_credentials grant returns a token."""
    cfg = AuthConfig(
        type=AuthType.OAUTH,
        oauth=OAuthConfig(
            client_id="cid",
            client_secret="csec",
        ),
    )
    mgr = AuthManager(cfg, instance_url="https://snow.example.com")

    async with respx.mock() as mock:
        mock.post("https://snow.example.com/oauth_token.do").respond(
            200,
            json={
                "access_token": "AT-xyz",
                "token_type": "Bearer",
                "expires_in": 1800,
            },
        )
        headers = await mgr.get_headers_async()

    assert headers["Authorization"] == "Bearer AT-xyz"
    assert mgr.token == "AT-xyz"
    assert mgr.token_expiry is not None


async def test_get_headers_async_oauth_password_grant_fallback() -> None:
    """If client_credentials fails (401) but password grant succeeds, use it."""
    cfg = AuthConfig(
        type=AuthType.OAUTH,
        oauth=OAuthConfig(
            client_id="cid",
            client_secret="csec",
            username="alice",
            password="hunter2",
        ),
    )
    mgr = AuthManager(cfg, instance_url="https://snow.example.com")

    async with respx.mock() as mock:
        # Both grants hit the same URL; respx differentiates by sequencing.
        route = mock.post("https://snow.example.com/oauth_token.do")
        route.side_effect = [
            __import__("httpx").Response(401, json={"error": "invalid_client"}),
            __import__("httpx").Response(
                200,
                json={"access_token": "AT-from-password", "expires_in": 1800},
            ),
        ]
        headers = await mgr.get_headers_async()

    assert headers["Authorization"] == "Bearer AT-from-password"


async def test_get_headers_async_oauth_failure_raises() -> None:
    """Both grants fail → ValueError."""
    cfg = AuthConfig(
        type=AuthType.OAUTH,
        oauth=OAuthConfig(client_id="cid", client_secret="csec"),
    )
    mgr = AuthManager(cfg, instance_url="https://snow.example.com")

    async with respx.mock() as mock:
        mock.post("https://snow.example.com/oauth_token.do").respond(
            401, json={"error": "invalid_client"}
        )
        with pytest.raises(ValueError, match="client_credentials"):
            await mgr.get_headers_async()


async def test_get_headers_async_caches_token_until_expiry() -> None:
    """Second call within token lifetime must NOT re-hit the OAuth endpoint."""
    cfg = AuthConfig(
        type=AuthType.OAUTH,
        oauth=OAuthConfig(client_id="cid", client_secret="csec"),
    )
    mgr = AuthManager(cfg, instance_url="https://snow.example.com")

    async with respx.mock() as mock:
        token_route = mock.post("https://snow.example.com/oauth_token.do").respond(
            200,
            json={"access_token": "AT-1", "token_type": "Bearer", "expires_in": 1800},
        )
        await mgr.get_headers_async()
        await mgr.get_headers_async()
        assert token_route.call_count == 1


async def test_get_headers_async_does_not_log_access_token(caplog) -> None:
    """Regression: async OAuth path must not log token bodies (Phase 1.2 / Issue #43)."""
    cfg = AuthConfig(
        type=AuthType.OAUTH,
        oauth=OAuthConfig(client_id="cid", client_secret="csec"),
    )
    mgr = AuthManager(cfg, instance_url="https://snow.example.com")

    async with respx.mock() as mock:
        mock.post("https://snow.example.com/oauth_token.do").respond(
            200,
            json={
                "access_token": "AT-must-not-leak",
                "token_type": "Bearer",
                "expires_in": 1800,
            },
        )
        await mgr.get_headers_async()

    for record in caplog.records:
        assert "AT-must-not-leak" not in record.getMessage()
        assert "access_token" not in record.getMessage().lower() or "Authorization" not in record.getMessage()

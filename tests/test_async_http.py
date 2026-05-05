"""Tests for the shared httpx.AsyncClient infrastructure (Phase 9.1)."""

import asyncio

import httpx
import pytest

from servicenow_mcp.utils import async_http


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Drop the singleton between tests so each test sees a fresh client."""
    async_http.reset_async_client()
    yield
    async_http.reset_async_client()


async def test_get_async_client_returns_async_client_instance() -> None:
    """Sanity check: get_async_client returns an httpx.AsyncClient."""
    client = await async_http.get_async_client()
    assert isinstance(client, httpx.AsyncClient)


async def test_get_async_client_returns_same_instance_on_repeat_calls() -> None:
    """Singleton behaviour — every call returns the same client object."""
    a = await async_http.get_async_client()
    b = await async_http.get_async_client()
    assert a is b


async def test_concurrent_callers_get_the_same_client() -> None:
    """Race-safety: concurrent first-callers don't each create their own client."""

    async def fetch():
        return await async_http.get_async_client()

    results = await asyncio.gather(fetch(), fetch(), fetch(), fetch())
    first = results[0]
    for c in results[1:]:
        assert c is first


async def test_aclose_async_client_idempotent() -> None:
    """Closing twice is a no-op the second time."""
    await async_http.get_async_client()
    await async_http.aclose_async_client()
    # Second close on the now-cleared singleton should be silent.
    await async_http.aclose_async_client()


async def test_reset_then_get_creates_a_fresh_client() -> None:
    """After reset(), the next get returns a different instance."""
    a = await async_http.get_async_client()
    async_http.reset_async_client()
    b = await async_http.get_async_client()
    assert a is not b


async def test_default_timeout_matches_serverconfig() -> None:
    """The 30s default mirrors ServerConfig.timeout default."""
    client = await async_http.get_async_client()
    # Timeout objects compare structurally; just check the connect/read fields.
    assert client.timeout.connect == 30.0
    assert client.timeout.read == 30.0


async def test_default_follows_redirects() -> None:
    """Match prior requests behaviour — auto-follow redirects."""
    client = await async_http.get_async_client()
    assert client.follow_redirects is True


async def test_aclose_closes_the_underlying_client() -> None:
    """After aclose, the previous client is no longer the singleton."""
    a = await async_http.get_async_client()
    await async_http.aclose_async_client()
    b = await async_http.get_async_client()
    assert a is not b

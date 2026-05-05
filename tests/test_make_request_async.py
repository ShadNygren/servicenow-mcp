"""Tests for ``_make_request_async`` (Phase 9.1)."""

from unittest.mock import patch

import httpx
import pytest
import respx

from servicenow_mcp.utils import async_http
from servicenow_mcp.utils.helpers import RateLimitTracker, _make_request_async


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Each test starts with a fresh shared client so respx mocks attach cleanly."""
    async_http.reset_async_client()
    yield
    async_http.reset_async_client()


async def test_make_request_async_returns_response_on_success() -> None:
    """Happy path: 2xx response returned to caller."""
    async with respx.mock(assert_all_called=True) as mock:
        mock.get("https://snow.example.com/api/now/table/incident").respond(
            200, json={"result": []}
        )
        resp = await _make_request_async(
            "GET", "https://snow.example.com/api/now/table/incident"
        )
        assert resp.status_code == 200
        assert resp.json() == {"result": []}


async def test_make_request_async_retries_on_500_and_succeeds() -> None:
    """Retryable 5xx triggers a second attempt; success is returned."""
    async with respx.mock() as mock:
        route = mock.get("https://snow.example.com/api").mock(
            side_effect=[
                httpx.Response(500, json={"error": "server"}),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        with patch("asyncio.sleep") as sleep:  # don't actually sleep in tests
            sleep.return_value = None
            resp = await _make_request_async(
                "GET", "https://snow.example.com/api", max_retries=2, backoff_factor=0
            )
        assert resp.status_code == 200
        assert route.call_count == 2


async def test_make_request_async_returns_4xx_without_retry() -> None:
    """Client errors (404 etc.) are returned immediately — retrying won't help."""
    async with respx.mock() as mock:
        route = mock.get("https://snow.example.com/api").respond(404, json={})
        resp = await _make_request_async(
            "GET", "https://snow.example.com/api", max_retries=3
        )
        assert resp.status_code == 404
        assert route.call_count == 1


async def test_make_request_async_honours_retry_after_header_on_429() -> None:
    """429 with Retry-After should sleep that long before retrying."""
    async with respx.mock() as mock:
        mock.get("https://snow.example.com/api").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "7"}),
                httpx.Response(200),
            ]
        )
        with patch("asyncio.sleep") as sleep:
            sleep.return_value = None
            resp = await _make_request_async(
                "GET", "https://snow.example.com/api", max_retries=1, backoff_factor=0
            )
        assert resp.status_code == 200
        # Last sleep call should be for 7 seconds (the Retry-After value).
        sleep.assert_awaited()
        # Find the 7s call — there may be a tracker throttle call too.
        delays = [c.args[0] for c in sleep.await_args_list]
        assert 7.0 in delays


async def test_make_request_async_passes_kwargs_through() -> None:
    """Verify params, headers, json kwargs reach the underlying client."""
    async with respx.mock() as mock:
        route = mock.post("https://snow.example.com/api/now/table/incident").respond(
            201, json={"result": {"sys_id": "abc"}}
        )
        resp = await _make_request_async(
            "POST",
            "https://snow.example.com/api/now/table/incident",
            json={"short_description": "hi"},
            headers={"X-Test": "yes"},
            params={"sysparm_limit": 1},
        )
        assert resp.status_code == 201
        # Round-trip: respx exposes the captured request.
        captured = route.calls[0].request
        assert captured.method == "POST"
        # Headers are case-insensitive in httpx; check via .get
        assert captured.headers.get("X-Test") == "yes"
        # Body is bytes; decode and check.
        assert b"short_description" in captured.content


async def test_make_request_async_uses_shared_client_singleton() -> None:
    """The async _make_request resolves the shared client lazily."""
    async with respx.mock() as mock:
        mock.get("https://snow.example.com/x").respond(200)
        await _make_request_async("GET", "https://snow.example.com/x")
        # After the call, the shared client exists.
        assert async_http._client is not None  # type: ignore[attr-defined]


async def test_make_request_async_updates_rate_limit_tracker() -> None:
    """The tracker should record X-RateLimit-* headers from the response."""
    tracker = RateLimitTracker()
    async with respx.mock() as mock:
        mock.get("https://snow.example.com/api").respond(
            200,
            headers={
                "X-RateLimit-Remaining": "42",
                "X-RateLimit-Limit": "100",
            },
        )
        await _make_request_async(
            "GET", "https://snow.example.com/api", rate_limit_tracker=tracker
        )
    assert tracker.remaining == 42
    assert tracker.limit == 100

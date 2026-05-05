"""Shared async HTTP client for ServiceNow API calls.

Phase 9.1 — async infrastructure.  Tool functions remain sync until
Phase 9.2+ batches convert them.  This module provides the shared
:class:`httpx.AsyncClient` they will use, with one client per process
so connection pooling and HTTP/2 multiplexing benefit every tool.

Lifecycle:

- The client is created **lazily** on first call to
  :func:`get_async_client`.
- It is closed via :func:`aclose_async_client` (called from
  ``atexit`` for process shutdown; Phase 9.4 will additionally wire it
  into FastMCP's lifespan so it closes cleanly when uvicorn stops).
- Per-test isolation: tests should call :func:`reset_async_client`
  in teardown so each test starts with a fresh client (and so respx
  mocks attach to the right instance).

Configuration:

- 30-second default timeout matches the ``ServerConfig.timeout``
  default; tools may override per-call.
- Connection pool sized for 100 keepalive connections — generous
  enough for any realistic agent workload, modest enough to fit
  inside Cloud Run / Lambda memory budgets.
- Follows redirects by default.  ServiceNow's REST API does not
  redirect under normal use; this matches the prior ``requests``
  behaviour.

Importing this module has zero side effects — the client is not
created until :func:`get_async_client` is awaited.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# Default timeout matches ServerConfig.timeout default.
_DEFAULT_TIMEOUT_SECONDS = 30.0

# Connection-pool tuning.  Generous defaults; tools that need more
# parallelism can pass an explicit client.
_DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 20
_DEFAULT_MAX_CONNECTIONS = 100

# Module-level singleton — protected by an asyncio.Lock to prevent
# two coroutines racing to create the client on first use.
_client: Optional[httpx.AsyncClient] = None
_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    """Lazily create the asyncio.Lock so importing this module is side-effect-free."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def get_async_client() -> httpx.AsyncClient:
    """Return the shared :class:`httpx.AsyncClient`, creating it on first use.

    Subsequent calls return the same instance for the lifetime of the
    process (or until :func:`reset_async_client` is called, typically
    only in tests).
    """
    global _client
    if _client is not None:
        return _client

    async with _get_lock():
        # Re-check inside the lock — another coroutine may have just created it.
        if _client is None:
            limits = httpx.Limits(
                max_keepalive_connections=_DEFAULT_MAX_KEEPALIVE_CONNECTIONS,
                max_connections=_DEFAULT_MAX_CONNECTIONS,
            )
            timeout = httpx.Timeout(_DEFAULT_TIMEOUT_SECONDS)
            _client = httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                follow_redirects=True,
            )
            logger.debug("Created shared httpx.AsyncClient")
        assert _client is not None
        return _client


async def aclose_async_client() -> None:
    """Close the shared client gracefully.  Idempotent."""
    global _client
    if _client is None:
        return
    client = _client
    _client = None
    try:
        await client.aclose()
        logger.debug("Closed shared httpx.AsyncClient")
    except Exception as exc:
        logger.warning("Error closing shared httpx.AsyncClient: %s", exc)


def reset_async_client() -> None:
    """Drop the shared client without closing it.

    Test-only: pytest fixtures use this to reset between tests so
    respx mocks attach to a fresh client instance.  Production code
    should call :func:`aclose_async_client` instead.
    """
    global _client
    _client = None


def _atexit_close() -> None:
    """Close the shared client at interpreter shutdown.

    Wraps :func:`aclose_async_client` in a fresh event loop because
    the original loop is typically closed by the time atexit runs.
    Best-effort — errors here only matter for clean shutdown traces.
    """
    if _client is None:
        return
    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(aclose_async_client())
        finally:
            loop.close()
    except Exception as exc:
        logger.debug("atexit close of httpx.AsyncClient failed: %s", exc)


atexit.register(_atexit_close)

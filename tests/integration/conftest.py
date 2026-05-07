# tests/integration/conftest.py
"""Integration test fixtures for E2E testing against a live ServiceNow PDI.

Original `live_config` / `live_auth` / `pdi_guard` fixtures from
Flowbie's commit 0199475 (Phase 4). Phase E2E.1 added ``run_id``,
``pdi_version``, ``track_record``, and ``cleanup_session`` for tagged
record cleanup and audit-ready test reports.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.async_http import (
    aclose_async_client,
    reset_async_client,
)
from servicenow_mcp.utils.config import (
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    ServerConfig,
)

from . import _cleanup, _report_plugin, _run_id, _version_probe

# Load .env from the project root (servicenow-mcp/)
load_dotenv()

logger = logging.getLogger(__name__)


def _build_config() -> ServerConfig:
    """Build a real ServerConfig from environment variables."""
    instance_url = os.environ.get("SERVICENOW_INSTANCE_URL", "").rstrip("/")
    username = os.environ.get("SERVICENOW_USERNAME", "")
    password = os.environ.get("SERVICENOW_PASSWORD", "")

    if not all([instance_url, username, password]):
        pytest.skip(
            "Integration test requires SERVICENOW_INSTANCE_URL, "
            "SERVICENOW_USERNAME, and SERVICENOW_PASSWORD env vars."
        )

    auth = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(username=username, password=password),
    )
    return ServerConfig(instance_url=instance_url, auth=auth)


@pytest.fixture(scope="session")
def live_config() -> ServerConfig:
    """Real ServerConfig loaded from environment variables."""
    return _build_config()


@pytest.fixture(scope="session")
def live_auth(live_config: ServerConfig) -> AuthManager:
    """Real AuthManager for the live instance."""
    return AuthManager(live_config.auth, instance_url=live_config.instance_url)


@pytest.fixture(scope="session")
def pdi_guard(live_config: ServerConfig) -> ServerConfig:
    """Guard fixture for write tests --- refuses to run against non-PDI URLs.

    Required by any test that creates or modifies records. Skips with a
    clear message when pointed at anything other than a `dev*` PDI.
    """
    url = live_config.instance_url
    if "dev" not in url:
        pytest.skip(
            f"Write integration tests only run against a PDI (dev*.service-now.com). "
            f"Current instance: {url}"
        )
    return live_config


@pytest.fixture(scope="session")
def run_id() -> str:
    """Session-scoped UUID4 used to tag every record this run creates."""
    rid = _run_id.new_run_id()
    _report_plugin.push_run_id(rid)
    logger.info("E2E run_id = %s", rid)
    return rid


@pytest.fixture(scope="session")
def pdi_version(
    live_config: ServerConfig,
    live_auth: AuthManager,
) -> _version_probe.PdiVersionInfo:
    """Probe ServiceNow version + plugin inventory once per session.

    The result is written to the test report header so every E2E run is
    stamped with the exact PDI version --- the user explicitly asked
    for this, since enterprise IT admins and CISOs need to know which
    ServiceNow version was certified by a given test run.

    Implementation note: ``asyncio.run`` creates and tears down its own
    event loop. Our shared httpx.AsyncClient singleton attaches to that
    loop on first use, so when the loop closes the singleton becomes
    unusable. ``reset_async_client()`` clears the stale handle so the
    next async fixture / test gets a fresh client tied to its own loop.
    """
    async def _probe() -> _version_probe.PdiVersionInfo:
        try:
            return await _version_probe.probe(live_config, live_auth)
        finally:
            await aclose_async_client()

    info = asyncio.run(_probe())
    reset_async_client()
    _report_plugin.push_pdi_version(info)
    logger.info("PDI version: %s", info.short())
    return info


# Module-level mutable list of records to clean up. The
# ``track_record`` fixture appends to this; ``cleanup_session`` consumes
# it. Function-scoped fixtures cannot directly close over session-scoped
# state, so we use module state for the registry --- pytest's standard
# pattern.
_TRACKED: list[_cleanup.TrackedRecord] = []


@pytest_asyncio.fixture(autouse=True)
async def _close_async_client_after_each_test():
    """Close + reset the shared httpx singleton after each integration test.

    Each pytest-asyncio test runs in a fresh event loop. The shared
    httpx.AsyncClient + asyncio.Lock get bound to the loop on first
    use. Without this fixture, a second test that calls
    ``get_async_client()`` would inherit a stale singleton bound to the
    previous (now-closed) loop and crash with "Event loop is closed".

    This fixture is async and shares the test's event loop, so it can
    properly aclose the client INSIDE the loop (avoiding the dangling-
    connection-finalisation crash that happens when the client outlives
    the loop it was created on).
    """
    yield
    try:
        await aclose_async_client()
    except Exception:  # noqa: BLE001
        pass
    reset_async_client()


@pytest.fixture
def track_record(run_id: str, request: pytest.FixtureRequest):
    """Returns a function that registers a record for session-end cleanup.

    Usage in a test::

        async def test_foo(live_config, live_auth, pdi_guard, track_record):
            sys_id = ...  # create the record
            track_record("incident", sys_id)
    """
    def _register(table: str, sys_id: str) -> None:
        _TRACKED.append(
            _cleanup.TrackedRecord(
                table=table,
                sys_id=sys_id,
                test_name=request.node.name,
                created_at_iso=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            )
        )
    return _register


@pytest.fixture(scope="session", autouse=True)
def cleanup_session():
    """Session-scoped finalizer that deletes every tracked record.

    Autouse=True so it runs even if no test explicitly requests it.
    Skips silently if no tests created any records (read-only suite).

    Implementation note: this is a sync fixture (not pytest_asyncio) that
    internally runs the async cleanup via ``asyncio.run``. That avoids
    the cross-loop singleton trap pytest-asyncio's per-function event
    loops create when an async session-scoped fixture spans multiple
    per-test loops. After ``asyncio.run`` we reset the shared httpx
    client so any subsequent async fixture/test gets a fresh one.

    Cleanup order:
      1. Delete every record in the tracked list (reverse creation order
         so children are removed before parents).
      2. Run an orphan sweep across each touched table, deleting any
         records still carrying the run-ID marker (defense-in-depth for
         tests that crashed before calling ``track_record``).
      3. Push results to the report plugin.
    """
    # Setup phase: nothing to do; tests register records via track_record.
    yield

    # Teardown phase: only fires once per session.
    if not _TRACKED:
        # No mutating tests ran (e.g., this was a smoke-only session).
        return

    rid = _report_plugin._state.get("run_id") or ""

    async def _do_cleanup() -> tuple[
        _cleanup.CleanupResult,
        _cleanup.CleanupResult | None,
    ]:
        # Build a fresh config + AuthManager inside the async context.
        config = _build_config()
        auth = AuthManager(config.auth, instance_url=config.instance_url)
        try:
            cleanup_res = await _cleanup.cleanup_tracked(config, auth, _TRACKED)
            sweep_res = None
            if rid:
                tables = sorted({r.table for r in _TRACKED})
                sweep_res = await _cleanup.sweep_orphans(
                    config, auth, rid, tables,
                )
            return cleanup_res, sweep_res
        finally:
            await aclose_async_client()

    cleanup_result, sweep_result = asyncio.run(_do_cleanup())
    reset_async_client()

    _report_plugin.push_cleanup_result(cleanup_result, sweep=False)
    if sweep_result is not None:
        _report_plugin.push_cleanup_result(sweep_result, sweep=True)

    # Push tracked records into the report state for the appendix.
    for r in _TRACKED:
        _report_plugin.push_tracked_record(r)

    # Clear the registry so a subsequent test session starts fresh.
    _TRACKED.clear()

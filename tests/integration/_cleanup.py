"""Session-scoped cleanup of all records created during an E2E run.

Implementation contract:

- Every test that mutates the PDI calls the ``track_record`` fixture
  with the table name and sys_id of each record it creates.
- The session-scoped ``cleanup_session`` finalizer iterates through the
  tracked records in REVERSE creation order (so children are deleted
  before parents) and calls DELETE for each.
- After the registered-record cleanup, a defense-in-depth sweep queries
  each touched table for records still carrying the run-ID marker
  prefix and deletes any orphans (which would only happen if a test
  crashed before calling ``track_record``).
- Cleanup failures are logged but do not raise --- the test report
  surfaces them, and the user can clean up manually using the run-ID.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.async_http import get_async_client
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


@dataclass
class TrackedRecord:
    """One record created by a test, registered for cleanup."""

    table: str
    sys_id: str
    test_name: str
    created_at_iso: str  # for forensics if cleanup is partial


@dataclass
class CleanupResult:
    """Aggregate results of a cleanup pass --- written to the report."""

    tracked_count: int = 0
    deleted_count: int = 0
    orphan_swept_count: int = 0
    failures: list[str] = field(default_factory=list)  # "{table}:{sys_id} -> error"


async def delete_one(
    config: ServerConfig,
    auth: AuthManager,
    table: str,
    sys_id: str,
) -> tuple[bool, str]:
    """Delete a single record. Returns (success, error_message_or_empty)."""
    try:
        client = await get_async_client()
        headers = await auth.get_headers_async()
        r = await client.delete(
            f"{config.instance_url}/api/now/table/{table}/{sys_id}",
            headers=headers,
            timeout=config.timeout,
        )
        if r.status_code in (200, 204):
            return True, ""
        # 404 => already gone (treat as success for idempotency)
        if r.status_code == 404:
            return True, ""
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except httpx.HTTPError as e:
        return False, f"{type(e).__name__}: {e}"


async def cleanup_tracked(
    config: ServerConfig,
    auth: AuthManager,
    tracked: list[TrackedRecord],
) -> CleanupResult:
    """Bulk-delete every tracked record. Reverse order to handle FKs."""
    result = CleanupResult(tracked_count=len(tracked))
    for record in reversed(tracked):
        ok, err = await delete_one(config, auth, record.table, record.sys_id)
        if ok:
            result.deleted_count += 1
        else:
            result.failures.append(
                f"{record.table}:{record.sys_id} ({record.test_name}) -> {err}"
            )
    return result


async def sweep_orphans(
    config: ServerConfig,
    auth: AuthManager,
    run_id: str,
    tables: list[str],
) -> CleanupResult:
    """Defense-in-depth: query each table for records still carrying the
    run-ID and delete any that the per-test cleanup missed."""
    result = CleanupResult()
    client = await get_async_client()
    headers = await auth.get_headers_async()

    for table in tables:
        try:
            r = await client.get(
                f"{config.instance_url}/api/now/table/{table}",
                params={
                    "sysparm_query": (
                        f"descriptionLIKE{run_id}"
                        f"^ORshort_descriptionLIKE{run_id}"
                        f"^ORcommentsLIKE{run_id}"
                    ),
                    "sysparm_fields": "sys_id",
                    "sysparm_limit": "200",
                },
                headers=headers,
                timeout=config.timeout,
            )
            if r.status_code != 200:
                continue
            for row in r.json().get("result", []):
                sys_id = row.get("sys_id")
                if not sys_id:
                    continue
                ok, err = await delete_one(config, auth, table, sys_id)
                if ok:
                    result.orphan_swept_count += 1
                else:
                    result.failures.append(
                        f"orphan {table}:{sys_id} (run_id={run_id}) -> {err}"
                    )
        except httpx.HTTPError as e:
            # Some tables don't support description-style queries; skip silently.
            logger.debug("orphan sweep skipped for %s: %s", table, e)
            continue

    return result

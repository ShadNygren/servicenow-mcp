"""Phase E2E.5 edge cases against the live PDI.

These tests exercise non-happy-path scenarios that enterprise IT admins
and CISOs care about: auth boundaries, concurrency under load,
malformed input, pagination edges, large bodies, reference-field
expansion, filter behavior, and tool-package security gates.

Tests deliberately omitted from this tier:

- Network failure injection: requires respx-style mocking of the live
  client; doesn't fit with real-PDI integration testing.
- Rate-limit handling: PDIs don't reliably trigger rate limits under
  normal load; would need a test-only proxy. Covered in the unit test
  suite via ``test_rate_limiting.py``.
- Read-back race timing: flaky against a real instance; the
  foundation test already proves the standard create→read pattern.
- ACL deactivation tests: would require destructive PDI changes.

Coverage gaps above are documented for E2E.5+ follow-up phases.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.incident_tools import (
    CreateIncidentParams,
    GetIncidentByNumberParams,
    ListIncidentsParams,
    create_incident,
    get_incident_by_number,
    list_incidents,
)
from servicenow_mcp.utils.config import (
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    ServerConfig,
)

from . import _run_id

# 1. Auth boundary: invalid password → 401 ==========================


@pytest.mark.integration
async def test_edge_invalid_password_returns_401(
    live_config: ServerConfig,
) -> None:
    """An incorrect password should produce an auth failure --- not a
    silent success or a generic 500. Verifies that ServiceNow's auth
    layer rejects bad credentials and our pipeline surfaces the failure
    cleanly.

    Uses a fresh AuthManager with a deliberately-wrong password rather
    than mutating the live_auth fixture (which other tests share).
    """
    bad_auth_config = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(
            username=os.environ.get("SERVICENOW_USERNAME", "admin"),
            password="this-is-deliberately-the-wrong-password-12345",
        ),
    )
    bad_auth = AuthManager(bad_auth_config, instance_url=live_config.instance_url)

    r = await list_incidents(live_config, bad_auth, ListIncidentsParams(limit=1))
    # The tool should return success=False with a 401 indication, not
    # crash and not return success=True.
    assert isinstance(r, dict), f"unexpected return type: {type(r)}"
    assert r.get("success") is False, (
        f"bad password should return success=False; got {r}"
    )
    msg = (r.get("message") or "").lower()
    assert "401" in msg or "unauthorized" in msg, (
        f"expected 401/unauthorized in error; got: {msg[:200]!r}"
    )


# 2. Concurrency: 10 simultaneous list calls ========================


@pytest.mark.integration
async def test_edge_concurrent_list_incidents_no_corruption(
    live_config: ServerConfig,
    live_auth: AuthManager,
) -> None:
    """Issue 10 parallel list_incidents calls via asyncio.gather.

    Verifies the Phase 9 concurrency invariant: many concurrent calls
    on the shared httpx.AsyncClient + the OAuth lock should all
    succeed without cross-contamination, deadlock, or duplicate-token-
    fetch issues. For basic auth there's no OAuth lock involvement,
    but the connection pool still gets exercised under load.
    """
    tasks = [
        list_incidents(live_config, live_auth, ListIncidentsParams(limit=1))
        for _ in range(10)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # All ten should be dicts with success=True. None should be exceptions.
    for i, r in enumerate(results):
        assert not isinstance(r, BaseException), (
            f"task {i} raised: {type(r).__name__}: {r}"
        )
        assert isinstance(r, dict), f"task {i} returned non-dict: {type(r)}"
        assert r.get("success") is True, (
            f"task {i} success=False: {r.get('message')}"
        )


# 3. Malformed input: empty required field ==========================


@pytest.mark.integration
async def test_edge_create_with_empty_short_description(
    live_config: ServerConfig,
    live_auth: AuthManager,
    pdi_guard,  # noqa: ARG001
    track_record,
) -> None:
    """``short_description`` is required by ServiceNow's incident table.

    An empty string is technically a valid Python string but
    ServiceNow may either reject it (preferred) or accept it and
    create an unusable incident. Either way is acceptable; what's NOT
    acceptable is a server-side crash or an unhandled exception in
    our tool layer. This test verifies graceful handling.
    """
    r = await create_incident(
        live_config, live_auth,
        CreateIncidentParams(short_description=""),
    )
    # We accept either:
    #   (a) ServiceNow accepted the create with empty short_description
    #       (their table-level validation may permit it; the SLA team
    #        is the ones who care about the field being meaningful)
    #   (b) ServiceNow rejected with 400, our tool returns success=False
    if r.success:
        # Track for cleanup --- it's a real record, however empty.
        if r.incident_id:
            track_record("incident", r.incident_id)
    else:
        # If rejected, the message should be informative, not a stack trace
        msg = (r.message or "").lower()
        informative_tokens = ("400", "required", "mandatory", "short_description")
        assert any(token in msg for token in informative_tokens), (
            f"rejection message should be informative; got: {msg[:200]!r}"
        )


# 4. Pagination edge: offset way past end ===========================


@pytest.mark.integration
async def test_edge_pagination_offset_beyond_total(
    live_config: ServerConfig,
    live_auth: AuthManager,
) -> None:
    """list_incidents at offset=999999 should return an empty page,
    not error. has_more should be False. This is the boundary the
    'Next page' button hits when scrolling past the end.
    """
    r = await list_incidents(
        live_config, live_auth,
        ListIncidentsParams(limit=10, offset=999999),
    )
    assert r.get("success") is True, f"list at huge offset failed: {r}"
    incidents = r.get("incidents", [])
    assert len(incidents) == 0, (
        f"expected empty page at offset=999999; got {len(incidents)} incidents"
    )
    # has_more=False is the documented pagination contract
    assert r.get("has_more") is False, (
        f"has_more should be False past the end; got {r.get('has_more')!r}"
    )


# 5. Large body roundtrip ===========================================


@pytest.mark.integration
async def test_edge_large_description_roundtrip(
    live_config: ServerConfig,
    live_auth: AuthManager,
    pdi_guard,  # noqa: ARG001
    run_id: str,
    track_record,
) -> None:
    """Create an incident with a 5000-character description, read it back,
    verify the body survived intact end-to-end. ServiceNow's description
    field is a "string" type with practically unlimited length; we
    verify our tool layer doesn't silently truncate or corrupt it.
    """
    test_name = "test_edge_large_description"
    marker = _run_id.tag(run_id, test_name)
    # Build a deterministic 5000-char body that's easy to verify
    big_body = (
        f"{marker}\n\n"
        + ("ServiceNowDocs reference E2E test. " * 140)  # ~5000 chars
    )
    assert len(big_body) >= 4500

    create_resp = await create_incident(
        live_config, live_auth,
        CreateIncidentParams(
            short_description=f"E2E large body test ({marker[:40]})",
            description=big_body,
            urgency="3", impact="3",
        ),
    )
    assert create_resp.success, f"create failed: {create_resp.message}"
    track_record("incident", create_resp.incident_id)

    read_resp = await get_incident_by_number(
        live_config, live_auth,
        GetIncidentByNumberParams(incident_number=create_resp.incident_number),
    )
    assert read_resp["success"], f"read failed: {read_resp}"
    fetched_desc = read_resp["incident"].get("description") or ""
    # ServiceNow may normalize whitespace (trailing newlines, etc.)
    # but the marker prefix and the bulk of the body should be intact
    assert _run_id.is_test_record(fetched_desc, run_id), (
        f"marker missing from fetched description; first 200 chars: "
        f"{fetched_desc[:200]!r}"
    )
    # Confirm a substantial fraction of the body roundtripped
    assert len(fetched_desc) >= 4000, (
        f"description appears truncated; sent {len(big_body)}, got {len(fetched_desc)}"
    )


# 6. Reference field expansion ======================================


@pytest.mark.integration
async def test_edge_reference_field_expansion_via_get(
    live_config: ServerConfig,
    live_auth: AuthManager,
) -> None:
    """get_incident_by_number requests sysparm_display_value=true.
    Reference fields like assigned_to should come back as the display
    name (a user's full name) rather than the raw sys_id, OR as a
    structured dict containing both. Verifies our tool layer correctly
    consumes ServiceNow's display_value mode.

    Picks up the first existing incident on the PDI (read-only test).
    """
    list_resp = await list_incidents(
        live_config, live_auth, ListIncidentsParams(limit=1),
    )
    assert list_resp.get("success"), f"list failed: {list_resp}"
    incidents = list_resp.get("incidents", [])
    if not incidents:
        pytest.skip("no incidents on this PDI to test reference expansion")
    inc = incidents[0]
    number = inc.get("number")
    assert number, f"no incident number in list response: {inc}"

    get_resp = await get_incident_by_number(
        live_config, live_auth,
        GetIncidentByNumberParams(incident_number=number),
    )
    assert get_resp["success"], f"get failed: {get_resp}"
    fetched = get_resp["incident"]

    # The shape of assigned_to: either a string (already display value),
    # a dict with display_value, or empty if unassigned. NOT a 32-char
    # sys_id hex string when display_value=true is set.
    assigned = fetched.get("assigned_to")
    if assigned and isinstance(assigned, str):
        # If it's a string, it should be the human-readable name, not
        # a 32-char sys_id hex
        is_sys_id = len(assigned) == 32 and all(
            c in "0123456789abcdef" for c in assigned
        )
        assert not is_sys_id, (
            f"assigned_to leaked as sys_id (sysparm_display_value not "
            f"applied?); value: {assigned!r}"
        )


# 7. List filter with no matches ====================================


@pytest.mark.integration
async def test_edge_list_filter_yields_empty_for_no_matches(
    live_config: ServerConfig,
    live_auth: AuthManager,
) -> None:
    """Filtering by a state value that no incident has should return
    an empty list, not error. ``state="999"`` is not a real
    ServiceNow incident state.
    """
    r = await list_incidents(
        live_config, live_auth,
        ListIncidentsParams(state="999", limit=10),
    )
    # ServiceNow accepts the filter even for nonsense values; just
    # returns no results. Our tool should pass that through.
    assert r.get("success") is True, f"filter call failed: {r}"
    incidents = r.get("incidents", [])
    assert len(incidents) == 0, (
        f"expected empty result for state=999; got {len(incidents)}"
    )
    assert r.get("has_more") is False, (
        f"has_more should be False for empty result; got {r.get('has_more')!r}"
    )


# 8. Tool-package security gate (in-process; no PDI call needed) ====


@pytest.mark.integration
def test_edge_tool_package_filter_excludes_script_execution() -> None:
    """The default packages must NOT include the arbitrary-script-
    execution tools (Issue #43 finding #1 mitigation). A future
    regression that re-adds them to defaults would silently expose an
    RCE sink to LLM agents.

    This test inspects the YAML config directly --- a config-level
    invariant that should always hold regardless of PDI state.
    """
    from importlib.resources import files

    import yaml

    config_text = files("servicenow_mcp").joinpath(
        "config/tool_packages.yaml"
    ).read_text()
    packages = yaml.safe_load(config_text)

    forbidden_in_defaults = {
        "execute_script_include",
        "create_script_include",
        "update_script_include",
        "delete_script_include",
    }

    default_packages = (
        "service_desk", "catalog_builder", "change_coordinator",
        "knowledge_author", "platform_developer", "agile_management",
    )

    for pkg in default_packages:
        if pkg not in packages:
            continue
        members = set(packages[pkg] or [])
        leaked = forbidden_in_defaults & members
        assert not leaked, (
            f"package {pkg!r} includes forbidden script-execution "
            f"tools: {sorted(leaked)} (Issue #43 finding #1 regression!)"
        )

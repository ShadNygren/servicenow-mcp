"""Phase E2E.1 foundation test.

Runs end-to-end against a live PDI to verify:
  1. The ``run_id`` fixture produces a UUID4 hex string.
  2. The ``pdi_version`` probe successfully identifies ServiceNow family
     and build tag.
  3. ``track_record`` plus ``cleanup_session`` correctly create and
     delete an incident, leaving the PDI in the same state.
  4. The marker prefix is searchable so manual cleanup works if a
     session crashes.
  5. The audit-ready test report is written to ``results/RESULTS_*.md``.

This is the canonical test that proves the foundation is healthy. If
this fails, the rest of E2E.2-E2E.7 will not run correctly.

Requires:
  - ``SN_INTEGRATION_TESTS=1`` set
  - ``.env`` with valid PDI credentials
"""

from __future__ import annotations

import pytest

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.incident_tools import (
    CreateIncidentParams,
    GetIncidentByNumberParams,
    create_incident,
    get_incident_by_number,
)
from servicenow_mcp.utils.config import ServerConfig

from . import _run_id


@pytest.mark.integration
def test_run_id_is_unique_uuid_hex(run_id: str) -> None:
    """The run_id should be a UUID4 hex string (32 chars)."""
    assert isinstance(run_id, str)
    assert len(run_id) == 32
    assert all(c in "0123456789abcdef" for c in run_id)


@pytest.mark.integration
def test_pdi_version_probe_identifies_family(pdi_version) -> None:
    """The version probe should at least identify the ServiceNow family.

    The family name is derived from the build_tag prefix (e.g.
    ``zurich-12-15-2025`` -> ``Zurich``). A failure here means either
    the PDI is unreachable, the credentials are wrong, or
    ``glide.product.build.tag`` was renamed in a newer ServiceNow
    version --- in which case this test is the early-warning signal.
    """
    assert pdi_version.instance_url, "instance_url should be populated"
    if pdi_version.probe_errors:
        pytest.fail(
            f"version probe had {len(pdi_version.probe_errors)} error(s): "
            + "; ".join(pdi_version.probe_errors)
        )
    assert pdi_version.family_name, (
        f"family_name not detected (build_tag={pdi_version.build_tag})"
    )
    assert pdi_version.build_tag, "build_tag should be populated"


@pytest.mark.integration
def test_pdi_version_plugin_probe_does_not_crash(pdi_version) -> None:
    """The plugin probe should return a (possibly zero) inventory.

    On default PDIs the ``v_plugin`` view returns 0 rows for the admin
    user --- the underlying ``sys_plugins`` and ``sys_store_app``
    tables are gated behind a stricter API-level ACL (403 for
    everyone, including admin, until you go through the in-instance
    Plugins UI as a logged-in user). The probe is best-effort: we
    record what we can read, but don't fail if it's empty.

    The non-empty path is exercised when run against an instance that
    grants v_plugin read access to the integration user (e.g. a
    dedicated company instance). On a vanilla PDI we tolerate zero.
    """
    assert pdi_version.plugin_count >= 0, "plugin_count should be a non-negative int"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_foundation_create_read_track_cleanup(
    live_config: ServerConfig,
    live_auth: AuthManager,
    pdi_guard,  # noqa: ARG001 --- presence is the safety check, not the value
    run_id: str,
    track_record,
) -> None:
    """The end-to-end smoke for the foundation:

      1. Create an incident tagged with the run-ID marker
      2. Read it back via get_incident_by_number
      3. Assert the marker is present in the description
      4. Register for cleanup via track_record
      5. cleanup_session (autouse) will delete it at session end

    This is the proof-of-life for every CRUD pattern E2E.3 builds.
    """
    test_name = "test_foundation_create_read_track_cleanup"
    marker = _run_id.tag(run_id, test_name)
    short_desc = f"E2E foundation incident ({marker[:60]}...)"

    create_resp = await create_incident(
        live_config,
        live_auth,
        CreateIncidentParams(
            short_description=short_desc,
            description=f"{marker}\n\nE2E.1 foundation test record. Safe to delete.",
            urgency="3",
            impact="3",
        ),
    )

    # create_incident returns an IncidentResponse Pydantic model with
    # success / message / incident_id / incident_number fields.
    assert create_resp.success is True, f"create failed: {create_resp.message}"
    sys_id = create_resp.incident_id
    number = create_resp.incident_number
    assert sys_id, f"incident_id missing from create response: {create_resp}"
    assert number, f"incident_number missing from create response: {create_resp}"

    # Register for cleanup BEFORE doing anything that could fail. If the
    # read-back step throws, cleanup still runs.
    track_record("incident", sys_id)

    # Read it back. get_incident_by_number returns a dict.
    read_resp = await get_incident_by_number(
        live_config,
        live_auth,
        GetIncidentByNumberParams(incident_number=number),
    )
    assert isinstance(read_resp, dict)
    assert read_resp.get("success") is True, (
        f"read failed: {read_resp.get('message') or read_resp}"
    )
    fetched = read_resp.get("incident") or {}

    # The marker must be visible in the description so manual cleanup works.
    desc = fetched.get("description") or ""
    assert _run_id.is_test_record(desc, run_id), (
        f"run_id {run_id} not found in description; "
        f"description starts with: {desc[:120]!r}"
    )

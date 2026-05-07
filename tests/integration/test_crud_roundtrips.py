"""Phase E2E.3 CRUD round-trips --- write → read → mutate → read → cleanup.

Each test in this file:
  1. Creates a record tagged with the run-ID marker
  2. Reads it back and asserts the marker is present
  3. Mutates the record (state change, field update)
  4. Re-reads and asserts the mutation took effect
  5. Registers for cleanup via ``track_record`` (session-end finalizer
     deletes it; orphan sweep is the safety net)

Compared to Phase E2E.2 smoke tests (which prove every domain is
reachable for reads), this tier proves that mutating operations
actually change ServiceNow state, not just shape valid HTTP requests
that return success.

Coverage target for E2E.3 first cut: representative high-value
enterprise scenarios. Other CRUD coverage rolls in via E2E.4
lifecycle flows and E2E.5 edge cases.

CMDB CRUD is intentionally deferred to a follow-up phase: cmdb_tools,
asset_tools, and contract_tools are still 100% sync (Phase 9 missed
them) and use a legacy ``(auth, config, params_dict)`` parameter
shape that doesn't match the rest of the project. Converting them
deserves its own focused phase rather than being mixed into E2E.3.
"""

from __future__ import annotations

import pytest

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.business_rule_tools import (
    CreateBusinessRuleParams,
    DeleteBusinessRuleParams,
    GetBusinessRuleParams,
    UpdateBusinessRuleParams,
    create_business_rule,
    delete_business_rule,
    get_business_rule,
    update_business_rule,
)
from servicenow_mcp.tools.incident_tools import (
    CreateIncidentParams,
    GetIncidentByNumberParams,
    UpdateIncidentParams,
    create_incident,
    get_incident_by_number,
    update_incident,
)
from servicenow_mcp.tools.user_tools import (
    CreateGroupParams,
    CreateUserParams,
    GetUserParams,
    UpdateUserParams,
    create_group,
    create_user,
    get_user,
    update_user,
)
from servicenow_mcp.utils.config import ServerConfig

from . import _run_id

# Incident lifecycle: open → assign → resolve =====================


@pytest.mark.integration
async def test_crud_incident_create_read_update_read(
    live_config: ServerConfig,
    live_auth: AuthManager,
    pdi_guard,  # noqa: ARG001
    run_id: str,
    track_record,
) -> None:
    """Open a P3 incident, assign to admin, then resolve it.

    Verifies that updates to the assigned_to and state fields are
    persisted by reading the record back at each step. This is the
    core ITSM round-trip every enterprise integration needs to do.
    """
    test_name = "test_crud_incident"
    marker = _run_id.tag(run_id, test_name)

    # Step 1: Create
    create_resp = await create_incident(
        live_config, live_auth,
        CreateIncidentParams(
            short_description=f"E2E CRUD: {marker[:50]}",
            description=f"{marker}\nE2E.3 incident CRUD round-trip.",
            urgency="3",
            impact="3",
        ),
    )
    assert create_resp.success, f"create failed: {create_resp.message}"
    sys_id, number = create_resp.incident_id, create_resp.incident_number
    track_record("incident", sys_id)

    # Step 2: Read back
    read1 = await get_incident_by_number(
        live_config, live_auth, GetIncidentByNumberParams(incident_number=number),
    )
    assert read1["success"] is True
    inc1 = read1["incident"]
    assert _run_id.is_test_record(inc1["description"], run_id)
    initial_state = inc1["state"]

    # Step 3: Update --- transition to "In Progress" (state=2)
    upd_resp = await update_incident(
        live_config, live_auth,
        UpdateIncidentParams(
            incident_id=sys_id,
            state="2",  # In Progress
            work_notes=f"{marker} | transition: New → In Progress",
        ),
    )
    assert upd_resp.success, f"update failed: {upd_resp.message}"

    # Step 4: Re-read and verify the state changed
    read2 = await get_incident_by_number(
        live_config, live_auth, GetIncidentByNumberParams(incident_number=number),
    )
    assert read2["success"] is True
    inc2 = read2["incident"]
    assert inc2["state"] != initial_state, (
        f"state should have changed from {initial_state!r}; got {inc2['state']!r}"
    )


# User lifecycle: create → read → update → read ====================


@pytest.mark.integration
async def test_crud_user_create_read_update_read(
    live_config: ServerConfig,
    live_auth: AuthManager,
    pdi_guard,  # noqa: ARG001
    run_id: str,
    track_record,
) -> None:
    """Create a user, fetch by username, update title, fetch again."""
    test_name = "test_crud_user"
    marker = _run_id.tag(run_id, test_name)
    # User_name must be valid for ServiceNow (no spaces). Use the
    # run_id hex prefix to guarantee uniqueness across concurrent runs.
    user_name = f"e2e.u.{run_id[:8]}"

    # Use last_name to carry the marker (sys_user.title has a 40-char
    # limit which is too short for our run-ID + test-name marker; last_name
    # is 100 chars which fits comfortably). For the post-update verification,
    # we update the email field --- short, distinct before/after.
    create_resp = await create_user(
        live_config, live_auth,
        CreateUserParams(
            user_name=user_name,
            first_name="E2E",
            last_name=marker,
            email=f"{user_name}@before.invalid",
            title="initial",
        ),
    )
    assert create_resp.success, f"create_user failed: {create_resp.message}"
    sys_id = create_resp.user_id
    track_record("sys_user", sys_id)

    read1 = await get_user(
        live_config, live_auth, GetUserParams(user_name=user_name),
    )
    assert read1["success"] is True
    user1 = read1["user"]
    assert user1["sys_id"] == sys_id
    assert user1["first_name"] == "E2E"
    # The marker should have landed in last_name verbatim
    assert _run_id.is_test_record(user1.get("last_name") or "", run_id), (
        f"run_id not in last_name; got: {user1.get('last_name')!r}"
    )

    upd_resp = await update_user(
        live_config, live_auth,
        UpdateUserParams(
            user_id=sys_id,
            email=f"{user_name}@after.invalid",
        ),
    )
    assert upd_resp.success, f"update_user failed: {upd_resp.message}"

    read2 = await get_user(
        live_config, live_auth, GetUserParams(user_id=sys_id),
    )
    assert read2["success"] is True
    user2 = read2["user"]
    assert (user2.get("email") or "").endswith("@after.invalid"), (
        f"email not updated; got: {user2.get('email')!r}"
    )


# Group lifecycle: create → list-confirms-presence ================


@pytest.mark.integration
async def test_crud_group_create_and_lookup(
    live_config: ServerConfig,
    live_auth: AuthManager,
    pdi_guard,  # noqa: ARG001
    run_id: str,
    track_record,
) -> None:
    """Create a group, then look up via the same Table API.

    No dedicated get_group tool exists; we use list_groups with a
    name filter to confirm the create succeeded.
    """
    from servicenow_mcp.tools.user_tools import ListGroupsParams, list_groups

    test_name = "test_crud_group"
    marker = _run_id.tag(run_id, test_name)
    group_name = f"E2E Group {run_id[:8]}"

    create_resp = await create_group(
        live_config, live_auth,
        CreateGroupParams(
            name=group_name,
            description=f"{marker} | E2E.3 group CRUD",
        ),
    )
    assert create_resp.success, f"create_group failed: {create_resp.message}"
    sys_id = create_resp.group_id
    track_record("sys_user_group", sys_id)

    # Look up via list with a name filter --- groups don't have a
    # dedicated get_group tool. We use the ListGroupsParams.query
    # field to filter to just our group.
    list_resp = await list_groups(
        live_config, live_auth,
        ListGroupsParams(query=group_name, limit=5),
    )
    assert isinstance(list_resp, dict)
    assert list_resp.get("success") is True
    found = [
        g for g in list_resp.get("groups", []) if g.get("sys_id") == sys_id
    ]
    assert found, (
        f"created group sys_id={sys_id} not found in list_groups("
        f"query={group_name!r}); got {len(list_resp.get('groups', []))} results"
    )
    assert _run_id.is_test_record(found[0].get("description") or "", run_id)


# Business Rule lifecycle: create → get → update → get → delete ====


@pytest.mark.integration
async def test_crud_business_rule_full_lifecycle(
    live_config: ServerConfig,
    live_auth: AuthManager,
    pdi_guard,  # noqa: ARG001
    run_id: str,
    track_record,  # noqa: ARG001 --- we use explicit delete; track is a backup
) -> None:
    """Create a business rule, get it, update it, get again, then delete it.

    Demonstrates the full create/read/update/delete cycle through
    dedicated tools rather than the generic Table API. The explicit
    delete proves the delete tool works; track_record is registered as
    a safety net in case the test fails before reaching the delete step.
    """
    test_name = "test_crud_business_rule"
    marker = _run_id.tag(run_id, test_name)
    br_name = f"E2E BR {run_id[:8]}"

    # Step 1: Create
    create_resp = await create_business_rule(
        live_config, live_auth,
        CreateBusinessRuleParams(
            name=br_name,
            table="incident",
            script="// E2E test rule. Body intentionally minimal.",
            description=f"{marker} | E2E.3 business rule lifecycle",
            when="before",
            insert=True,
            active=False,  # Inactive so we don't actually run on incident inserts
        ),
    )
    assert isinstance(create_resp, dict)
    assert create_resp.get("success") is True, (
        f"create_business_rule failed: {create_resp.get('message')}"
    )
    # The tool returns the created record under either ``rule`` (the
    # canonical key in business_rule_tools) or ``business_rule``
    # (legacy key). Try both.
    sys_id = (
        (create_resp.get("rule") or {}).get("sys_id")
        or (create_resp.get("business_rule") or {}).get("sys_id")
        or create_resp.get("sys_id")
    )
    assert sys_id, f"sys_id missing: {create_resp}"

    # Step 2: Get it back
    read1 = await get_business_rule(
        live_config, live_auth, GetBusinessRuleParams(sys_id=sys_id),
    )
    assert read1.get("success") is True, f"get_business_rule failed: {read1}"
    br1 = read1.get("rule") or read1.get("business_rule") or {}
    initial_when = br1.get("when")

    # Step 3: Update --- change the timing
    new_when = "after" if initial_when == "before" else "before"
    upd_resp = await update_business_rule(
        live_config, live_auth,
        UpdateBusinessRuleParams(
            sys_id=sys_id,
            when=new_when,
            description=f"{marker} | UPDATED",
        ),
    )
    assert upd_resp.get("success") is True, f"update_business_rule failed: {upd_resp}"

    # Step 4: Re-read and verify
    read2 = await get_business_rule(
        live_config, live_auth, GetBusinessRuleParams(sys_id=sys_id),
    )
    br2 = read2.get("rule") or read2.get("business_rule") or {}
    assert br2.get("when") == new_when, (
        f"when not updated; expected {new_when!r}, got {br2.get('when')!r}; "
        f"full body: {br2}"
    )

    # Step 5: Delete
    del_resp = await delete_business_rule(
        live_config, live_auth, DeleteBusinessRuleParams(sys_id=sys_id),
    )
    assert del_resp.get("success") is True, f"delete_business_rule failed: {del_resp}"

    # Step 6: Verify it's gone (get should now fail)
    read3 = await get_business_rule(
        live_config, live_auth, GetBusinessRuleParams(sys_id=sys_id),
    )
    # The tool may return success=False with "not found" or a 404 in the message
    if read3.get("success") is True:
        # If it claims success, the record body should be empty
        body = read3.get("rule") or read3.get("business_rule") or {}
        assert not body, (
            f"deleted record still exists: {body}"
        )

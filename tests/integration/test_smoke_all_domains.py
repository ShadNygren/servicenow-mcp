"""Phase E2E.2 smoke tests --- one read per ServiceNow domain.

For each major ServiceNow domain we exercise, we call exactly one
list/get tool with limit=1 against the live PDI. The intent is
breadth, not depth: this tier proves every major surface area is
reachable through our tool pipeline. CRUD round-trips are
in :mod:`tests.integration.test_crud_*` (Phase E2E.3); lifecycle
flows are in :mod:`tests.integration.test_lifecycle_*` (E2E.4).

All tests in this file are pure read operations --- no writes --- so
``pdi_guard`` is not required. They run against any reachable instance
that gives the integration user read access to the relevant tables.

Tools that depend on a plugin or table that may be inactive on a
default PDI (CSM, Agile, PPM, time_card, sys_log) skip with a clear
reason rather than fail when the table returns 400/404.
"""

from __future__ import annotations

import asyncio
import inspect
import re

import pytest

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig

# Tables that ship inactive on a default PDI. When a tool hits one of
# these and gets a 400/404, we skip the test with a clear reason
# rather than fail (the tool is correct; the plugin just isn't on).
_PLUGIN_GATED_TABLES = {
    "rm_story": "Agile Development 2.0",
    "rm_epic": "Agile Development 2.0",
    "rm_scrum_task": "Agile Development 2.0",
    "rm_sprint": "Agile Development 2.0",
    "pm_project": "Project Portfolio Management",
    "customer_account": "Customer Service Management",
    "sn_customerservice_case": "Customer Service Management",
    "sn_customerservice_account": "Customer Service Management",
    "csm_location": "Customer Service Management",
    "product_catalog_item": "Customer Service Management",
    "time_card": "Time Card Management",
    "sys_log": "syslog (admin-only on PDI)",
    "alm_contract": "Asset Management Contracts (alm_contract not on default Zurich PDI)",
}


def _success(result) -> bool:
    if hasattr(result, "success"):
        return bool(result.success)
    if isinstance(result, dict):
        return bool(result.get("success", True))
    return True


def _message(result) -> str:
    if hasattr(result, "message"):
        return str(result.message)
    if isinstance(result, dict):
        return str(result.get("message", ""))
    return ""


def _maybe_skip_for_plugin(result) -> None:
    """Skip the test if the result is a plugin-gated table 400/404.

    Recognises two error-message shapes:
      1. ``Client error '400 Bad Request' for url '.../api/now/table/<name>?...'``
      2. ``HTTP 400: Invalid table <name>``
    """
    msg = _message(result)
    if not msg:
        return
    if "400" not in msg and "404" not in msg and "Not Found" not in msg:
        return
    table: str | None = None
    m = re.search(r"/api/now/table/([a-z_0-9]+)", msg)
    if m:
        table = m.group(1)
    else:
        m = re.search(r"Invalid table\s+([a-z_0-9]+)", msg)
        if m:
            table = m.group(1)
    if table is None:
        return
    plugin = _PLUGIN_GATED_TABLES.get(table)
    if plugin:
        pytest.skip(f"{plugin} not active on this PDI ({table} returned 400/404)")


async def _call_tool(impl, *args):
    """Call a tool function, awaiting it if it's a coroutine.

    Three tool files (cmdb_tools, asset_tools, contract_tools) are still
    sync as of v0.9.11 --- Phase 9's async refactor missed them. They
    work fine via FastMCP's threadpool dispatch when invoked through the
    MCP transport, but pytest-asyncio tests calling them directly need
    ``asyncio.to_thread`` to avoid ``TypeError: object dict can't be
    used in 'await' expression``. This helper transparently handles
    both shapes so tests don't need to know which is which.

    See the Phase E2E.2 PR description for the gap analysis (3 files,
    ~12 tools still sync --- convert in a separate follow-up phase).
    """
    if inspect.iscoroutinefunction(impl):
        return await impl(*args)
    return await asyncio.to_thread(impl, *args)


def _check(result, label: str) -> None:
    """Standard assert-or-skip for a smoke test result."""
    _maybe_skip_for_plugin(result)
    assert _success(result), f"{label} failed: {_message(result)[:300]}"


# ITSM =============================================================


@pytest.mark.integration
async def test_smoke_list_incidents(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.incident_tools import (
        ListIncidentsParams,
        list_incidents,
    )
    r = await _call_tool(
        list_incidents, live_config, live_auth, ListIncidentsParams(limit=1),
    )
    _check(r, "list_incidents")


@pytest.mark.integration
async def test_smoke_list_change_requests(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.change_tools import (
        ListChangeRequestsParams,
        list_change_requests,
    )
    r = await _call_tool(
        list_change_requests, live_config, live_auth,
        ListChangeRequestsParams(limit=1),
    )
    _check(r, "list_change_requests")


@pytest.mark.integration
async def test_smoke_list_sctasks(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.sctask_tools import ListSCTasksParams, list_sctasks
    r = await _call_tool(
        list_sctasks, live_config, live_auth, ListSCTasksParams(limit=1),
    )
    _check(r, "list_sctasks")


@pytest.mark.integration
async def test_smoke_list_time_cards(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.time_card_tools import (
        ListTimeCardsParams,
        list_time_cards,
    )
    r = await _call_tool(
        list_time_cards, live_config, live_auth, ListTimeCardsParams(limit=1),
    )
    _check(r, "list_time_cards")


@pytest.mark.integration
async def test_smoke_list_articles(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.knowledge_base import (
        ListArticlesParams,
        list_articles,
    )
    r = await _call_tool(
        list_articles, live_config, live_auth, ListArticlesParams(limit=1),
    )
    _check(r, "list_articles")


@pytest.mark.integration
async def test_smoke_list_knowledge_bases(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.knowledge_base import (
        ListKnowledgeBasesParams,
        list_knowledge_bases,
    )
    r = await _call_tool(
        list_knowledge_bases, live_config, live_auth,
        ListKnowledgeBasesParams(limit=1),
    )
    _check(r, "list_knowledge_bases")


# Catalog ==========================================================


@pytest.mark.integration
async def test_smoke_list_catalog_items(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.catalog_tools import (
        ListCatalogItemsParams,
        list_catalog_items,
    )
    r = await _call_tool(
        list_catalog_items, live_config, live_auth,
        ListCatalogItemsParams(limit=1),
    )
    _check(r, "list_catalog_items")


@pytest.mark.integration
async def test_smoke_list_catalog_categories(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.catalog_tools import (
        ListCatalogCategoriesParams,
        list_catalog_categories,
    )
    r = await _call_tool(
        list_catalog_categories, live_config, live_auth,
        ListCatalogCategoriesParams(limit=1),
    )
    _check(r, "list_catalog_categories")


# CMDB / Asset (cmdb_tools, asset_tools, contract_tools — still sync) =====


@pytest.mark.integration
async def test_smoke_list_cis(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.cmdb_tools import ListCIsParams, list_cis
    r = await _call_tool(
        list_cis, live_config, live_auth, ListCIsParams(limit=1),
    )
    _check(r, "list_cis")


@pytest.mark.integration
async def test_smoke_list_assets(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.asset_tools import ListAssetsParams, list_assets
    r = await _call_tool(
        list_assets, live_config, live_auth, ListAssetsParams(limit=1),
    )
    _check(r, "list_assets")


@pytest.mark.integration
async def test_smoke_list_asset_contracts(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.contract_tools import (
        ListAssetContractsParams,
        list_asset_contracts,
    )
    r = await _call_tool(
        list_asset_contracts, live_config, live_auth,
        ListAssetContractsParams(limit=1),
    )
    _check(r, "list_asset_contracts")


# User / Group / Auth ==============================================


@pytest.mark.integration
async def test_smoke_list_users(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.user_tools import ListUsersParams, list_users
    r = await _call_tool(
        list_users, live_config, live_auth, ListUsersParams(limit=1),
    )
    _check(r, "list_users")


@pytest.mark.integration
async def test_smoke_list_groups(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.user_tools import ListGroupsParams, list_groups
    r = await _call_tool(
        list_groups, live_config, live_auth, ListGroupsParams(limit=1),
    )
    _check(r, "list_groups")


@pytest.mark.integration
async def test_smoke_list_roles(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.acl_tools import ListRolesParams, list_roles
    r = await _call_tool(
        list_roles, live_config, live_auth, ListRolesParams(limit=1),
    )
    _check(r, "list_roles")


@pytest.mark.integration
async def test_smoke_list_acls(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.acl_tools import ListACLsParams, list_acls
    r = await _call_tool(
        list_acls, live_config, live_auth, ListACLsParams(limit=1),
    )
    _check(r, "list_acls")


# Workflow / Flow Designer =========================================


@pytest.mark.integration
async def test_smoke_list_workflows(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.workflow_tools import (
        ListWorkflowsParams,
        list_workflows,
    )
    r = await _call_tool(
        list_workflows, live_config, live_auth, ListWorkflowsParams(limit=1),
    )
    _check(r, "list_workflows")


@pytest.mark.integration
async def test_smoke_list_flows(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.flow_tools import ListFlowsParams, list_flows
    r = await _call_tool(
        list_flows, live_config, live_auth, ListFlowsParams(limit=1),
    )
    _check(r, "list_flows")


@pytest.mark.integration
async def test_smoke_list_subflows(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.flow_tools import ListSubflowsParams, list_subflows
    r = await _call_tool(
        list_subflows, live_config, live_auth, ListSubflowsParams(limit=1),
    )
    _check(r, "list_subflows")


@pytest.mark.integration
async def test_smoke_list_actions(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.flow_tools import ListActionsParams, list_actions
    r = await _call_tool(
        list_actions, live_config, live_auth, ListActionsParams(limit=1),
    )
    _check(r, "list_actions")


# Platform / Admin =================================================


@pytest.mark.integration
async def test_smoke_list_business_rules(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.business_rule_tools import (
        ListBusinessRulesParams,
        list_business_rules,
    )
    r = await _call_tool(
        list_business_rules, live_config, live_auth,
        ListBusinessRulesParams(limit=1),
    )
    _check(r, "list_business_rules")


@pytest.mark.integration
async def test_smoke_list_scheduled_jobs(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.scheduled_job_tools import (
        ListScheduledJobsParams,
        list_scheduled_jobs,
    )
    r = await _call_tool(
        list_scheduled_jobs, live_config, live_auth,
        ListScheduledJobsParams(limit=1),
    )
    _check(r, "list_scheduled_jobs")


@pytest.mark.integration
async def test_smoke_list_script_includes(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.script_include_tools import (
        ListScriptIncludesParams,
        list_script_includes,
    )
    r = await _call_tool(
        list_script_includes, live_config, live_auth,
        ListScriptIncludesParams(limit=1),
    )
    _check(r, "list_script_includes")


@pytest.mark.integration
async def test_smoke_list_oauth_entities(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.oauth_tools import (
        ListOAuthEntitiesParams,
        list_oauth_entities,
    )
    r = await _call_tool(
        list_oauth_entities, live_config, live_auth,
        ListOAuthEntitiesParams(limit=1),
    )
    _check(r, "list_oauth_entities")


@pytest.mark.integration
async def test_smoke_list_rest_messages(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.rest_message_tools import (
        ListRestMessagesParams,
        list_rest_messages,
    )
    r = await _call_tool(
        list_rest_messages, live_config, live_auth,
        ListRestMessagesParams(limit=1),
    )
    _check(r, "list_rest_messages")


# Schema / Generic =================================================


@pytest.mark.integration
async def test_smoke_table_get_records_sys_user(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    """Generic Table API read --- proves the universal /api/now/table/{name} path."""
    from servicenow_mcp.tools.table_api_tools import (
        TableGetRecordsParams,
        table_get_records,
    )
    r = await _call_tool(
        table_get_records, live_config, live_auth,
        TableGetRecordsParams(table="sys_user", limit=1),
    )
    _check(r, "table_get_records")


@pytest.mark.integration
async def test_smoke_list_fields_for_incident(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.sys_dictionary_tools import (
        ListFieldsParams,
        list_fields,
    )
    r = await _call_tool(
        list_fields, live_config, live_auth,
        ListFieldsParams(table_name="incident"),
    )
    _check(r, "list_fields")


@pytest.mark.integration
async def test_smoke_list_syslog_entries(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.syslog_tools import (
        ListSyslogEntriesParams,
        list_syslog_entries,
    )
    r = await _call_tool(
        list_syslog_entries, live_config, live_auth,
        ListSyslogEntriesParams(limit=1),
    )
    _check(r, "list_syslog_entries")


# Agile / SDLC (skips when plugin not active) ======================


@pytest.mark.integration
async def test_smoke_list_stories(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.story_tools import ListStoriesParams, list_stories
    r = await _call_tool(
        list_stories, live_config, live_auth, ListStoriesParams(limit=1),
    )
    _check(r, "list_stories")


@pytest.mark.integration
async def test_smoke_list_epics(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.epic_tools import ListEpicsParams, list_epics
    r = await _call_tool(
        list_epics, live_config, live_auth, ListEpicsParams(limit=1),
    )
    _check(r, "list_epics")


@pytest.mark.integration
async def test_smoke_list_projects(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.project_tools import (
        ListProjectsParams,
        list_projects,
    )
    r = await _call_tool(
        list_projects, live_config, live_auth, ListProjectsParams(limit=1),
    )
    _check(r, "list_projects")


@pytest.mark.integration
async def test_smoke_list_scrum_tasks(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.scrum_task_tools import (
        ListScrumTasksParams,
        list_scrum_tasks,
    )
    r = await _call_tool(
        list_scrum_tasks, live_config, live_auth,
        ListScrumTasksParams(limit=1),
    )
    _check(r, "list_scrum_tasks")


# CSM (skips when plugin not active) ===============================


@pytest.mark.integration
async def test_smoke_list_cases(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.case_tools import ListCasesParams, list_cases
    r = await _call_tool(
        list_cases, live_config, live_auth, ListCasesParams(limit=1),
    )
    _check(r, "list_cases")


@pytest.mark.integration
async def test_smoke_list_accounts(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.csm_tools import ListAccountsParams, list_accounts
    r = await _call_tool(
        list_accounts, live_config, live_auth, ListAccountsParams(limit=1),
    )
    _check(r, "list_accounts")


# Data Integration =================================================


@pytest.mark.integration
async def test_smoke_list_import_sets(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.import_set_tools import (
        ListImportSetsParams,
        list_import_sets,
    )
    r = await _call_tool(
        list_import_sets, live_config, live_auth,
        ListImportSetsParams(limit=1),
    )
    _check(r, "list_import_sets")


@pytest.mark.integration
async def test_smoke_list_changesets(
    live_config: ServerConfig, live_auth: AuthManager
) -> None:
    from servicenow_mcp.tools.changeset_tools import (
        ListChangesetsParams,
        list_changesets,
    )
    r = await _call_tool(
        list_changesets, live_config, live_auth,
        ListChangesetsParams(limit=1),
    )
    _check(r, "list_changesets")

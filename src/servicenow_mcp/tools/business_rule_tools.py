"""
Business Rule tools for the ServiceNow MCP server.

Provides tools to create, list, update, and delete Business Rules (sys_script)
in ServiceNow. Business Rules execute server-side logic on record operations.
"""

import logging
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter models
# ---------------------------------------------------------------------------


class CreateBusinessRuleParams(BaseModel):
    """Parameters for creating a new Business Rule."""

    name: str = Field(..., description="Name of the business rule")
    table: str = Field(
        ..., description="Table the rule applies to, e.g. 'cmdb_ci', 'incident'"
    )
    script: str = Field(
        ...,
        description="Server-side JavaScript that executes when the rule fires",
    )
    when: str = Field(
        "after",
        description="When the rule fires: 'before', 'after', 'async', 'display'",
    )
    insert: bool = Field(False, description="Fire on insert (create)")
    update: bool = Field(False, description="Fire on update")
    delete: bool = Field(False, description="Fire on delete")
    query: bool = Field(False, description="Fire on query")
    filter_condition: Optional[str] = Field(
        None,
        description="Encoded query condition that must be true for the rule to fire, e.g. 'priority=1'",
    )
    order: int = Field(
        100, description="Execution order (lower = earlier). Default 100."
    )
    active: bool = Field(True, description="Whether the rule is active")
    description: Optional[str] = Field(
        None, description="Description of what the rule does"
    )


class ListBusinessRulesParams(BaseModel):
    """Parameters for listing Business Rules."""

    table: Optional[str] = Field(
        None, description="Filter by table name, e.g. 'cmdb_ci'"
    )
    name_filter: Optional[str] = Field(
        None, description="Filter by name (contains)"
    )
    active_only: bool = Field(
        True, description="Only return active rules (default: true)"
    )
    query: Optional[str] = Field(
        None, description="Additional encoded query string"
    )
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")


class GetBusinessRuleParams(BaseModel):
    """Parameters for getting a single Business Rule."""

    sys_id: str = Field(..., description="sys_id of the business rule")


class UpdateBusinessRuleParams(BaseModel):
    """Parameters for updating an existing Business Rule."""

    sys_id: str = Field(..., description="sys_id of the business rule to update")
    name: Optional[str] = Field(None, description="New name")
    script: Optional[str] = Field(None, description="New script")
    when: Optional[str] = Field(None, description="New timing: 'before', 'after', 'async', 'display'")
    insert: Optional[bool] = Field(None, description="Fire on insert")
    update: Optional[bool] = Field(None, description="Fire on update")
    delete: Optional[bool] = Field(None, description="Fire on delete")
    query: Optional[bool] = Field(None, description="Fire on query")
    filter_condition: Optional[str] = Field(None, description="New filter condition")
    order: Optional[int] = Field(None, description="New execution order")
    active: Optional[bool] = Field(None, description="Set active flag")
    description: Optional[str] = Field(None, description="New description")


class DeleteBusinessRuleParams(BaseModel):
    """Parameters for deleting a Business Rule."""

    sys_id: str = Field(..., description="sys_id of the business rule to delete")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def create_business_rule(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateBusinessRuleParams,
) -> Dict[str, Any]:
    """Create a new Business Rule in ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sys_script"

    data: Dict[str, Any] = {
        "name": params.name,
        "collection": params.table,
        "script": params.script,
        "when": params.when,
        "action_insert": str(params.insert).lower(),
        "action_update": str(params.update).lower(),
        "action_delete": str(params.delete).lower(),
        "action_query": str(params.query).lower(),
        "order": str(params.order),
        "active": str(params.active).lower(),
    }

    if params.filter_condition:
        data["filter_condition"] = params.filter_condition
    if params.description:
        data["comments"] = params.description

    try:
        response = requests.post(
            url,
            headers=auth_manager.get_headers(),
            json=data,
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Created business rule '{params.name}' on table '{params.table}'",
            "sys_id": result.get("sys_id"),
            "name": params.name,
            "table": params.table,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to create business rule '{params.name}': {e}")
        return {
            "success": False,
            "message": f"Failed to create business rule: {str(e)}",
            "sys_id": None,
            "name": params.name,
            "table": params.table,
            "record": {},
        }


def list_business_rules(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListBusinessRulesParams,
) -> Dict[str, Any]:
    """List Business Rules from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sys_script"

    query_parts: List[str] = []
    if params.table:
        query_parts.append(f"collection={params.table}")
    if params.name_filter:
        query_parts.append(f"nameLIKE{params.name_filter}")
    if params.active_only:
        query_parts.append("active=true")
    if params.query:
        query_parts.append(params.query)

    query_params = {
        "sysparm_query": "^".join(query_parts) if query_parts else "",
        "sysparm_fields": "sys_id,name,collection,when,action_insert,action_update,action_delete,action_query,order,active,filter_condition,sys_updated_on",
        "sysparm_limit": str(params.limit),
        "sysparm_offset": str(params.offset),
    }

    try:
        response = requests.get(
            url,
            headers=auth_manager.get_headers(),
            params=query_params,
            timeout=config.timeout,
        )
        response.raise_for_status()
        records = response.json().get("result", [])
        rules = []
        for r in records:
            rules.append({
                "sys_id": r.get("sys_id"),
                "name": r.get("name"),
                "table": r.get("collection"),
                "when": r.get("when"),
                "insert": r.get("action_insert"),
                "update": r.get("action_update"),
                "delete": r.get("action_delete"),
                "query": r.get("action_query"),
                "order": r.get("order"),
                "active": r.get("active"),
                "filter_condition": r.get("filter_condition"),
                "updated_on": r.get("sys_updated_on"),
            })
        return {
            "success": True,
            "message": f"Found {len(rules)} business rules",
            "count": len(rules),
            "rules": rules,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to list business rules: {e}")
        return {
            "success": False,
            "message": f"Failed to list business rules: {str(e)}",
            "count": 0,
            "rules": [],
        }


def get_business_rule(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetBusinessRuleParams,
) -> Dict[str, Any]:
    """Get a single Business Rule with full details including script."""
    url = f"{config.instance_url}/api/now/table/sys_script/{params.sys_id}"

    try:
        response = requests.get(
            url,
            headers=auth_manager.get_headers(),
            params={"sysparm_display_value": "false"},
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Retrieved business rule '{result.get('name', params.sys_id)}'",
            "rule": {
                "sys_id": result.get("sys_id"),
                "name": result.get("name"),
                "table": result.get("collection"),
                "script": result.get("script"),
                "when": result.get("when"),
                "insert": result.get("action_insert"),
                "update": result.get("action_update"),
                "delete": result.get("action_delete"),
                "query": result.get("action_query"),
                "order": result.get("order"),
                "active": result.get("active"),
                "filter_condition": result.get("filter_condition"),
                "description": result.get("comments"),
                "updated_on": result.get("sys_updated_on"),
            },
        }
    except requests.RequestException as e:
        logger.error(f"Failed to get business rule {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to get business rule: {str(e)}",
            "rule": {},
        }


def update_business_rule(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateBusinessRuleParams,
) -> Dict[str, Any]:
    """Update an existing Business Rule."""
    url = f"{config.instance_url}/api/now/table/sys_script/{params.sys_id}"

    data: Dict[str, Any] = {}
    if params.name is not None:
        data["name"] = params.name
    if params.script is not None:
        data["script"] = params.script
    if params.when is not None:
        data["when"] = params.when
    if params.insert is not None:
        data["action_insert"] = str(params.insert).lower()
    if params.update is not None:
        data["action_update"] = str(params.update).lower()
    if params.delete is not None:
        data["action_delete"] = str(params.delete).lower()
    if params.query is not None:
        data["action_query"] = str(params.query).lower()
    if params.filter_condition is not None:
        data["filter_condition"] = params.filter_condition
    if params.order is not None:
        data["order"] = str(params.order)
    if params.active is not None:
        data["active"] = str(params.active).lower()
    if params.description is not None:
        data["comments"] = params.description

    if not data:
        return {
            "success": False,
            "message": "No fields to update.",
            "sys_id": params.sys_id,
            "record": {},
        }

    try:
        response = requests.patch(
            url,
            headers=auth_manager.get_headers(),
            json=data,
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Updated business rule {params.sys_id}",
            "sys_id": params.sys_id,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to update business rule {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to update business rule: {str(e)}",
            "sys_id": params.sys_id,
            "record": {},
        }


def delete_business_rule(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: DeleteBusinessRuleParams,
) -> Dict[str, Any]:
    """Delete a Business Rule from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sys_script/{params.sys_id}"

    try:
        response = requests.delete(
            url,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Deleted business rule {params.sys_id}",
            "sys_id": params.sys_id,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to delete business rule {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to delete business rule: {str(e)}",
            "sys_id": params.sys_id,
        }

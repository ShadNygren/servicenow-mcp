"""
Generic Table API tools for the ServiceNow MCP server.

Provides generic CRUD operations on any ServiceNow table via the Table API.
This enables flexible access to tables that don't have dedicated tool modules
(e.g. sys_properties, sys_ui_section, or any custom table).
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


class TableGetRecordsParams(BaseModel):
    """Parameters for retrieving multiple records from any SN table."""

    table: str = Field(..., description="ServiceNow table name, e.g. 'incident', 'cmdb_ci', 'sys_properties'")
    query: Optional[str] = Field(
        None,
        description="Encoded query string, e.g. 'active=true^priority=1'. Uses ServiceNow query syntax.",
    )
    fields: Optional[str] = Field(
        None,
        description="Comma-separated list of fields to return, e.g. 'sys_id,name,number'. If omitted, all fields are returned.",
    )
    limit: int = Field(20, description="Maximum number of records to return (default 20)")
    offset: int = Field(0, description="Offset for pagination")
    order_by: Optional[str] = Field(
        None,
        description="Field to sort by. Prefix with '-' for descending, e.g. '-sys_created_on'.",
    )
    display_value: Optional[str] = Field(
        "false",
        description="Return display values: 'true', 'false', or 'all' (both value and display_value).",
    )


class TableGetRecordParams(BaseModel):
    """Parameters for retrieving a single record by sys_id."""

    table: str = Field(..., description="ServiceNow table name")
    sys_id: str = Field(..., description="sys_id of the record to retrieve")
    fields: Optional[str] = Field(
        None,
        description="Comma-separated list of fields to return. If omitted, all fields are returned.",
    )
    display_value: Optional[str] = Field(
        "false",
        description="Return display values: 'true', 'false', or 'all'.",
    )


class TableCreateRecordParams(BaseModel):
    """Parameters for creating a new record on any SN table."""

    table: str = Field(..., description="ServiceNow table name to create the record in")
    data: Dict[str, Any] = Field(
        ...,
        description="Field-value pairs for the new record, e.g. {'name': 'My CI', 'serial_number': 'SN123'}",
    )
    fields: Optional[str] = Field(
        None,
        description="Comma-separated list of fields to return in the response.",
    )


class TableUpdateRecordParams(BaseModel):
    """Parameters for updating an existing record (PATCH)."""

    table: str = Field(..., description="ServiceNow table name")
    sys_id: str = Field(..., description="sys_id of the record to update")
    data: Dict[str, Any] = Field(
        ...,
        description="Field-value pairs to update (delta — only changed fields needed).",
    )
    fields: Optional[str] = Field(
        None,
        description="Comma-separated list of fields to return in the response.",
    )


class TableDeleteRecordParams(BaseModel):
    """Parameters for deleting a record."""

    table: str = Field(..., description="ServiceNow table name")
    sys_id: str = Field(..., description="sys_id of the record to delete")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _build_params(
    fields: Optional[str] = None,
    query: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    order_by: Optional[str] = None,
    display_value: Optional[str] = None,
) -> Dict[str, str]:
    """Build query parameter dict for the SN Table API."""
    params: Dict[str, str] = {}
    if query:
        params["sysparm_query"] = query
    if fields:
        params["sysparm_fields"] = fields
    if limit is not None:
        params["sysparm_limit"] = str(limit)
    if offset:
        params["sysparm_offset"] = str(offset)
    if order_by:
        if order_by.startswith("-"):
            params["sysparm_query"] = (
                (params.get("sysparm_query", "") + "^" if params.get("sysparm_query") else "")
                + f"ORDERBY{order_by[1:]}"
            )
        else:
            params["sysparm_query"] = (
                (params.get("sysparm_query", "") + "^" if params.get("sysparm_query") else "")
                + f"ORDERBY{order_by}"
            )
    if display_value:
        params["sysparm_display_value"] = display_value
    return params


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def table_get_records(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: TableGetRecordsParams,
) -> Dict[str, Any]:
    """
    Retrieve multiple records from any ServiceNow table.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Query parameters.

    Returns:
        Dict with success flag, message, and list of records.
    """
    url = f"{config.instance_url}/api/now/table/{params.table}"
    query_params = _build_params(
        fields=params.fields,
        query=params.query,
        limit=params.limit,
        offset=params.offset,
        order_by=params.order_by,
        display_value=params.display_value,
    )

    try:
        response = requests.get(
            url,
            headers=auth_manager.get_headers(),
            params=query_params,
            timeout=config.timeout,
        )
        response.raise_for_status()
        records = response.json().get("result", [])
        return {
            "success": True,
            "message": f"Retrieved {len(records)} records from {params.table}",
            "table": params.table,
            "count": len(records),
            "records": records,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to get records from {params.table}: {e}")
        return {
            "success": False,
            "message": f"Failed to get records from {params.table}: {str(e)}",
            "table": params.table,
            "count": 0,
            "records": [],
        }


def table_get_record(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: TableGetRecordParams,
) -> Dict[str, Any]:
    """
    Retrieve a single record by sys_id from any ServiceNow table.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Record identifier parameters.

    Returns:
        Dict with success flag, message, and the record.
    """
    url = f"{config.instance_url}/api/now/table/{params.table}/{params.sys_id}"
    query_params = _build_params(
        fields=params.fields,
        display_value=params.display_value,
    )

    try:
        response = requests.get(
            url,
            headers=auth_manager.get_headers(),
            params=query_params,
            timeout=config.timeout,
        )
        response.raise_for_status()
        record = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Retrieved record {params.sys_id} from {params.table}",
            "table": params.table,
            "record": record,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to get record {params.sys_id} from {params.table}: {e}")
        return {
            "success": False,
            "message": f"Failed to get record from {params.table}: {str(e)}",
            "table": params.table,
            "record": {},
        }


def table_create_record(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: TableCreateRecordParams,
) -> Dict[str, Any]:
    """
    Create a new record on any ServiceNow table.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Table name and field data.

    Returns:
        Dict with success flag, message, and the created record.
    """
    url = f"{config.instance_url}/api/now/table/{params.table}"
    query_params = _build_params(fields=params.fields)

    try:
        response = requests.post(
            url,
            headers=auth_manager.get_headers(),
            json=params.data,
            params=query_params,
            timeout=config.timeout,
        )
        response.raise_for_status()
        record = response.json().get("result", {})
        sys_id = record.get("sys_id", "unknown")
        return {
            "success": True,
            "message": f"Created record {sys_id} in {params.table}",
            "table": params.table,
            "sys_id": sys_id,
            "record": record,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to create record in {params.table}: {e}")
        return {
            "success": False,
            "message": f"Failed to create record in {params.table}: {str(e)}",
            "table": params.table,
            "sys_id": None,
            "record": {},
        }


def table_update_record(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: TableUpdateRecordParams,
) -> Dict[str, Any]:
    """
    Update an existing record on any ServiceNow table (PATCH — delta only).

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Table name, sys_id, and changed fields.

    Returns:
        Dict with success flag, message, and the updated record.
    """
    url = f"{config.instance_url}/api/now/table/{params.table}/{params.sys_id}"
    query_params = _build_params(fields=params.fields)

    try:
        response = requests.patch(
            url,
            headers=auth_manager.get_headers(),
            json=params.data,
            params=query_params,
            timeout=config.timeout,
        )
        response.raise_for_status()
        record = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Updated record {params.sys_id} in {params.table}",
            "table": params.table,
            "sys_id": params.sys_id,
            "record": record,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to update record {params.sys_id} in {params.table}: {e}")
        return {
            "success": False,
            "message": f"Failed to update record in {params.table}: {str(e)}",
            "table": params.table,
            "sys_id": params.sys_id,
            "record": {},
        }


def table_delete_record(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: TableDeleteRecordParams,
) -> Dict[str, Any]:
    """
    Delete a record from any ServiceNow table.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Table name and sys_id.

    Returns:
        Dict with success flag and message.
    """
    url = f"{config.instance_url}/api/now/table/{params.table}/{params.sys_id}"

    try:
        response = requests.delete(
            url,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Deleted record {params.sys_id} from {params.table}",
            "table": params.table,
            "sys_id": params.sys_id,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to delete record {params.sys_id} from {params.table}: {e}")
        return {
            "success": False,
            "message": f"Failed to delete record from {params.table}: {str(e)}",
            "table": params.table,
            "sys_id": params.sys_id,
        }

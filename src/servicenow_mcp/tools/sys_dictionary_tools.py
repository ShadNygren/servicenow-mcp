"""
System Dictionary tools for the ServiceNow MCP server.

Provides tools to create, list, and update custom fields (columns) on
ServiceNow tables via the sys_dictionary table.
"""

import logging
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.async_http import get_async_client
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter models
# ---------------------------------------------------------------------------


class CreateFieldParams(BaseModel):
    """Parameters for creating a new field (column) on a ServiceNow table."""

    table_name: str = Field(
        ..., description="Table to add the field to, e.g. 'cmdb_ci', 'incident'"
    )
    column_label: str = Field(
        ..., description="Human-readable label, e.g. 'External ID'"
    )
    column_name: str = Field(
        ...,
        description="Internal column name (must start with 'u_' for custom fields), e.g. 'u_severity'",
    )
    column_type: str = Field(
        "string",
        description=(
            "Field type: 'string', 'integer', 'boolean', 'date', 'datetime', "
            "'decimal', 'float', 'url', 'email', 'reference', 'choice', 'journal', "
            "'glide_date', 'glide_date_time'. Default: 'string'"
        ),
    )
    max_length: Optional[int] = Field(
        None, description="Maximum length for string fields (default depends on type)"
    )
    default_value: Optional[str] = Field(
        None, description="Default value for the field"
    )
    reference_table: Optional[str] = Field(
        None,
        description="For reference fields: target table name, e.g. 'cmdb_model'",
    )
    mandatory: bool = Field(False, description="Whether the field is mandatory")
    read_only: bool = Field(False, description="Whether the field is read-only")
    active: bool = Field(True, description="Whether the field is active")
    description: Optional[str] = Field(
        None, description="Field description / help text"
    )


class ListFieldsParams(BaseModel):
    """Parameters for listing fields on a ServiceNow table."""

    table_name: str = Field(
        ..., description="Table to list fields for, e.g. 'cmdb_ci'"
    )
    name_filter: Optional[str] = Field(
        None,
        description="Filter by column name (contains), e.g. 'u_' to find custom fields",
    )
    custom_only: bool = Field(
        False,
        description="If true, only return custom fields (column_name starts with 'u_')",
    )
    limit: int = Field(50, description="Maximum number of fields to return")
    offset: int = Field(0, description="Offset for pagination")


class UpdateFieldParams(BaseModel):
    """Parameters for updating an existing field definition."""

    sys_id: str = Field(..., description="sys_id of the sys_dictionary record to update")
    column_label: Optional[str] = Field(None, description="New label")
    max_length: Optional[int] = Field(None, description="New max length")
    default_value: Optional[str] = Field(None, description="New default value")
    mandatory: Optional[bool] = Field(None, description="Set mandatory flag")
    read_only: Optional[bool] = Field(None, description="Set read-only flag")
    active: Optional[bool] = Field(None, description="Set active flag")
    description: Optional[str] = Field(None, description="New description / help text")


# ---------------------------------------------------------------------------
# Internal type mapping
# ---------------------------------------------------------------------------

_SN_TYPE_MAP = {
    "string": "string",
    "integer": "integer",
    "boolean": "boolean",
    "date": "glide_date",
    "datetime": "glide_date_time",
    "glide_date": "glide_date",
    "glide_date_time": "glide_date_time",
    "decimal": "decimal",
    "float": "float",
    "url": "url",
    "email": "email",
    "reference": "reference",
    "choice": "choice",
    "journal": "journal",
}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def create_field(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateFieldParams,
) -> Dict[str, Any]:
    """
    Create a new field (column) on a ServiceNow table.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Field definition parameters.

    Returns:
        Dict with success flag, message, and created field details.
    """
    url = f"{config.instance_url}/api/now/table/sys_dictionary"

    internal_type = _SN_TYPE_MAP.get(params.column_type, params.column_type)

    data: Dict[str, Any] = {
        "name": params.table_name,
        "element": params.column_name,
        "column_label": params.column_label,
        "internal_type": internal_type,
        "active": str(params.active).lower(),
        "mandatory": str(params.mandatory).lower(),
        "read_only": str(params.read_only).lower(),
    }

    if params.max_length is not None:
        data["max_length"] = str(params.max_length)
    if params.default_value is not None:
        data["default_value"] = params.default_value
    if params.reference_table and internal_type == "reference":
        data["reference"] = params.reference_table
    if params.description:
        data["comments"] = params.description

    try:
        client = await get_async_client()
        response = await client.post(
            url,
            headers=await auth_manager.get_headers_async(),
            json=data,
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Created field '{params.column_name}' on table '{params.table_name}'",
            "sys_id": result.get("sys_id"),
            "table_name": params.table_name,
            "column_name": params.column_name,
            "record": result,
        }
    except httpx.HTTPError as e:
        logger.error(f"Failed to create field {params.column_name}: {e}")
        return {
            "success": False,
            "message": f"Failed to create field: {str(e)}",
            "sys_id": None,
            "table_name": params.table_name,
            "column_name": params.column_name,
            "record": {},
        }


async def list_fields(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListFieldsParams,
) -> Dict[str, Any]:
    """
    List fields defined on a ServiceNow table.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Filter and pagination parameters.

    Returns:
        Dict with success flag, message, and list of field definitions.
    """
    url = f"{config.instance_url}/api/now/table/sys_dictionary"

    query_parts = [f"name={params.table_name}"]
    if params.name_filter:
        query_parts.append(f"elementLIKE{params.name_filter}")
    if params.custom_only:
        query_parts.append("elementSTARTSWITHu_")

    query_params = {
        "sysparm_query": "^".join(query_parts),
        "sysparm_fields": "sys_id,name,element,column_label,internal_type,max_length,mandatory,read_only,active,default_value,comments,reference",
        "sysparm_limit": str(params.limit),
        "sysparm_offset": str(params.offset),
    }

    try:
        client = await get_async_client()
        response = await client.get(
            url,
            headers=await auth_manager.get_headers_async(),
            params=query_params,
            timeout=config.timeout,
        )
        response.raise_for_status()
        records = response.json().get("result", [])
        fields = []
        for r in records:
            fields.append({
                "sys_id": r.get("sys_id"),
                "table_name": r.get("name"),
                "column_name": r.get("element"),
                "column_label": r.get("column_label"),
                "type": r.get("internal_type"),
                "max_length": r.get("max_length"),
                "mandatory": r.get("mandatory"),
                "read_only": r.get("read_only"),
                "active": r.get("active"),
                "default_value": r.get("default_value"),
                "description": r.get("comments"),
                "reference": r.get("reference"),
            })
        return {
            "success": True,
            "message": f"Found {len(fields)} fields on {params.table_name}",
            "table_name": params.table_name,
            "count": len(fields),
            "fields": fields,
        }
    except httpx.HTTPError as e:
        logger.error(f"Failed to list fields for {params.table_name}: {e}")
        return {
            "success": False,
            "message": f"Failed to list fields: {str(e)}",
            "table_name": params.table_name,
            "count": 0,
            "fields": [],
        }


async def update_field(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateFieldParams,
) -> Dict[str, Any]:
    """
    Update an existing field definition in sys_dictionary.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Fields to update.

    Returns:
        Dict with success flag, message, and updated record.
    """
    url = f"{config.instance_url}/api/now/table/sys_dictionary/{params.sys_id}"

    data: Dict[str, Any] = {}
    if params.column_label is not None:
        data["column_label"] = params.column_label
    if params.max_length is not None:
        data["max_length"] = str(params.max_length)
    if params.default_value is not None:
        data["default_value"] = params.default_value
    if params.mandatory is not None:
        data["mandatory"] = str(params.mandatory).lower()
    if params.read_only is not None:
        data["read_only"] = str(params.read_only).lower()
    if params.active is not None:
        data["active"] = str(params.active).lower()
    if params.description is not None:
        data["comments"] = params.description

    if not data:
        return {
            "success": False,
            "message": "No fields to update — provide at least one field to change.",
            "sys_id": params.sys_id,
            "record": {},
        }

    try:
        client = await get_async_client()
        response = await client.patch(
            url,
            headers=await auth_manager.get_headers_async(),
            json=data,
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Updated field definition {params.sys_id}",
            "sys_id": params.sys_id,
            "record": result,
        }
    except httpx.HTTPError as e:
        logger.error(f"Failed to update field {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to update field: {str(e)}",
            "sys_id": params.sys_id,
            "record": {},
        }

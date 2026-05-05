"""
Service Portal Widget tools for the ServiceNow MCP server.

This module provides tools for managing Service Portal widgets in ServiceNow.
"""

import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.async_http import get_async_client
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


# ============================================================================
# PARAMETER MODELS
# ============================================================================


class CreateWidgetParams(BaseModel):
    """Parameters for creating a Service Portal widget."""

    # Mandatory fields
    name: str = Field(..., description="Display name of the widget")
    id: str = Field(..., description="Widget ID (unique user-defined identifier)")
    description: str = Field(..., description="Description of the widget")

    # Optional fields
    template: Optional[str] = Field(None, description="HTML template for the widget")
    css: Optional[str] = Field(None, description="CSS styles for the widget")
    client_script: Optional[str] = Field(
        None, description="Client-side AngularJS controller script"
    )
    server_script: Optional[str] = Field(
        None, description="Server-side script executed on widget load"
    )
    script: Optional[str] = Field(
        None, description="Alternative name for server script"
    )
    option_schema: Optional[str] = Field(
        None, description="JSON schema for widget options/instance options"
    )
    controller_as: Optional[str] = Field(
        None, description="AngularJS controller alias (default: 'c')"
    )
    demo_data: Optional[str] = Field(
        None, description="Demo/sample data for widget preview"
    )
    has_preview: Optional[bool] = Field(
        None, description="Whether the widget has a preview available"
    )
    data_table: Optional[str] = Field(
        None, description="Associated data table for the widget"
    )
    public: Optional[bool] = Field(
        None, description="Whether the widget is publicly accessible"
    )
    roles: Optional[str] = Field(
        None, description="Comma-separated list of roles that can access the widget"
    )


class UpdateWidgetParams(BaseModel):
    """Parameters for updating an existing Service Portal widget."""

    # Identifier - required
    widget_id: str = Field(
        ..., description="Widget sys_id or widget ID (user-defined id field)"
    )

    # Optional updatable fields
    name: Optional[str] = Field(None, description="Display name of the widget")
    description: Optional[str] = Field(None, description="Description of the widget")
    template: Optional[str] = Field(None, description="HTML template for the widget")
    css: Optional[str] = Field(None, description="CSS styles for the widget")
    client_script: Optional[str] = Field(
        None, description="Client-side AngularJS controller script"
    )
    server_script: Optional[str] = Field(
        None, description="Server-side script executed on widget load"
    )
    script: Optional[str] = Field(
        None, description="Alternative name for server script"
    )
    option_schema: Optional[str] = Field(
        None, description="JSON schema for widget options"
    )
    controller_as: Optional[str] = Field(
        None, description="AngularJS controller alias"
    )
    demo_data: Optional[str] = Field(
        None, description="Demo/sample data for widget preview"
    )
    has_preview: Optional[bool] = Field(
        None, description="Whether the widget has a preview available"
    )
    data_table: Optional[str] = Field(
        None, description="Associated data table for the widget"
    )
    public: Optional[bool] = Field(
        None, description="Whether the widget is publicly accessible"
    )
    roles: Optional[str] = Field(
        None, description="Comma-separated list of roles that can access the widget"
    )


class GetWidgetParams(BaseModel):
    """Parameters for getting/searching Service Portal widgets."""

    # Search by sys_id OR name (one should be provided)
    sys_id: Optional[str] = Field(None, description="Widget sys_id for exact match")
    name: Optional[str] = Field(None, description="Widget name for 'contains' search")

    # Optional pagination for name search
    limit: int = Field(10, description="Maximum number of widgets to return")
    offset: int = Field(0, description="Offset for pagination")


class WidgetResponse(BaseModel):
    """Response from widget operations."""

    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Message describing the result")
    widget_id: Optional[str] = Field(None, description="sys_id of the affected widget")
    widget_name: Optional[str] = Field(None, description="Name of the affected widget")


# ============================================================================
# HELPER CONSTANTS
# ============================================================================

WIDGET_FIELDS = (
    "sys_id,id,name,description,template,css,client_script,server_script,"
    "script,option_schema,controller_as,demo_data,has_preview,data_table,"
    "public,roles,sys_created_on,sys_updated_on,sys_created_by,sys_updated_by"
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _parse_widget(item: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a widget record from ServiceNow API response."""
    return {
        "sys_id": item.get("sys_id"),
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "template": item.get("template"),
        "css": item.get("css"),
        "client_script": item.get("client_script"),
        "server_script": item.get("server_script"),
        "script": item.get("script"),
        "option_schema": item.get("option_schema"),
        "controller_as": item.get("controller_as"),
        "demo_data": item.get("demo_data"),
        "has_preview": item.get("has_preview") == "true",
        "data_table": item.get("data_table"),
        "public": item.get("public") == "true",
        "roles": item.get("roles"),
        "created_on": item.get("sys_created_on"),
        "updated_on": item.get("sys_updated_on"),
        "created_by": item.get("sys_created_by", {}).get("display_value")
        if isinstance(item.get("sys_created_by"), dict)
        else item.get("sys_created_by"),
        "updated_by": item.get("sys_updated_by", {}).get("display_value")
        if isinstance(item.get("sys_updated_by"), dict)
        else item.get("sys_updated_by"),
    }


def _add_optional_field(body: Dict, key: str, value: Optional[str]) -> None:
    """Add a string field to body if value is not None."""
    if value is not None:
        body[key] = value


def _add_optional_bool(body: Dict, key: str, value: Optional[bool]) -> None:
    """Add a boolean field to body as lowercase string if value is not None."""
    if value is not None:
        body[key] = str(value).lower()


async def _resolve_widget_id(
    config: ServerConfig, headers: Dict, widget_id: str
) -> Optional[str]:
    """
    Resolve a widget_id to a sys_id.

    If widget_id is a 32-char hex string, return it as-is (assumed sys_id).
    Otherwise, query by the 'id' field.
    """
    # Check if it's a sys_id (32 char hex)
    if len(widget_id) == 32 and all(
        c in "0123456789abcdef" for c in widget_id.lower()
    ):
        return widget_id

    # Query by widget 'id' field
    url = f"{config.instance_url}/api/now/table/sp_widget"
    query_params: Dict[str, Any] = {
        "sysparm_query": f"id={widget_id}",
        "sysparm_limit": 1,
        "sysparm_fields": "sys_id",
    }

    try:
        client = await get_async_client()
        response = await client.get(
            url, params=query_params, headers=headers, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("result", [])
        if results:
            return results[0].get("sys_id")  # type: ignore[no-any-return]
    except Exception as e:
        logger.error(f"Error resolving widget ID: {e}")

    return None


# ============================================================================
# TOOL FUNCTIONS
# ============================================================================


async def get_widget(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetWidgetParams,
) -> Dict[str, Any]:
    """Get Service Portal widget(s) by sys_id or search by name.

    Args:
        config: The server configuration.
        auth_manager: The authentication manager.
        params: The parameters for the request.

    Returns:
        A dictionary containing the widget(s) data.
    """
    try:
        # Validate: at least one search param required
        if not params.sys_id and not params.name:
            return {
                "success": False,
                "message": "Either sys_id or name must be provided",
            }

        headers = await auth_manager.get_headers_async()
        base_url = f"{config.instance_url}/api/now/table/sp_widget"

        # Search by sys_id (exact match)
        if params.sys_id:
            url = f"{base_url}/{params.sys_id}"
            query_params: Dict[str, Any] = {
                "sysparm_display_value": "true",
                "sysparm_exclude_reference_link": "true",
                "sysparm_fields": WIDGET_FIELDS,
            }

            client = await get_async_client()
            response = await client.get(
                url, params=query_params, headers=headers, timeout=30
            )
            response.raise_for_status()

            data = response.json()
            if "result" not in data:
                return {
                    "success": False,
                    "message": f"Widget not found: {params.sys_id}",
                }

            widget = _parse_widget(data["result"])
            return {
                "success": True,
                "message": f"Found widget: {widget.get('name')}",
                "widget": widget,
            }

        # Search by name (contains)
        query_params = {
            "sysparm_query": f"nameLIKE{params.name}",
            "sysparm_limit": params.limit,
            "sysparm_offset": params.offset,
            "sysparm_display_value": "true",
            "sysparm_exclude_reference_link": "true",
            "sysparm_fields": WIDGET_FIELDS,
        }

        client = await get_async_client()
        response = await client.get(
            base_url, params=query_params, headers=headers, timeout=30
        )
        response.raise_for_status()

        data = response.json()
        widgets = [_parse_widget(item) for item in data.get("result", [])]

        return {
            "success": True,
            "message": f"Found {len(widgets)} widget(s)",
            "widgets": widgets,
            "total": len(widgets),
            "limit": params.limit,
            "offset": params.offset,
        }

    except Exception as e:
        logger.error(f"Error getting widget: {e}")
        return {"success": False, "message": f"Error getting widget: {str(e)}"}


async def create_widget(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateWidgetParams,
) -> WidgetResponse:
    """Create a new Service Portal widget in ServiceNow.

    Args:
        config: The server configuration.
        auth_manager: The authentication manager.
        params: The parameters for the request.

    Returns:
        A response indicating the result of the operation.
    """
    url = f"{config.instance_url}/api/now/table/sp_widget"

    # Build request body with mandatory fields
    body: Dict[str, Any] = {
        "name": params.name,
        "id": params.id,
        "description": params.description,
    }

    # Add optional fields
    _add_optional_field(body, "template", params.template)
    _add_optional_field(body, "css", params.css)
    _add_optional_field(body, "client_script", params.client_script)
    _add_optional_field(body, "server_script", params.server_script)
    _add_optional_field(body, "script", params.script)
    _add_optional_field(body, "option_schema", params.option_schema)
    _add_optional_field(body, "controller_as", params.controller_as)
    _add_optional_field(body, "demo_data", params.demo_data)
    _add_optional_bool(body, "has_preview", params.has_preview)
    _add_optional_field(body, "data_table", params.data_table)
    _add_optional_bool(body, "public", params.public)
    _add_optional_field(body, "roles", params.roles)

    try:
        headers = await auth_manager.get_headers_async()
        client = await get_async_client()
        response = await client.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        if "result" not in data:
            return WidgetResponse(success=False, message="Failed to create widget")

        result = data["result"]
        return WidgetResponse(
            success=True,
            message=f"Created widget: {result.get('name')}",
            widget_id=result.get("sys_id"),
            widget_name=result.get("name"),
        )

    except Exception as e:
        logger.error(f"Error creating widget: {e}")
        return WidgetResponse(
            success=False, message=f"Error creating widget: {str(e)}"
        )


async def update_widget(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateWidgetParams,
) -> WidgetResponse:
    """Update an existing Service Portal widget in ServiceNow.

    Args:
        config: The server configuration.
        auth_manager: The authentication manager.
        params: The parameters for the request.

    Returns:
        A response indicating the result of the operation.
    """
    try:
        headers = await auth_manager.get_headers_async()

        # Resolve widget_id to sys_id
        sys_id = _resolve_widget_id(config, headers, params.widget_id)
        if not sys_id:
            return WidgetResponse(
                success=False,
                message=f"Widget not found: {params.widget_id}",
            )

        # Build update body with only provided fields
        body: Dict[str, Any] = {}
        _add_optional_field(body, "name", params.name)
        _add_optional_field(body, "description", params.description)
        _add_optional_field(body, "template", params.template)
        _add_optional_field(body, "css", params.css)
        _add_optional_field(body, "client_script", params.client_script)
        _add_optional_field(body, "server_script", params.server_script)
        _add_optional_field(body, "script", params.script)
        _add_optional_field(body, "option_schema", params.option_schema)
        _add_optional_field(body, "controller_as", params.controller_as)
        _add_optional_field(body, "demo_data", params.demo_data)
        _add_optional_bool(body, "has_preview", params.has_preview)
        _add_optional_field(body, "data_table", params.data_table)
        _add_optional_bool(body, "public", params.public)
        _add_optional_field(body, "roles", params.roles)

        if not body:
            return WidgetResponse(
                success=True,
                message="No changes to update",
                widget_id=sys_id,
            )

        url = f"{config.instance_url}/api/now/table/sp_widget/{sys_id}"
        client = await get_async_client()
        response = await client.patch(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        if "result" not in data:
            return WidgetResponse(success=False, message="Failed to update widget")

        result = data["result"]
        return WidgetResponse(
            success=True,
            message=f"Updated widget: {result.get('name')}",
            widget_id=result.get("sys_id"),
            widget_name=result.get("name"),
        )

    except Exception as e:
        logger.error(f"Error updating widget: {e}")
        return WidgetResponse(
            success=False, message=f"Error updating widget: {str(e)}"
        )

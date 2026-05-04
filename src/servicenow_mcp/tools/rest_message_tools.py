"""
REST Message tools for the ServiceNow MCP server.

Provides tools to create, list, update, and delete REST Messages
(sys_rest_message) and their HTTP Methods (sys_rest_message_fn) in ServiceNow.
Used for configuring outbound REST integrations (e.g. ServiceNow → external API).
"""

import logging
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter models — REST Message (sys_rest_message)
# ---------------------------------------------------------------------------


class CreateRestMessageParams(BaseModel):
    """Parameters for creating a new REST Message (outbound endpoint)."""

    name: str = Field(..., description="Name of the REST Message, e.g. 'External API'")
    rest_endpoint: str = Field(
        ...,
        description="Base URL of the external endpoint, e.g. 'https://api.example.com'",
    )
    description: Optional[str] = Field(
        None, description="Description of the REST Message"
    )
    authentication_type: str = Field(
        "no_authentication",
        description=(
            "Auth type: 'no_authentication', 'basic', 'oauth2', "
            "'mutual_auth'. Default: 'no_authentication'"
        ),
    )
    basic_auth_user: Optional[str] = Field(
        None, description="Username for basic auth (if authentication_type='basic')"
    )
    basic_auth_password: Optional[str] = Field(
        None, description="Password for basic auth (if authentication_type='basic')"
    )
    oauth2_profile: Optional[str] = Field(
        None,
        description="sys_id of the OAuth2 profile to use (if authentication_type='oauth2')",
    )
    use_mid_server: bool = Field(
        False, description="Whether to route through a MID Server"
    )
    mid_server: Optional[str] = Field(
        None, description="sys_id of the MID Server to use"
    )


class ListRestMessagesParams(BaseModel):
    """Parameters for listing REST Messages."""

    name_filter: Optional[str] = Field(
        None, description="Filter by name (contains)"
    )
    query: Optional[str] = Field(
        None, description="Additional encoded query string"
    )
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")


class GetRestMessageParams(BaseModel):
    """Parameters for getting a single REST Message."""

    sys_id: str = Field(..., description="sys_id of the REST Message")


class UpdateRestMessageParams(BaseModel):
    """Parameters for updating a REST Message."""

    sys_id: str = Field(..., description="sys_id of the REST Message to update")
    name: Optional[str] = Field(None, description="New name")
    rest_endpoint: Optional[str] = Field(None, description="New base URL")
    description: Optional[str] = Field(None, description="New description")
    authentication_type: Optional[str] = Field(None, description="New auth type")
    basic_auth_user: Optional[str] = Field(None, description="New basic auth username")
    basic_auth_password: Optional[str] = Field(None, description="New basic auth password")
    oauth2_profile: Optional[str] = Field(None, description="New OAuth2 profile sys_id")


class DeleteRestMessageParams(BaseModel):
    """Parameters for deleting a REST Message."""

    sys_id: str = Field(..., description="sys_id of the REST Message to delete")


# ---------------------------------------------------------------------------
# Parameter models — HTTP Method (sys_rest_message_fn)
# ---------------------------------------------------------------------------


class CreateHttpMethodParams(BaseModel):
    """Parameters for creating an HTTP Method on a REST Message."""

    rest_message_sys_id: str = Field(
        ..., description="sys_id of the parent REST Message"
    )
    name: str = Field(
        ..., description="Name of the HTTP method, e.g. 'Update CI', 'Create CI'"
    )
    http_method: str = Field(
        ...,
        description="HTTP verb: 'GET', 'POST', 'PUT', 'PATCH', 'DELETE'",
    )
    rest_endpoint: str = Field(
        ...,
        description="Relative or absolute URL for this method, e.g. '/object/${elid}'. Supports variable substitution.",
    )
    content: Optional[str] = Field(
        None,
        description="Request body template (JSON). Supports variable substitution with ${variable_name}.",
    )
    authentication_type: Optional[str] = Field(
        None,
        description="Override auth type for this method. If omitted, inherits from parent REST Message.",
    )


class ListHttpMethodsParams(BaseModel):
    """Parameters for listing HTTP Methods of a REST Message."""

    rest_message_sys_id: str = Field(
        ..., description="sys_id of the parent REST Message"
    )
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")


class UpdateHttpMethodParams(BaseModel):
    """Parameters for updating an HTTP Method."""

    sys_id: str = Field(..., description="sys_id of the HTTP Method to update")
    name: Optional[str] = Field(None, description="New name")
    http_method: Optional[str] = Field(None, description="New HTTP verb")
    rest_endpoint: Optional[str] = Field(None, description="New endpoint URL")
    content: Optional[str] = Field(None, description="New request body template")


class DeleteHttpMethodParams(BaseModel):
    """Parameters for deleting an HTTP Method."""

    sys_id: str = Field(..., description="sys_id of the HTTP Method to delete")


# ---------------------------------------------------------------------------
# Tool implementations — REST Message
# ---------------------------------------------------------------------------


def create_rest_message(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateRestMessageParams,
) -> Dict[str, Any]:
    """Create a new REST Message in ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sys_rest_message"

    data: Dict[str, Any] = {
        "name": params.name,
        "rest_endpoint": params.rest_endpoint,
        "authentication_type": params.authentication_type,
    }

    if params.description:
        data["description"] = params.description
    if params.basic_auth_user:
        data["basic_auth_user"] = params.basic_auth_user
    if params.basic_auth_password:
        data["basic_auth_password"] = params.basic_auth_password
    if params.oauth2_profile:
        data["oauth2_profile"] = params.oauth2_profile
    if params.use_mid_server:
        data["use_mid_server"] = str(params.use_mid_server).lower()
    if params.mid_server:
        data["mid_server"] = params.mid_server

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
            "message": f"Created REST Message '{params.name}'",
            "sys_id": result.get("sys_id"),
            "name": params.name,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to create REST Message '{params.name}': {e}")
        return {
            "success": False,
            "message": f"Failed to create REST Message: {str(e)}",
            "sys_id": None,
            "name": params.name,
            "record": {},
        }


def list_rest_messages(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListRestMessagesParams,
) -> Dict[str, Any]:
    """List REST Messages from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sys_rest_message"

    query_parts: List[str] = []
    if params.name_filter:
        query_parts.append(f"nameLIKE{params.name_filter}")
    if params.query:
        query_parts.append(params.query)

    query_params = {
        "sysparm_query": "^".join(query_parts) if query_parts else "",
        "sysparm_fields": "sys_id,name,rest_endpoint,authentication_type,description,use_mid_server,sys_updated_on",
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
        messages = []
        for r in records:
            messages.append({
                "sys_id": r.get("sys_id"),
                "name": r.get("name"),
                "rest_endpoint": r.get("rest_endpoint"),
                "authentication_type": r.get("authentication_type"),
                "description": r.get("description"),
                "use_mid_server": r.get("use_mid_server"),
                "updated_on": r.get("sys_updated_on"),
            })
        return {
            "success": True,
            "message": f"Found {len(messages)} REST Messages",
            "count": len(messages),
            "rest_messages": messages,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to list REST Messages: {e}")
        return {
            "success": False,
            "message": f"Failed to list REST Messages: {str(e)}",
            "count": 0,
            "rest_messages": [],
        }


def get_rest_message(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetRestMessageParams,
) -> Dict[str, Any]:
    """Get a single REST Message with full details."""
    url = f"{config.instance_url}/api/now/table/sys_rest_message/{params.sys_id}"

    try:
        response = requests.get(
            url,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Retrieved REST Message '{result.get('name', params.sys_id)}'",
            "rest_message": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to get REST Message {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to get REST Message: {str(e)}",
            "rest_message": {},
        }


def update_rest_message(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateRestMessageParams,
) -> Dict[str, Any]:
    """Update an existing REST Message."""
    url = f"{config.instance_url}/api/now/table/sys_rest_message/{params.sys_id}"

    data: Dict[str, Any] = {}
    if params.name is not None:
        data["name"] = params.name
    if params.rest_endpoint is not None:
        data["rest_endpoint"] = params.rest_endpoint
    if params.description is not None:
        data["description"] = params.description
    if params.authentication_type is not None:
        data["authentication_type"] = params.authentication_type
    if params.basic_auth_user is not None:
        data["basic_auth_user"] = params.basic_auth_user
    if params.basic_auth_password is not None:
        data["basic_auth_password"] = params.basic_auth_password
    if params.oauth2_profile is not None:
        data["oauth2_profile"] = params.oauth2_profile

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
            "message": f"Updated REST Message {params.sys_id}",
            "sys_id": params.sys_id,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to update REST Message {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to update REST Message: {str(e)}",
            "sys_id": params.sys_id,
            "record": {},
        }


def delete_rest_message(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: DeleteRestMessageParams,
) -> Dict[str, Any]:
    """Delete a REST Message from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sys_rest_message/{params.sys_id}"

    try:
        response = requests.delete(
            url,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Deleted REST Message {params.sys_id}",
            "sys_id": params.sys_id,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to delete REST Message {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to delete REST Message: {str(e)}",
            "sys_id": params.sys_id,
        }


# ---------------------------------------------------------------------------
# Tool implementations — HTTP Method
# ---------------------------------------------------------------------------


def create_http_method(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateHttpMethodParams,
) -> Dict[str, Any]:
    """Create an HTTP Method on a REST Message."""
    url = f"{config.instance_url}/api/now/table/sys_rest_message_fn"

    data: Dict[str, Any] = {
        "rest_message": params.rest_message_sys_id,
        "function_name": params.name,
        "http_method": params.http_method.upper(),
        "rest_endpoint": params.rest_endpoint,
    }

    if params.content:
        data["content"] = params.content
    if params.authentication_type:
        data["authentication_type"] = params.authentication_type

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
            "message": f"Created HTTP Method '{params.name}' ({params.http_method})",
            "sys_id": result.get("sys_id"),
            "name": params.name,
            "http_method": params.http_method,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to create HTTP Method '{params.name}': {e}")
        return {
            "success": False,
            "message": f"Failed to create HTTP Method: {str(e)}",
            "sys_id": None,
            "name": params.name,
            "record": {},
        }


def list_http_methods(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListHttpMethodsParams,
) -> Dict[str, Any]:
    """List HTTP Methods of a REST Message."""
    url = f"{config.instance_url}/api/now/table/sys_rest_message_fn"

    query_params = {
        "sysparm_query": f"rest_message={params.rest_message_sys_id}",
        "sysparm_fields": "sys_id,function_name,http_method,rest_endpoint,authentication_type,sys_updated_on",
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
        methods = []
        for r in records:
            methods.append({
                "sys_id": r.get("sys_id"),
                "name": r.get("function_name"),
                "http_method": r.get("http_method"),
                "rest_endpoint": r.get("rest_endpoint"),
                "authentication_type": r.get("authentication_type"),
                "updated_on": r.get("sys_updated_on"),
            })
        return {
            "success": True,
            "message": f"Found {len(methods)} HTTP Methods",
            "count": len(methods),
            "methods": methods,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to list HTTP Methods: {e}")
        return {
            "success": False,
            "message": f"Failed to list HTTP Methods: {str(e)}",
            "count": 0,
            "methods": [],
        }


def update_http_method(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateHttpMethodParams,
) -> Dict[str, Any]:
    """Update an HTTP Method."""
    url = f"{config.instance_url}/api/now/table/sys_rest_message_fn/{params.sys_id}"

    data: Dict[str, Any] = {}
    if params.name is not None:
        data["function_name"] = params.name
    if params.http_method is not None:
        data["http_method"] = params.http_method.upper()
    if params.rest_endpoint is not None:
        data["rest_endpoint"] = params.rest_endpoint
    if params.content is not None:
        data["content"] = params.content

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
            "message": f"Updated HTTP Method {params.sys_id}",
            "sys_id": params.sys_id,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to update HTTP Method {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to update HTTP Method: {str(e)}",
            "sys_id": params.sys_id,
            "record": {},
        }


def delete_http_method(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: DeleteHttpMethodParams,
) -> Dict[str, Any]:
    """Delete an HTTP Method from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sys_rest_message_fn/{params.sys_id}"

    try:
        response = requests.delete(
            url,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Deleted HTTP Method {params.sys_id}",
            "sys_id": params.sys_id,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to delete HTTP Method {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to delete HTTP Method: {str(e)}",
            "sys_id": params.sys_id,
        }

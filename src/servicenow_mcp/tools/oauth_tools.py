"""
OAuth Credential tools for the ServiceNow MCP server.

Provides tools to create, list, update, and delete OAuth Entity records
(oauth_entity) and OAuth Entity Profiles (oauth_entity_profile) in ServiceNow.
Used for configuring OAuth2 credentials for outbound integrations.
"""

import logging
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter models — OAuth Entity (oauth_entity)
# ---------------------------------------------------------------------------


class CreateOAuthEntityParams(BaseModel):
    """Parameters for creating a new OAuth Entity (Application Registry)."""

    name: str = Field(
        ..., description="Name of the OAuth application, e.g. 'Acme Service OAuth'"
    )
    client_id: str = Field(..., description="OAuth2 client ID")
    client_secret: str = Field(..., description="OAuth2 client secret")
    token_url: str = Field(
        ...,
        description="Token endpoint URL, e.g. 'https://oauth.example.com/token'",
    )
    auth_url: Optional[str] = Field(
        None, description="Authorization URL (for authorization code flow)"
    )
    default_grant_type: str = Field(
        "client_credentials",
        description="Default grant type: 'client_credentials', 'password', 'authorization_code', 'refresh_token'",
    )
    redirect_url: Optional[str] = Field(
        None, description="Redirect URL (for authorization code flow)"
    )
    active: bool = Field(True, description="Whether the OAuth entity is active")
    comments: Optional[str] = Field(
        None, description="Description or comments"
    )


class ListOAuthEntitiesParams(BaseModel):
    """Parameters for listing OAuth Entities."""

    name_filter: Optional[str] = Field(
        None, description="Filter by name (contains)"
    )
    active_only: bool = Field(
        True, description="Only return active entities (default: true)"
    )
    query: Optional[str] = Field(
        None, description="Additional encoded query string"
    )
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")


class GetOAuthEntityParams(BaseModel):
    """Parameters for getting a single OAuth Entity."""

    sys_id: str = Field(..., description="sys_id of the OAuth Entity")


class UpdateOAuthEntityParams(BaseModel):
    """Parameters for updating an existing OAuth Entity."""

    sys_id: str = Field(..., description="sys_id of the OAuth Entity to update")
    name: Optional[str] = Field(None, description="New name")
    client_id: Optional[str] = Field(None, description="New client ID")
    client_secret: Optional[str] = Field(None, description="New client secret")
    token_url: Optional[str] = Field(None, description="New token URL")
    auth_url: Optional[str] = Field(None, description="New authorization URL")
    default_grant_type: Optional[str] = Field(None, description="New default grant type")
    active: Optional[bool] = Field(None, description="Set active flag")
    comments: Optional[str] = Field(None, description="New comments")


class DeleteOAuthEntityParams(BaseModel):
    """Parameters for deleting an OAuth Entity."""

    sys_id: str = Field(..., description="sys_id of the OAuth Entity to delete")


# ---------------------------------------------------------------------------
# Parameter models — OAuth Entity Profile (oauth_entity_profile)
# ---------------------------------------------------------------------------


class CreateOAuthProfileParams(BaseModel):
    """Parameters for creating an OAuth Entity Profile (credential set)."""

    oauth_entity_sys_id: str = Field(
        ..., description="sys_id of the parent OAuth Entity"
    )
    name: str = Field(
        ..., description="Profile name, e.g. 'Production Profile'"
    )
    grant_type: str = Field(
        "client_credentials",
        description="Grant type: 'client_credentials', 'password', 'authorization_code'",
    )
    username: Optional[str] = Field(
        None, description="Username (for password grant)"
    )
    password: Optional[str] = Field(
        None, description="Password (for password grant)"
    )
    default_profile: bool = Field(
        True, description="Whether this is the default profile"
    )


class ListOAuthProfilesParams(BaseModel):
    """Parameters for listing OAuth Entity Profiles."""

    oauth_entity_sys_id: Optional[str] = Field(
        None, description="Filter by parent OAuth Entity sys_id"
    )
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")


class UpdateOAuthProfileParams(BaseModel):
    """Parameters for updating an OAuth Entity Profile."""

    sys_id: str = Field(..., description="sys_id of the OAuth Profile to update")
    name: Optional[str] = Field(None, description="New name")
    grant_type: Optional[str] = Field(None, description="New grant type")
    username: Optional[str] = Field(None, description="New username")
    password: Optional[str] = Field(None, description="New password")
    default_profile: Optional[bool] = Field(None, description="Set as default profile")


class DeleteOAuthProfileParams(BaseModel):
    """Parameters for deleting an OAuth Entity Profile."""

    sys_id: str = Field(..., description="sys_id of the OAuth Profile to delete")


# ---------------------------------------------------------------------------
# Tool implementations — OAuth Entity
# ---------------------------------------------------------------------------


def create_oauth_entity(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateOAuthEntityParams,
) -> Dict[str, Any]:
    """Create a new OAuth Entity in ServiceNow."""
    url = f"{config.instance_url}/api/now/table/oauth_entity"

    data: Dict[str, Any] = {
        "name": params.name,
        "client_id": params.client_id,
        "client_secret": params.client_secret,
        "token_url": params.token_url,
        "default_grant_type": params.default_grant_type,
        "active": str(params.active).lower(),
    }

    if params.auth_url:
        data["auth_url"] = params.auth_url
    if params.redirect_url:
        data["redirect_url"] = params.redirect_url
    if params.comments:
        data["comments"] = params.comments

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
            "message": f"Created OAuth Entity '{params.name}'",
            "sys_id": result.get("sys_id"),
            "name": params.name,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to create OAuth Entity '{params.name}': {e}")
        return {
            "success": False,
            "message": f"Failed to create OAuth Entity: {str(e)}",
            "sys_id": None,
            "name": params.name,
            "record": {},
        }


def list_oauth_entities(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListOAuthEntitiesParams,
) -> Dict[str, Any]:
    """List OAuth Entities from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/oauth_entity"

    query_parts: List[str] = []
    if params.name_filter:
        query_parts.append(f"nameLIKE{params.name_filter}")
    if params.active_only:
        query_parts.append("active=true")
    if params.query:
        query_parts.append(params.query)

    query_params = {
        "sysparm_query": "^".join(query_parts) if query_parts else "",
        "sysparm_fields": "sys_id,name,client_id,token_url,auth_url,default_grant_type,active,sys_updated_on",
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
        entities = []
        for r in records:
            entities.append({
                "sys_id": r.get("sys_id"),
                "name": r.get("name"),
                "client_id": r.get("client_id"),
                "token_url": r.get("token_url"),
                "auth_url": r.get("auth_url"),
                "default_grant_type": r.get("default_grant_type"),
                "active": r.get("active"),
                "updated_on": r.get("sys_updated_on"),
            })
        return {
            "success": True,
            "message": f"Found {len(entities)} OAuth Entities",
            "count": len(entities),
            "entities": entities,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to list OAuth Entities: {e}")
        return {
            "success": False,
            "message": f"Failed to list OAuth Entities: {str(e)}",
            "count": 0,
            "entities": [],
        }


def get_oauth_entity(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetOAuthEntityParams,
) -> Dict[str, Any]:
    """Get a single OAuth Entity with full details."""
    url = f"{config.instance_url}/api/now/table/oauth_entity/{params.sys_id}"

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
            "message": f"Retrieved OAuth Entity '{result.get('name', params.sys_id)}'",
            "entity": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to get OAuth Entity {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to get OAuth Entity: {str(e)}",
            "entity": {},
        }


def update_oauth_entity(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateOAuthEntityParams,
) -> Dict[str, Any]:
    """Update an existing OAuth Entity."""
    url = f"{config.instance_url}/api/now/table/oauth_entity/{params.sys_id}"

    data: Dict[str, Any] = {}
    if params.name is not None:
        data["name"] = params.name
    if params.client_id is not None:
        data["client_id"] = params.client_id
    if params.client_secret is not None:
        data["client_secret"] = params.client_secret
    if params.token_url is not None:
        data["token_url"] = params.token_url
    if params.auth_url is not None:
        data["auth_url"] = params.auth_url
    if params.default_grant_type is not None:
        data["default_grant_type"] = params.default_grant_type
    if params.active is not None:
        data["active"] = str(params.active).lower()
    if params.comments is not None:
        data["comments"] = params.comments

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
            "message": f"Updated OAuth Entity {params.sys_id}",
            "sys_id": params.sys_id,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to update OAuth Entity {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to update OAuth Entity: {str(e)}",
            "sys_id": params.sys_id,
            "record": {},
        }


def delete_oauth_entity(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: DeleteOAuthEntityParams,
) -> Dict[str, Any]:
    """Delete an OAuth Entity from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/oauth_entity/{params.sys_id}"

    try:
        response = requests.delete(
            url,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Deleted OAuth Entity {params.sys_id}",
            "sys_id": params.sys_id,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to delete OAuth Entity {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to delete OAuth Entity: {str(e)}",
            "sys_id": params.sys_id,
        }


# ---------------------------------------------------------------------------
# Tool implementations — OAuth Entity Profile
# ---------------------------------------------------------------------------


def create_oauth_profile(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateOAuthProfileParams,
) -> Dict[str, Any]:
    """Create an OAuth Entity Profile."""
    url = f"{config.instance_url}/api/now/table/oauth_entity_profile"

    data: Dict[str, Any] = {
        "oauth_entity": params.oauth_entity_sys_id,
        "name": params.name,
        "grant_type": params.grant_type,
        "default": str(params.default_profile).lower(),
    }

    if params.username:
        data["username"] = params.username
    if params.password:
        data["password"] = params.password

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
            "message": f"Created OAuth Profile '{params.name}'",
            "sys_id": result.get("sys_id"),
            "name": params.name,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to create OAuth Profile '{params.name}': {e}")
        return {
            "success": False,
            "message": f"Failed to create OAuth Profile: {str(e)}",
            "sys_id": None,
            "name": params.name,
            "record": {},
        }


def list_oauth_profiles(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListOAuthProfilesParams,
) -> Dict[str, Any]:
    """List OAuth Entity Profiles."""
    url = f"{config.instance_url}/api/now/table/oauth_entity_profile"

    query_parts: List[str] = []
    if params.oauth_entity_sys_id:
        query_parts.append(f"oauth_entity={params.oauth_entity_sys_id}")

    query_params = {
        "sysparm_query": "^".join(query_parts) if query_parts else "",
        "sysparm_fields": "sys_id,name,oauth_entity,grant_type,default,sys_updated_on",
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
        profiles = []
        for r in records:
            profiles.append({
                "sys_id": r.get("sys_id"),
                "name": r.get("name"),
                "oauth_entity": r.get("oauth_entity"),
                "grant_type": r.get("grant_type"),
                "default": r.get("default"),
                "updated_on": r.get("sys_updated_on"),
            })
        return {
            "success": True,
            "message": f"Found {len(profiles)} OAuth Profiles",
            "count": len(profiles),
            "profiles": profiles,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to list OAuth Profiles: {e}")
        return {
            "success": False,
            "message": f"Failed to list OAuth Profiles: {str(e)}",
            "count": 0,
            "profiles": [],
        }


def update_oauth_profile(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateOAuthProfileParams,
) -> Dict[str, Any]:
    """Update an OAuth Entity Profile."""
    url = f"{config.instance_url}/api/now/table/oauth_entity_profile/{params.sys_id}"

    data: Dict[str, Any] = {}
    if params.name is not None:
        data["name"] = params.name
    if params.grant_type is not None:
        data["grant_type"] = params.grant_type
    if params.username is not None:
        data["username"] = params.username
    if params.password is not None:
        data["password"] = params.password
    if params.default_profile is not None:
        data["default"] = str(params.default_profile).lower()

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
            "message": f"Updated OAuth Profile {params.sys_id}",
            "sys_id": params.sys_id,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to update OAuth Profile {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to update OAuth Profile: {str(e)}",
            "sys_id": params.sys_id,
            "record": {},
        }


def delete_oauth_profile(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: DeleteOAuthProfileParams,
) -> Dict[str, Any]:
    """Delete an OAuth Entity Profile from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/oauth_entity_profile/{params.sys_id}"

    try:
        response = requests.delete(
            url,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Deleted OAuth Profile {params.sys_id}",
            "sys_id": params.sys_id,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to delete OAuth Profile {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to delete OAuth Profile: {str(e)}",
            "sys_id": params.sys_id,
        }

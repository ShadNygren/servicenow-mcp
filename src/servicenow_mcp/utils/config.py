"""
Configuration module for the ServiceNow MCP server.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AuthType(str, Enum):
    """Authentication types supported by the ServiceNow MCP server."""

    BASIC = "basic"
    OAUTH = "oauth"
    API_KEY = "api_key"


class BasicAuthConfig(BaseModel):
    """Configuration for basic authentication."""

    username: str
    password: str


class OAuthConfig(BaseModel):
    """Configuration for OAuth authentication.

    ``username`` and ``password`` are optional — required only for the
    legacy ``password`` grant fallback. The recommended path is
    ``client_credentials`` (set ``client_id`` + ``client_secret`` only).
    The OAuth Best Current Practice deprecates the password grant; we
    keep it for environments that have it as a hard requirement.

    ``resource_url`` is the optional ``resource`` parameter used by some
    Authorization Server flavors (notably Azure AD-backed ServiceNow
    instances). When set, it's added to the client_credentials request
    body.
    """

    client_id: str
    client_secret: str
    username: Optional[str] = None
    password: Optional[str] = None
    token_url: Optional[str] = None
    resource_url: Optional[str] = None


class ApiKeyConfig(BaseModel):
    """Configuration for API key authentication."""

    api_key: str
    header_name: str = "X-ServiceNow-API-Key"


class AuthConfig(BaseModel):
    """Authentication configuration."""

    type: AuthType
    basic: Optional[BasicAuthConfig] = None
    oauth: Optional[OAuthConfig] = None
    api_key: Optional[ApiKeyConfig] = None


class ServerConfig(BaseModel):
    """Server configuration."""

    instance_url: str
    auth: AuthConfig
    debug: bool = False
    timeout: int = 30
    api_path: str = Field(
        default="api",
        description=(
            "Path segment between the instance URL and ``/now`` in the "
            "Table-API URL. Defaults to ``api`` for stock ServiceNow; "
            "override via ``SERVICENOW_API_PATH`` for instances behind a "
            "gateway or with a non-standard API mount."
        ),
    )

    @property
    def api_url(self) -> str:
        """Get the API URL for the ServiceNow instance."""
        return f"{self.instance_url}/{self.api_path}/now"

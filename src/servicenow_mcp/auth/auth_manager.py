"""
Authentication manager for the ServiceNow MCP server.
"""

import base64
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

from servicenow_mcp.utils.config import AuthConfig, AuthType


logger = logging.getLogger(__name__)

# Refresh OAuth tokens this many seconds before their stated expiry, to
# avoid losing a request to clock skew or in-flight expiry.
_TOKEN_REFRESH_SAFETY_MARGIN = timedelta(seconds=30)

# Default token lifetime if the OAuth response omits expires_in. ServiceNow
# defaults to 1800s (30min) for access tokens; we mirror that here.
_TOKEN_DEFAULT_LIFETIME_SECONDS = 1800


class AuthManager:
    """
    Authentication manager for ServiceNow API.

    This class handles authentication with the ServiceNow API using
    different authentication methods. For OAuth, tokens are cached with
    their stated expiry and refreshed automatically before they expire.
    """

    def __init__(self, config: AuthConfig, instance_url: str = None):
        """
        Initialize the authentication manager.

        Args:
            config: Authentication configuration.
            instance_url: ServiceNow instance URL.
        """
        self.config = config
        self.instance_url = instance_url
        self.token: Optional[str] = None
        self.token_type: Optional[str] = None
        # Timezone-aware UTC datetime — never an epoch float, never a naive
        # datetime. michaelbuckner's implementation mixed datetime and float
        # which crashed with TypeError on the second refresh.
        self.token_expiry: Optional[datetime] = None
        self.refresh_token_value: Optional[str] = None
    
    @staticmethod
    def _extract_oauth_error_code(response: requests.Response) -> str:
        """Extract a non-sensitive OAuth error code from a response, or 'unknown_error'."""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return str(payload.get("error", "unknown_error"))
        except ValueError:
            pass
        return "non_json_response"

    def get_headers(self) -> Dict[str, str]:
        """
        Get the authentication headers for API requests.
        
        Returns:
            Dict[str, str]: Headers to include in API requests.
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        if self.config.type == AuthType.BASIC:
            if not self.config.basic:
                raise ValueError("Basic auth configuration is required")
            
            auth_str = f"{self.config.basic.username}:{self.config.basic.password}"
            encoded = base64.b64encode(auth_str.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        
        elif self.config.type == AuthType.OAUTH:
            if self._oauth_token_is_expired():
                self._get_oauth_token()

            headers["Authorization"] = f"{self.token_type} {self.token}"
        
        elif self.config.type == AuthType.API_KEY:
            if not self.config.api_key:
                raise ValueError("API key configuration is required")
            
            headers[self.config.api_key.header_name] = self.config.api_key.api_key
        
        return headers
    
    def _get_oauth_token(self):
        """
        Get an OAuth token from ServiceNow.
        
        Raises:
            ValueError: If OAuth configuration is missing or token request fails.
        """
        if not self.config.oauth:
            raise ValueError("OAuth configuration is required")
        oauth_config = self.config.oauth

        # Determine token URL — derive from instance_url so custom domains
        # (e.g. instances on `.example.com` instead of `.service-now.com`) work.
        token_url = oauth_config.token_url
        if not token_url:
            if not self.instance_url:
                raise ValueError("Instance URL is required for OAuth authentication")
            token_url = f"{self.instance_url.rstrip('/')}/oauth_token.do"

        # Prepare Authorization header
        auth_str = f"{oauth_config.client_id}:{oauth_config.client_secret}"
        auth_header = base64.b64encode(auth_str.encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        # Try client_credentials grant first — recommended path. Falls back
        # to password grant only if username+password configured (deprecated
        # by OAuth Best Current Practice; see Issue #43 finding #2).
        data_client_credentials = {
            "grant_type": "client_credentials"
        }
        if oauth_config.resource_url:
            # Azure AD-backed ServiceNow and some on-prem AS implementations
            # require a `resource` parameter naming the audience.
            data_client_credentials["resource"] = oauth_config.resource_url

        logger.info("Attempting OAuth client_credentials grant")
        response = requests.post(token_url, headers=headers, data=data_client_credentials)
        logger.info("OAuth client_credentials response status: %s", response.status_code)

        if response.status_code == 200:
            self._store_token_response(response.json())
            return

        client_credentials_error = self._extract_oauth_error_code(response)
        client_credentials_status = response.status_code

        # Try password grant if client_credentials failed
        if oauth_config.username and oauth_config.password:
            data_password = {
                "grant_type": "password",
                "username": oauth_config.username,
                "password": oauth_config.password
            }

            logger.info("Attempting OAuth password grant")
            response = requests.post(token_url, headers=headers, data=data_password)
            logger.info("OAuth password grant response status: %s", response.status_code)

            if response.status_code == 200:
                self._store_token_response(response.json())
                return

            password_error = self._extract_oauth_error_code(response)
            raise ValueError(
                f"Failed to get OAuth token: client_credentials returned "
                f"{client_credentials_status} ({client_credentials_error}); "
                f"password grant returned {response.status_code} ({password_error})."
            )

        raise ValueError(
            f"Failed to get OAuth token: client_credentials returned "
            f"{client_credentials_status} ({client_credentials_error}); "
            "no username/password configured for password-grant fallback."
        )
    
    def _oauth_token_is_expired(self) -> bool:
        """True if there is no cached OAuth token, or it is within the safety
        margin of expiry."""
        if not self.token:
            return True
        if self.token_expiry is None:
            # Token cached but no expiry recorded — assume valid (legacy path,
            # for token responses that omit expires_in).
            return False
        return datetime.now(timezone.utc) >= self.token_expiry - _TOKEN_REFRESH_SAFETY_MARGIN

    def _store_token_response(self, token_data: dict) -> None:
        """Cache an OAuth token-endpoint response, including a timezone-aware
        UTC expiry derived from expires_in (or the default lifetime)."""
        self.token = token_data.get("access_token")
        self.token_type = token_data.get("token_type", "Bearer")
        expires_in = token_data.get("expires_in", _TOKEN_DEFAULT_LIFETIME_SECONDS)
        self.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        # OAuth servers may or may not return a refresh_token; store if present.
        refresh = token_data.get("refresh_token")
        if refresh:
            self.refresh_token_value = refresh

    def refresh_token(self):
        """Force-refresh the OAuth token by clearing the cache and re-fetching.

        Useful from a 401-retry handler after a south-bound ServiceNow request
        fails: clear the cached token so the next get_headers() call refetches
        unconditionally.
        """
        if self.config.type == AuthType.OAUTH:
            self.token = None
            self.token_expiry = None
            self._get_oauth_token()

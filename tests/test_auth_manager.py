"""
Tests for the AuthManager OAuth token caching and refresh-on-expiry logic.

Validates the type-safe datetime expiry handling that avoids the
datetime-vs-float TypeError seen in upstream michaelbuckner code.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
import requests

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import (
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    OAuthConfig,
)


def _oauth_config():
    return AuthConfig(
        type=AuthType.OAUTH,
        oauth=OAuthConfig(
            client_id="cid",
            client_secret="csec",
            username="u",
            password="p",
        ),
    )


def _mock_token_response(access_token: str = "tok-1", expires_in: int = 1800):
    response = MagicMock(spec=requests.Response)
    response.status_code = 200
    response.json.return_value = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
    }
    return response


def test_token_expiry_stored_as_timezone_aware_datetime():
    """Token expiry must be a timezone-aware UTC datetime, never an epoch float."""
    manager = AuthManager(_oauth_config(), instance_url="https://dev.example.com")
    with patch("servicenow_mcp.auth.auth_manager.requests.post", return_value=_mock_token_response()):
        manager.get_headers()

    assert isinstance(manager.token_expiry, datetime)
    assert manager.token_expiry.tzinfo is not None, "token_expiry must be timezone-aware"
    # Sanity: expiry is in the future.
    assert manager.token_expiry > datetime.now(timezone.utc)


def test_token_not_refetched_while_valid():
    """Within the validity window, get_headers reuses the cached token."""
    manager = AuthManager(_oauth_config(), instance_url="https://dev.example.com")
    with patch("servicenow_mcp.auth.auth_manager.requests.post", return_value=_mock_token_response()) as post:
        manager.get_headers()
        manager.get_headers()
        manager.get_headers()
    assert post.call_count == 1, "Token endpoint should only be hit once while token is valid"


def test_token_refetched_when_expired():
    """When the cached token is past its expiry (minus safety margin), get_headers refetches."""
    manager = AuthManager(_oauth_config(), instance_url="https://dev.example.com")
    with patch("servicenow_mcp.auth.auth_manager.requests.post", return_value=_mock_token_response("tok-1")) as post:
        manager.get_headers()
        # Force expiry into the past.
        manager.token_expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
        post.return_value = _mock_token_response("tok-2")
        headers = manager.get_headers()

    assert post.call_count == 2, "Expired token must trigger a second token fetch"
    assert manager.token == "tok-2"
    assert headers["Authorization"] == "Bearer tok-2"


def test_token_refetched_within_safety_margin():
    """A token that expires within the 30s safety margin is treated as expired."""
    manager = AuthManager(_oauth_config(), instance_url="https://dev.example.com")
    with patch("servicenow_mcp.auth.auth_manager.requests.post", return_value=_mock_token_response("tok-1")) as post:
        manager.get_headers()
        # Set expiry to 10s in the future — inside the 30s safety margin.
        manager.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=10)
        post.return_value = _mock_token_response("tok-2")
        manager.get_headers()

    assert post.call_count == 2
    assert manager.token == "tok-2"


def test_repeated_refresh_does_not_raise_typeerror():
    """Regression test for michaelbuckner's datetime-vs-float bug.

    Their implementation compared datetime.now() (datetime) to
    self.token_expiry (sometimes datetime, sometimes float from .timestamp()),
    which raised TypeError after the first refresh. This test loops three
    refreshes to catch any reintroduction of that mistake.
    """
    manager = AuthManager(_oauth_config(), instance_url="https://dev.example.com")
    with patch("servicenow_mcp.auth.auth_manager.requests.post", return_value=_mock_token_response("tok-1")) as post:
        for i in range(3):
            manager.get_headers()
            manager.token_expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
            post.return_value = _mock_token_response(f"tok-{i+2}")
        # Final call uses the still-valid token from the loop's last refetch.
        manager.token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        manager.get_headers()


def test_force_refresh_clears_cache():
    """refresh_token() forces an unconditional refetch, even if the cached token is valid."""
    manager = AuthManager(_oauth_config(), instance_url="https://dev.example.com")
    with patch("servicenow_mcp.auth.auth_manager.requests.post", return_value=_mock_token_response("tok-1")) as post:
        manager.get_headers()
        post.return_value = _mock_token_response("tok-2")
        manager.refresh_token()

    assert post.call_count == 2
    assert manager.token == "tok-2"


def test_client_credentials_only_no_username_password():
    """Phase 3.1 / Issue #43 finding #2: client_credentials should work
    without username/password configured."""
    config = AuthConfig(
        type=AuthType.OAUTH,
        oauth=OAuthConfig(
            client_id="cid",
            client_secret="csec",
            # username and password deliberately omitted
        ),
    )
    manager = AuthManager(config, instance_url="https://dev.example.com")
    with patch("servicenow_mcp.auth.auth_manager.requests.post", return_value=_mock_token_response("tok-cc")) as post:
        manager.get_headers()

    assert manager.token == "tok-cc"
    # Verify only client_credentials grant was attempted
    assert post.call_count == 1
    sent_data = post.call_args[1]["data"]
    assert sent_data == {"grant_type": "client_credentials"}


def test_extra_http_headers_env_var_merged_into_headers(monkeypatch):
    """Phase 3.3: SERVICENOW_EXTRA_HTTP_HEADERS env var (JSON dict) is
    merged into every get_headers() call. Useful for corporate proxies
    and trace headers without monkey-patching the auth manager."""
    monkeypatch.setenv(
        "SERVICENOW_EXTRA_HTTP_HEADERS",
        '{"X-Tenant-Id": "acme", "X-Trace-Id": "abc123"}',
    )
    config = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(username="u", password="p"),
    )
    headers = AuthManager(config).get_headers()
    assert headers.get("X-Tenant-Id") == "acme"
    assert headers.get("X-Trace-Id") == "abc123"
    # Standard headers still present
    assert headers["Accept"] == "application/json"


def test_extra_http_headers_legacy_env_var_still_works(monkeypatch):
    """The original EXTRA_HTTP_HEADERS env var (without SERVICENOW_ prefix)
    remains supported as a fallback for backward compatibility."""
    monkeypatch.delenv("SERVICENOW_EXTRA_HTTP_HEADERS", raising=False)
    monkeypatch.setenv("EXTRA_HTTP_HEADERS", '{"X-Legacy": "yes"}')
    config = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(username="u", password="p"),
    )
    headers = AuthManager(config).get_headers()
    assert headers.get("X-Legacy") == "yes"


def test_extra_http_headers_namespaced_takes_precedence(monkeypatch):
    """When both env vars are set, SERVICENOW_EXTRA_HTTP_HEADERS wins."""
    monkeypatch.setenv("SERVICENOW_EXTRA_HTTP_HEADERS", '{"X-Source": "namespaced"}')
    monkeypatch.setenv("EXTRA_HTTP_HEADERS", '{"X-Source": "legacy"}')
    config = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(username="u", password="p"),
    )
    headers = AuthManager(config).get_headers()
    assert headers.get("X-Source") == "namespaced"


def test_resource_url_added_to_client_credentials_request():
    """Azure AD-style flows: when resource_url is set, it goes into the
    client_credentials request body as the `resource` parameter."""
    config = AuthConfig(
        type=AuthType.OAUTH,
        oauth=OAuthConfig(
            client_id="cid",
            client_secret="csec",
            resource_url="https://api.example.com",
        ),
    )
    manager = AuthManager(config, instance_url="https://dev.example.com")
    with patch("servicenow_mcp.auth.auth_manager.requests.post", return_value=_mock_token_response()) as post:
        manager.get_headers()

    sent_data = post.call_args[1]["data"]
    assert sent_data == {
        "grant_type": "client_credentials",
        "resource": "https://api.example.com",
    }


def test_default_lifetime_when_expires_in_missing():
    """If the token response omits expires_in, fall back to the default lifetime."""
    response = MagicMock(spec=requests.Response)
    response.status_code = 200
    response.json.return_value = {"access_token": "tok-1", "token_type": "Bearer"}
    manager = AuthManager(_oauth_config(), instance_url="https://dev.example.com")
    with patch("servicenow_mcp.auth.auth_manager.requests.post", return_value=response):
        manager.get_headers()

    assert manager.token_expiry is not None
    # Should be roughly _TOKEN_DEFAULT_LIFETIME_SECONDS (1800) in the future.
    seconds_until_expiry = (manager.token_expiry - datetime.now(timezone.utc)).total_seconds()
    assert 1700 < seconds_until_expiry < 1800

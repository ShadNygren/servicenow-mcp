# tests/test_identifier_resolver.py
import pytest
from unittest.mock import MagicMock, patch

from servicenow_mcp.utils.identifier_resolver import is_sys_id, resolve_identifier

VALID_SYS_ID = "a" * 32


def test_is_sys_id_accepts_32_hex_chars():
    assert is_sys_id("a" * 32) is True
    assert is_sys_id("0" * 32) is True
    assert is_sys_id("abc123def456abc123def456abc123de") is True  # exactly 32


def test_is_sys_id_rejects_ticket_numbers():
    assert is_sys_id("INC0012345") is False
    assert is_sys_id("CHG0012345") is False
    assert is_sys_id("PRB0012345") is False


def test_is_sys_id_rejects_wrong_length():
    assert is_sys_id("a" * 31) is False
    assert is_sys_id("a" * 33) is False


def test_is_sys_id_rejects_non_string_inputs():
    assert is_sys_id(None) is False
    assert is_sys_id(123) is False


def _make_config():
    config = MagicMock()
    config.api_url = "https://dev.service-now.com/api/now"
    config.timeout = 30
    return config


def _make_auth(headers=None):
    auth = MagicMock()
    auth.get_headers.return_value = headers or {"Authorization": "Basic dGVzdA=="}
    return auth


def test_resolve_identifier_returns_sys_id_unchanged():
    config = _make_config()
    auth = _make_auth()
    result = resolve_identifier(config, auth, "incident", VALID_SYS_ID)
    assert result == VALID_SYS_ID
    auth.get_headers.assert_not_called()  # No HTTP call for sys_id passthrough


def test_resolve_identifier_looks_up_ticket_number():
    config = _make_config()
    auth = _make_auth()
    found_sys_id = "b" * 32

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": [{"sys_id": found_sys_id}]}

    with patch("servicenow_mcp.utils.identifier_resolver.requests.get", return_value=mock_resp) as mock_get:
        result = resolve_identifier(config, auth, "incident", "INC0012345")

    assert result == found_sys_id
    call_params = mock_get.call_args
    assert "sysparm_query" in call_params.kwargs["params"]
    assert "INC0012345" in call_params.kwargs["params"]["sysparm_query"]


def test_resolve_identifier_raises_value_error_when_not_found():
    config = _make_config()
    auth = _make_auth()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": []}

    with patch("servicenow_mcp.utils.identifier_resolver.requests.get", return_value=mock_resp):
        with pytest.raises(ValueError, match="Record not found: incident/INC9999999"):
            resolve_identifier(config, auth, "incident", "INC9999999")


def test_resolve_identifier_uppercases_ticket_before_query():
    config = _make_config()
    auth = _make_auth()
    found_sys_id = "c" * 32

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": [{"sys_id": found_sys_id}]}

    with patch("servicenow_mcp.utils.identifier_resolver.requests.get", return_value=mock_resp) as mock_get:
        resolve_identifier(config, auth, "incident", "inc0012345")  # lowercase input

    params = mock_get.call_args.kwargs["params"]["sysparm_query"]
    assert "INC0012345" in params  # must be uppercased in query

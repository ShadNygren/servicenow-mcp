"""Tests for the NLP processor and natural-language tools."""

from unittest.mock import MagicMock, patch

import pytest

from servicenow_mcp.tools.nl_tools import (
    NaturalLanguageSearchParams,
    NaturalLanguageUpdateParams,
    natural_language_search,
    natural_language_update,
)
from servicenow_mcp.utils.config import (
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    ServerConfig,
)
from servicenow_mcp.utils.nl import NLPProcessor


# ---------------------------------------------------------------------------
# NLPProcessor (rule-based parser)
# ---------------------------------------------------------------------------


def test_search_query_defaults_to_incident_table():
    parsed = NLPProcessor.parse_search_query("find anything urgent")
    assert parsed["table"] == "incident"


def test_search_query_routes_to_problem():
    parsed = NLPProcessor.parse_search_query("find problems related to outages")
    assert parsed["table"] == "problem"


def test_search_query_routes_to_change_request():
    parsed = NLPProcessor.parse_search_query("show changes about firewall")
    assert parsed["table"] == "change_request"


def test_search_query_extracts_priority():
    parsed = NLPProcessor.parse_search_query("incidents with high priority about SAP")
    assert "priority=1" in parsed["query"]
    assert "123TEXTQUERY321=SAP" in parsed["query"]


def test_search_query_extracts_state():
    parsed = NLPProcessor.parse_search_query("show resolved incidents about email")
    assert "state=7" in parsed["query"]


def test_update_command_extracts_record_number():
    record_number, updates = NLPProcessor.parse_update_command(
        "Update incident INC0010001 saying I'm working on it"
    )
    assert record_number == "INC0010001"
    assert updates["state"] == 2  # In Progress
    assert "I'm working on it" in updates["comments"]


def test_update_command_close_with_resolution():
    record_number, updates = NLPProcessor.parse_update_command(
        "Close incident INC0010003 with resolution: fixed the issue"
    )
    assert record_number == "INC0010003"
    assert updates["state"] == 7  # Closed
    assert updates["close_notes"] == "fixed the issue"
    assert updates["close_code"] == "Solved (Permanently)"


def test_update_command_work_note_vs_comment():
    _, updates = NLPProcessor.parse_update_command(
        "Update INC0010002 with work note: investigating root cause"
    )
    assert "work_notes" in updates
    assert "comments" not in updates


def test_update_command_missing_number_raises():
    with pytest.raises(ValueError, match="No record number"):
        NLPProcessor.parse_update_command("Close that incident already")


# ---------------------------------------------------------------------------
# natural_language_search tool
# ---------------------------------------------------------------------------


def _config():
    return ServerConfig(
        instance_url="https://dev12345.service-now.com",
        auth=AuthConfig(
            type=AuthType.BASIC,
            basic=BasicAuthConfig(username="admin", password="x"),
        ),
    )


def _auth_manager():
    am = MagicMock()
    am.get_headers.return_value = {"Authorization": "Basic xxx"}
    return am


def test_natural_language_search_returns_records():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "result": [
            {"number": "INC0010001", "short_description": "SAP outage"},
            {"number": "INC0010002", "short_description": "SAP login"},
        ]
    }
    with patch(
        "servicenow_mcp.tools.nl_tools.requests.get", return_value=response
    ) as get:
        result = natural_language_search(
            _config(),
            _auth_manager(),
            NaturalLanguageSearchParams(query="incidents about SAP"),
        )

    assert result.success is True
    assert result.table == "incident"
    assert result.record_count == 2
    assert "/api/now/table/incident" in get.call_args[0][0]
    assert "123TEXTQUERY321=SAP" in get.call_args[1]["params"]["sysparm_query"]


def test_natural_language_search_handles_error():
    response = MagicMock()
    response.status_code = 401
    response.text = '{"error":"unauthorized"}'
    with patch(
        "servicenow_mcp.tools.nl_tools.requests.get", return_value=response
    ):
        result = natural_language_search(
            _config(),
            _auth_manager(),
            NaturalLanguageSearchParams(query="incidents"),
        )
    assert result.success is False
    assert "401" in result.message


# ---------------------------------------------------------------------------
# natural_language_update tool
# ---------------------------------------------------------------------------


def test_natural_language_update_full_flow():
    """Successful update: lookup sys_id → patch."""
    lookup = MagicMock()
    lookup.status_code = 200
    lookup.json.return_value = {"result": [{"sys_id": "abc123", "number": "INC0010001"}]}

    patch_resp = MagicMock()
    patch_resp.status_code = 200

    with patch("servicenow_mcp.tools.nl_tools.requests.get", return_value=lookup) as get, patch(
        "servicenow_mcp.tools.nl_tools.requests.patch", return_value=patch_resp
    ) as patch_call:
        result = natural_language_update(
            _config(),
            _auth_manager(),
            NaturalLanguageUpdateParams(command="Close incident INC0010001 with resolution: fixed"),
        )

    assert result.success is True
    assert result.sys_id == "abc123"
    assert "/api/now/table/incident/abc123" in patch_call.call_args[0][0]
    assert patch_call.call_args[1]["json"]["state"] == 7


def test_natural_language_update_record_not_found():
    lookup = MagicMock()
    lookup.status_code = 200
    lookup.json.return_value = {"result": []}
    with patch(
        "servicenow_mcp.tools.nl_tools.requests.get", return_value=lookup
    ):
        result = natural_language_update(
            _config(),
            _auth_manager(),
            NaturalLanguageUpdateParams(command="Close INC9999999 with resolution: foo"),
        )
    assert result.success is False
    assert "not found" in result.message


def test_natural_language_update_no_actionable_updates():
    """If the command parses no changes, don't hit the API."""
    with patch("servicenow_mcp.tools.nl_tools.requests.get") as get, patch(
        "servicenow_mcp.tools.nl_tools.requests.patch"
    ) as patch_call:
        result = natural_language_update(
            _config(),
            _auth_manager(),
            NaturalLanguageUpdateParams(command="just look at incident INC0010001 please"),
        )
    assert result.success is False
    assert "No actionable updates" in result.message
    assert get.call_count == 0
    assert patch_call.call_count == 0


def test_natural_language_update_missing_number():
    result = natural_language_update(
        _config(),
        _auth_manager(),
        NaturalLanguageUpdateParams(command="close that ticket I sent earlier"),
    )
    assert result.success is False
    assert "No record number" in result.message

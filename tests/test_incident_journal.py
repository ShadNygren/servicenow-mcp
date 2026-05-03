"""Tests for get_incident_journal — the work_notes/comments timeline tool.

Closes echelon Issue #52
(https://github.com/echelon-ai-labs/servicenow-mcp/issues/52).
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from servicenow_mcp.tools.incident_tools import (
    GetIncidentJournalParams,
    get_incident_journal,
)
from servicenow_mcp.utils.config import (
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    ServerConfig,
)


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


def _mock_response(status_code: int = 200, result=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {"result": result if result is not None else []}
    return response


def test_returns_journal_entries_in_order():
    """Happy path: lookup → journal query → ordered entries returned."""
    lookup_resp = _mock_response(200, [{"sys_id": "abc123", "number": "INC0010001"}])
    journal_resp = _mock_response(
        200,
        [
            {
                "sys_id": "j1",
                "sys_created_on": "2026-04-01 10:00:00",
                "sys_created_by": "alice",
                "element": "comments",
                "value": "Customer reports issue.",
            },
            {
                "sys_id": "j2",
                "sys_created_on": "2026-04-01 11:30:00",
                "sys_created_by": "bob",
                "element": "work_notes",
                "value": "Investigating logs.",
            },
        ],
    )

    with patch(
        "servicenow_mcp.tools.incident_tools.requests.get",
        side_effect=[lookup_resp, journal_resp],
    ) as mock_get:
        result = get_incident_journal(
            _config(),
            _auth_manager(),
            GetIncidentJournalParams(incident_number="INC0010001"),
        )

    assert result["success"] is True
    assert result["incident_number"] == "INC0010001"
    assert result["incident_sys_id"] == "abc123"
    assert result["count"] == 2
    assert result["entries"][0]["field"] == "comments"
    assert result["entries"][1]["field"] == "work_notes"
    assert result["entries"][1]["created_by"] == "bob"

    # Verify the journal query targets sys_journal_field with the right filter.
    journal_call = mock_get.call_args_list[1]
    assert "/api/now/table/sys_journal_field" in journal_call[0][0]
    query = journal_call[1]["params"]["sysparm_query"]
    assert "name=incident" in query
    assert "element_id=abc123" in query
    assert "element=work_notes" in query
    assert "element=comments" in query
    assert "ORDERBYsys_created_on" in query


def test_returns_only_requested_fields():
    """When fields=['work_notes'], only that field is queried."""
    lookup_resp = _mock_response(200, [{"sys_id": "abc123"}])
    journal_resp = _mock_response(200, [])

    with patch(
        "servicenow_mcp.tools.incident_tools.requests.get",
        side_effect=[lookup_resp, journal_resp],
    ) as mock_get:
        result = get_incident_journal(
            _config(),
            _auth_manager(),
            GetIncidentJournalParams(incident_number="INC0010001", fields=["work_notes"]),
        )

    assert result["success"] is True
    assert result["fields_queried"] == ["work_notes"]
    journal_call = mock_get.call_args_list[1]
    query = journal_call[1]["params"]["sysparm_query"]
    assert "element=work_notes" in query
    assert "element=comments" not in query


def test_incident_not_found():
    lookup_resp = _mock_response(200, [])
    with patch("servicenow_mcp.tools.incident_tools.requests.get", return_value=lookup_resp):
        result = get_incident_journal(
            _config(),
            _auth_manager(),
            GetIncidentJournalParams(incident_number="INC9999999"),
        )
    assert result["success"] is False
    assert "not found" in result["message"]


def test_lookup_returns_non_200():
    lookup_resp = _mock_response(401, [])
    with patch("servicenow_mcp.tools.incident_tools.requests.get", return_value=lookup_resp):
        result = get_incident_journal(
            _config(),
            _auth_manager(),
            GetIncidentJournalParams(incident_number="INC0010001"),
        )
    assert result["success"] is False
    assert "401" in result["message"]


def test_lookup_network_error():
    with patch(
        "servicenow_mcp.tools.incident_tools.requests.get",
        side_effect=requests.RequestException("connection refused"),
    ):
        result = get_incident_journal(
            _config(),
            _auth_manager(),
            GetIncidentJournalParams(incident_number="INC0010001"),
        )
    assert result["success"] is False
    assert "look up" in result["message"]


def test_journal_query_returns_non_200():
    lookup_resp = _mock_response(200, [{"sys_id": "abc"}])
    journal_resp = _mock_response(500, [])
    with patch(
        "servicenow_mcp.tools.incident_tools.requests.get",
        side_effect=[lookup_resp, journal_resp],
    ):
        result = get_incident_journal(
            _config(),
            _auth_manager(),
            GetIncidentJournalParams(incident_number="INC0010001"),
        )
    assert result["success"] is False
    assert "500" in result["message"]


def test_limit_parameter_passed_through():
    lookup_resp = _mock_response(200, [{"sys_id": "abc"}])
    journal_resp = _mock_response(200, [])
    with patch(
        "servicenow_mcp.tools.incident_tools.requests.get",
        side_effect=[lookup_resp, journal_resp],
    ) as mock_get:
        get_incident_journal(
            _config(),
            _auth_manager(),
            GetIncidentJournalParams(incident_number="INC0010001", limit=25),
        )
    journal_call = mock_get.call_args_list[1]
    assert journal_call[1]["params"]["sysparm_limit"] == "25"

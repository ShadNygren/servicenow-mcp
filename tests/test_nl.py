"""Tests for the NLP processor and natural-language tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
# NLPProcessor (rule-based parser) — pure functions, no I/O.
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
    assert "123TEXTQUERY321=" in parsed["query"]
    assert "SAP" in parsed["query"]


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
        "Resolve incident INC0010003 with resolution: applied patch"
    )
    assert record_number == "INC0010003"
    assert updates["state"] == 6  # Resolved
    assert updates["close_notes"] == "applied patch"
    assert updates["close_code"] == "Solved (Permanently)"

    _, closed_updates = NLPProcessor.parse_update_command(
        "Close incident INC0010003 with close note: superseded by INC0020000"
    )
    assert closed_updates["state"] == 7


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
# natural_language_search / natural_language_update tools (async, httpx).
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
    am.get_headers_async = AsyncMock(return_value={"Authorization": "Basic xxx"})
    return am


def _mock_response(status_code=200, json_body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_body or {})
    return resp


async def test_natural_language_search_returns_records():
    response = _mock_response(
        json_body={
            "result": [
                {"number": "INC0010001", "short_description": "SAP outage"},
                {"number": "INC0010002", "short_description": "SAP login"},
            ]
        }
    )
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as get:
        get.return_value = response
        result = await natural_language_search(
            _config(),
            _auth_manager(),
            NaturalLanguageSearchParams(query="incidents about SAP"),
        )

    assert result.success is True
    assert result.table == "incident"
    assert result.record_count == 2
    assert "/api/now/table/incident" in get.call_args[0][0]
    assert "123TEXTQUERY321=SAP" in get.call_args[1]["params"]["sysparm_query"]


async def test_natural_language_search_handles_error():
    response = _mock_response(status_code=401, text='{"error":"unauthorized"}')
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as get:
        get.return_value = response
        result = await natural_language_search(
            _config(),
            _auth_manager(),
            NaturalLanguageSearchParams(query="incidents"),
        )
    assert result.success is False
    assert "401" in result.message


async def test_natural_language_update_full_flow():
    """Successful update: lookup sys_id → patch."""
    lookup = _mock_response(json_body={"result": [{"sys_id": "abc123", "number": "INC0010001"}]})
    patch_resp = _mock_response()

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as get, patch.object(
        httpx.AsyncClient, "patch", new_callable=AsyncMock
    ) as patch_call:
        get.return_value = lookup
        patch_call.return_value = patch_resp
        result = await natural_language_update(
            _config(),
            _auth_manager(),
            NaturalLanguageUpdateParams(
                command="Resolve incident INC0010001 with resolution: applied patch"
            ),
        )

    assert result.success is True
    assert result.sys_id == "abc123"
    assert "/api/now/table/incident/abc123" in patch_call.call_args[0][0]
    assert patch_call.call_args[1]["json"]["state"] == 6  # Resolved


async def test_natural_language_update_record_not_found():
    lookup = _mock_response(json_body={"result": []})
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as get:
        get.return_value = lookup
        result = await natural_language_update(
            _config(),
            _auth_manager(),
            NaturalLanguageUpdateParams(command="Close INC9999999 with resolution: foo"),
        )
    assert result.success is False
    assert "not found" in result.message


async def test_natural_language_update_no_actionable_updates():
    """If the command parses no changes, don't hit the API."""
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as get, patch.object(
        httpx.AsyncClient, "patch", new_callable=AsyncMock
    ) as patch_call:
        result = await natural_language_update(
            _config(),
            _auth_manager(),
            NaturalLanguageUpdateParams(command="just look at incident INC0010001 please"),
        )
    assert result.success is False
    assert "No actionable updates" in result.message
    assert get.call_count == 0
    assert patch_call.call_count == 0


async def test_natural_language_update_missing_number():
    result = await natural_language_update(
        _config(),
        _auth_manager(),
        NaturalLanguageUpdateParams(command="close that ticket I sent earlier"),
    )
    assert result.success is False
    assert "No record number" in result.message

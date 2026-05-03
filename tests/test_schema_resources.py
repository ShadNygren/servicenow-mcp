"""Tests for the schema-discovery resources."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from servicenow_mcp.resources.schema import SchemaResources, _TTLCache
from servicenow_mcp.utils.config import (
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    ServerConfig,
)


def _make_resources():
    config = ServerConfig(
        instance_url="https://dev12345.service-now.com",
        auth=AuthConfig(
            type=AuthType.BASIC,
            basic=BasicAuthConfig(username="admin", password="secret"),
        ),
    )
    auth_manager = MagicMock()
    auth_manager.get_headers.return_value = {"Authorization": "Basic xyz"}
    return SchemaResources(config, auth_manager)


def _mock_table_response(rows):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"result": rows}
    return response


def test_list_tables_uri_returns_table_list():
    resources = _make_resources()
    rows = [
        {"name": "incident", "label": "Incident", "sys_id": "abc"},
        {"name": "task", "label": "Task", "sys_id": "def"},
    ]
    with patch(
        "servicenow_mcp.resources.schema.requests.get",
        return_value=_mock_table_response(rows),
    ) as get:
        body = resources.read("servicenow://tables")

    assert json.loads(body) == rows
    # Verify it hit /api/now/table/sys_db_object
    called_url = get.call_args[0][0]
    assert "/api/now/table/sys_db_object" in called_url


def test_table_records_uri_returns_sample_rows():
    resources = _make_resources()
    rows = [{"number": "INC0010001", "short_description": "test"}]
    with patch(
        "servicenow_mcp.resources.schema.requests.get",
        return_value=_mock_table_response(rows),
    ) as get:
        body = resources.read("servicenow://tables/incident")

    assert json.loads(body) == rows
    assert "/api/now/table/incident" in get.call_args[0][0]
    # Sample limit applied
    assert get.call_args[1]["params"]["sysparm_limit"] == "10"


def test_table_schema_uri_queries_sys_dictionary():
    resources = _make_resources()
    rows = [
        {"element": "number", "column_label": "Number", "internal_type": "string"},
        {"element": "short_description", "column_label": "Description", "internal_type": "string"},
    ]
    with patch(
        "servicenow_mcp.resources.schema.requests.get",
        return_value=_mock_table_response(rows),
    ) as get:
        body = resources.read("servicenow://schema/incident")

    assert json.loads(body) == rows
    assert "/api/now/table/sys_dictionary" in get.call_args[0][0]
    assert get.call_args[1]["params"]["sysparm_query"] == "name=incident^elementISNOTEMPTY"


def test_repeated_reads_use_cache():
    resources = _make_resources()
    rows = [{"name": "incident"}]
    with patch(
        "servicenow_mcp.resources.schema.requests.get",
        return_value=_mock_table_response(rows),
    ) as get:
        resources.read("servicenow://tables")
        resources.read("servicenow://tables")
        resources.read("servicenow://tables")

    assert get.call_count == 1, "Cache hit should prevent repeat HTTP calls"


def test_unsupported_uri_raises():
    resources = _make_resources()
    with pytest.raises(ValueError, match="Unsupported schema resource URI"):
        resources.read("servicenow://does-not-exist")


def test_missing_table_in_template_raises():
    resources = _make_resources()
    with pytest.raises(ValueError, match="Missing table name"):
        resources.read("servicenow://schema/")


def test_non_200_response_raises():
    resources = _make_resources()
    bad_response = MagicMock()
    bad_response.status_code = 401
    with patch(
        "servicenow_mcp.resources.schema.requests.get",
        return_value=bad_response,
    ):
        with pytest.raises(RuntimeError, match="returned 401"):
            resources.read("servicenow://tables")


def test_ttl_cache_expires_entries():
    cache = _TTLCache(ttl_seconds=0)  # Everything expires immediately
    cache.set("k", "v")
    # Sleep a tiny bit to be safe across monotonic clock resolutions
    time.sleep(0.01)
    assert cache.get("k") is None


def test_ttl_cache_returns_fresh_entries():
    cache = _TTLCache(ttl_seconds=300)
    cache.set("k", "v")
    assert cache.get("k") == "v"

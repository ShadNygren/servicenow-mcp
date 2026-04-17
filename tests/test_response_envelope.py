# tests/test_response_envelope.py
from servicenow_mcp.utils.response_envelope import SnowResponse


def test_success_response_includes_data_and_context():
    resp = SnowResponse(success=True, data={"sys_id": "abc"}, table="incident", operation="create_record")
    d = resp.to_dict()
    assert d["success"] is True
    assert d["data"] == {"sys_id": "abc"}
    assert d["table"] == "incident"
    assert d["operation"] == "create_record"


def test_none_fields_absent_from_output():
    resp = SnowResponse(success=True, data={"sys_id": "abc"})
    d = resp.to_dict()
    assert "error" not in d
    assert "details" not in d
    assert "table" not in d
    assert "operation" not in d


def test_error_response_omits_none_data():
    resp = SnowResponse(success=False, error="Record not found", details="HTTP 404")
    d = resp.to_dict()
    assert d["success"] is False
    assert d["error"] == "Record not found"
    assert d["details"] == "HTTP 404"
    assert "data" not in d


def test_warnings_present_when_non_empty():
    resp = SnowResponse(success=True, data={}, warnings=["Field 'x' does not exist"])
    d = resp.to_dict()
    assert d["warnings"] == ["Field 'x' does not exist"]


def test_warnings_absent_when_empty():
    resp = SnowResponse(success=True, data={})
    d = resp.to_dict()
    assert "warnings" not in d


def test_to_dict_is_json_serialisable():
    import json
    resp = SnowResponse(
        success=True,
        data={"sys_id": "abc", "count": 3},
        warnings=["test"],
        table="incident",
        operation="query_records",
    )
    # Should not raise
    json.dumps(resp.to_dict())

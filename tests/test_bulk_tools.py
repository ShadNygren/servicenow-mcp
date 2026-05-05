"""Tests for bulk_tools.py — execute_bulk_operations."""

import json
import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.bulk_tools import (
    BulkOperationRequest,
    BulkOperationsParams,
    execute_bulk_operations,
)
from servicenow_mcp.utils.config import AuthConfig, AuthType, BasicAuthConfig, ServerConfig

_AUTH_CONFIG = AuthConfig(
    type=AuthType.BASIC,
    basic=BasicAuthConfig(username="admin", password="password"),
)
_FAKE_HEADERS = {"Authorization": "Basic YWRtaW46cGFzc3dvcmQ="}


def _config() -> ServerConfig:
    return ServerConfig(instance_url="https://dev99999.service-now.com", auth=_AUTH_CONFIG)


def _auth() -> MagicMock:
    m = MagicMock(spec=AuthManager)
    # Phase 9.2: tools now call get_headers_async instead of get_headers.
    m.get_headers_async = AsyncMock(return_value=_FAKE_HEADERS)
    return m


def _batch_response(items: list) -> MagicMock:
    """Build a mock httpx.Response for a batch call."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"servicedRequests": items}
    return mock_resp


class TestBulkOperationRequestModel(unittest.TestCase):
    def test_method_normalised_to_uppercase(self):
        req = BulkOperationRequest(id="1", method="get", url="/api/now/v2/table/incident")
        self.assertEqual(req.method, "GET")

    def test_invalid_method_raises(self):
        with self.assertRaises(Exception):
            BulkOperationRequest(id="1", method="HEAD", url="/api/now/v2/table/incident")

    def test_full_url_stripped_to_path(self):
        req = BulkOperationRequest(
            id="1",
            method="GET",
            url="https://dev99999.service-now.com/api/now/v2/table/incident?sysparm_limit=5",
        )
        self.assertEqual(req.url, "/api/now/v2/table/incident?sysparm_limit=5")

    def test_relative_url_kept_unchanged(self):
        req = BulkOperationRequest(id="1", method="POST", url="/api/now/v2/table/incident")
        self.assertEqual(req.url, "/api/now/v2/table/incident")

    def test_body_defaults_to_none(self):
        req = BulkOperationRequest(id="1", method="GET", url="/api/now/v2/table/incident")
        self.assertIsNone(req.body)

    def test_all_allowed_methods_accepted(self):
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            req = BulkOperationRequest(id="1", method=method, url="/api/now/v2/table/incident")
            self.assertEqual(req.method, method)


class TestExecuteBulkOperationsSuccess(IsolatedAsyncioTestCase):
    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_single_get_request_success(self, mock_post):
        mock_post.return_value = _batch_response(
            [
                {
                    "id": "req1",
                    "statusCode": 200,
                    "statusText": "OK",
                    "body": json.dumps({"result": [{"sys_id": "abc"}]}),
                }
            ]
        )
        params = BulkOperationsParams(
            requests=[
                BulkOperationRequest(
                    id="req1",
                    method="GET",
                    url="/api/now/v2/table/incident",
                )
            ]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)

        self.assertTrue(result["success"])
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["results"][0]["ok"])
        self.assertEqual(result["results"][0]["status_code"], 200)
        self.assertEqual(result["results"][0]["id"], "req1")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_batch_url_constructed_correctly(self, mock_post):
        mock_post.return_value = _batch_response(
            [{"id": "r1", "statusCode": 200, "statusText": "OK", "body": "{}"}]
        )
        params = BulkOperationsParams(
            requests=[BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident")]
        )
        await execute_bulk_operations(_config(), _auth(), params)

        call_url = mock_post.call_args[0][0]
        self.assertEqual(call_url, "https://dev99999.service-now.com/api/now/v1/batch")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_post_request_body_serialised_as_json_string(self, mock_post):
        mock_post.return_value = _batch_response(
            [{"id": "r1", "statusCode": 201, "statusText": "Created", "body": "{}"}]
        )
        params = BulkOperationsParams(
            requests=[
                BulkOperationRequest(
                    id="r1",
                    method="POST",
                    url="/api/now/v2/table/incident",
                    body={"short_description": "Test"},
                )
            ]
        )
        await execute_bulk_operations(_config(), _auth(), params)

        sent_payload = mock_post.call_args[1]["json"]
        sub_req = sent_payload["requests"][0]
        # body must be a JSON string, not a dict
        self.assertIsInstance(sub_req["body"], str)
        self.assertEqual(json.loads(sub_req["body"]), {"short_description": "Test"})

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_get_request_body_is_empty_string(self, mock_post):
        mock_post.return_value = _batch_response(
            [{"id": "r1", "statusCode": 200, "statusText": "OK", "body": "{}"}]
        )
        params = BulkOperationsParams(
            requests=[BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident")]
        )
        await execute_bulk_operations(_config(), _auth(), params)

        sent_payload = mock_post.call_args[1]["json"]
        sub_req = sent_payload["requests"][0]
        self.assertEqual(sub_req["body"], "")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_multiple_requests_all_succeed(self, mock_post):
        mock_post.return_value = _batch_response(
            [
                {"id": "r1", "statusCode": 200, "statusText": "OK", "body": "{}"},
                {"id": "r2", "statusCode": 201, "statusText": "Created", "body": "{}"},
                {"id": "r3", "statusCode": 204, "statusText": "No Content", "body": ""},
            ]
        )
        params = BulkOperationsParams(
            requests=[
                BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident"),
                BulkOperationRequest(
                    id="r2",
                    method="POST",
                    url="/api/now/v2/table/change_request",
                    body={"short_description": "x"},
                ),
                BulkOperationRequest(
                    id="r3",
                    method="DELETE",
                    url="/api/now/v2/table/incident/abc123",
                ),
            ]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)

        self.assertTrue(result["success"])
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["succeeded"], 3)
        self.assertEqual(result["failed"], 0)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_response_body_parsed_from_json_string(self, mock_post):
        body_data = {"result": {"sys_id": "abc123", "number": "INC0001234"}}
        mock_post.return_value = _batch_response(
            [
                {
                    "id": "r1",
                    "statusCode": 200,
                    "statusText": "OK",
                    "body": json.dumps(body_data),
                }
            ]
        )
        params = BulkOperationsParams(
            requests=[BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident/abc123")]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)

        self.assertEqual(result["results"][0]["body"], body_data)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_empty_body_in_response_becomes_none(self, mock_post):
        mock_post.return_value = _batch_response(
            [{"id": "r1", "statusCode": 204, "statusText": "No Content", "body": ""}]
        )
        params = BulkOperationsParams(
            requests=[
                BulkOperationRequest(id="r1", method="DELETE", url="/api/now/v2/table/incident/abc")
            ]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)
        self.assertIsNone(result["results"][0]["body"])


class TestExecuteBulkOperationsPartialFailure(IsolatedAsyncioTestCase):
    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_one_failure_sets_success_false(self, mock_post):
        mock_post.return_value = _batch_response(
            [
                {"id": "r1", "statusCode": 200, "statusText": "OK", "body": "{}"},
                {
                    "id": "r2",
                    "statusCode": 404,
                    "statusText": "Not Found",
                    "body": json.dumps({"error": {"message": "No record found"}}),
                },
            ]
        )
        params = BulkOperationsParams(
            requests=[
                BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident"),
                BulkOperationRequest(
                    id="r2", method="GET", url="/api/now/v2/table/incident/missing_id"
                ),
            ]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)

        self.assertFalse(result["success"])
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertFalse(result["results"][1]["ok"])
        self.assertEqual(result["results"][1]["status_code"], 404)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_5xx_error_counted_as_failure(self, mock_post):
        mock_post.return_value = _batch_response(
            [{"id": "r1", "statusCode": 500, "statusText": "Internal Server Error", "body": "{}"}]
        )
        params = BulkOperationsParams(
            requests=[BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident")]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)

        self.assertFalse(result["success"])
        self.assertEqual(result["failed"], 1)


class TestExecuteBulkOperationsErrors(IsolatedAsyncioTestCase):
    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_connection_error_returns_failure(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        params = BulkOperationsParams(
            requests=[BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident")]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)

        self.assertFalse(result["success"])
        self.assertIn("Batch request failed", result["message"])

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_http_error_returns_failure_with_message(self, mock_post):
        mock_resp = httpx.Response(
            401,
            json={"error": {"message": "User Not Authenticated"}},
            request=httpx.Request("POST", "https://dev99999.service-now.com/api/now/v1/batch"),
        )
        http_err = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=mock_resp.request,
            response=mock_resp,
        )
        mock_post.side_effect = http_err

        params = BulkOperationsParams(
            requests=[BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident")]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)

        self.assertFalse(result["success"])
        self.assertIn("401", result["message"])

    async def test_empty_requests_list_returns_failure(self):
        # Bypass Pydantic min_length by constructing manually
        params = BulkOperationsParams.__new__(BulkOperationsParams)
        object.__setattr__(params, "requests", [])
        result = await execute_bulk_operations(_config(), _auth(), params)
        self.assertFalse(result["success"])
        self.assertIn("No requests provided", result["message"])

    async def test_over_100_requests_returns_failure(self):
        params = BulkOperationsParams.__new__(BulkOperationsParams)
        too_many = [
            BulkOperationRequest(id=str(i), method="GET", url="/api/now/v2/table/incident")
            for i in range(101)
        ]
        object.__setattr__(params, "requests", too_many)
        result = await execute_bulk_operations(_config(), _auth(), params)
        self.assertFalse(result["success"])
        self.assertIn("Too many requests", result["message"])

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_non_json_body_in_response_kept_as_string(self, mock_post):
        mock_post.return_value = _batch_response(
            [{"id": "r1", "statusCode": 200, "statusText": "OK", "body": "not-json"}]
        )
        params = BulkOperationsParams(
            requests=[BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident")]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)

        self.assertEqual(result["results"][0]["body"], "not-json")


class TestExecuteBulkOperationsPayloadStructure(IsolatedAsyncioTestCase):
    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_request_ids_preserved_in_batch_payload(self, mock_post):
        mock_post.return_value = _batch_response(
            [
                {"id": "alpha", "statusCode": 200, "statusText": "OK", "body": "{}"},
                {"id": "beta", "statusCode": 200, "statusText": "OK", "body": "{}"},
            ]
        )
        params = BulkOperationsParams(
            requests=[
                BulkOperationRequest(id="alpha", method="GET", url="/api/now/v2/table/incident"),
                BulkOperationRequest(id="beta", method="GET", url="/api/now/v2/table/change_request"),
            ]
        )
        await execute_bulk_operations(_config(), _auth(), params)

        sent_payload = mock_post.call_args[1]["json"]
        ids = [r["id"] for r in sent_payload["requests"]]
        self.assertEqual(ids, ["alpha", "beta"])

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_content_type_header_included_in_each_sub_request(self, mock_post):
        mock_post.return_value = _batch_response(
            [{"id": "r1", "statusCode": 200, "statusText": "OK", "body": "{}"}]
        )
        params = BulkOperationsParams(
            requests=[BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident")]
        )
        await execute_bulk_operations(_config(), _auth(), params)

        sent_payload = mock_post.call_args[1]["json"]
        sub_headers = {h["name"]: h["value"] for h in sent_payload["requests"][0]["headers"]}
        self.assertEqual(sub_headers.get("Content-Type"), "application/json")
        self.assertEqual(sub_headers.get("Accept"), "application/json")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_auth_headers_sent_on_outer_request(self, mock_post):
        mock_post.return_value = _batch_response(
            [{"id": "r1", "statusCode": 200, "statusText": "OK", "body": "{}"}]
        )
        params = BulkOperationsParams(
            requests=[BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident")]
        )
        auth = _auth()
        await execute_bulk_operations(_config(), auth, params)

        called_headers = mock_post.call_args[1]["headers"]
        self.assertIn("Authorization", called_headers)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_result_message_shows_counts(self, mock_post):
        mock_post.return_value = _batch_response(
            [
                {"id": "r1", "statusCode": 200, "statusText": "OK", "body": "{}"},
                {"id": "r2", "statusCode": 404, "statusText": "Not Found", "body": "{}"},
            ]
        )
        params = BulkOperationsParams(
            requests=[
                BulkOperationRequest(id="r1", method="GET", url="/api/now/v2/table/incident"),
                BulkOperationRequest(id="r2", method="GET", url="/api/now/v2/table/incident/bad"),
            ]
        )
        result = await execute_bulk_operations(_config(), _auth(), params)
        self.assertIn("1/2", result["message"])


if __name__ == "__main__":
    unittest.main()

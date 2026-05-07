"""Tests for contract_tools.py."""

import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.contract_tools import (
    _format_contract,
    create_asset_contract,
    get_asset_contract,
    list_asset_contracts,
    update_asset_contract,
)
from servicenow_mcp.utils.config import AuthConfig, AuthType, BasicAuthConfig, ServerConfig

FAKE_CONTRACT = {
    "sys_id": "con001",
    "number": "CON0001234",
    "short_description": "Annual hardware maintenance",
    "vendor": {"display_value": "Dell Inc.", "value": "vendor001"},
    "state": "active",
    "contract_type": {"display_value": "Maintenance", "value": "maint001"},
    "category": {"display_value": "Hardware", "value": "cat001"},
    "start_date": "2025-01-01",
    "end_date": "2026-01-01",
    "value": "50000.00",
    "currency": "USD",
    "assigned_to": {"display_value": "Jane Smith", "value": "user001"},
    "department": {"display_value": "IT", "value": "dept001"},
    "company": {"display_value": "Acme Corp", "value": "comp001"},
    "location": {"display_value": "HQ", "value": "loc001"},
    "sys_created_on": "2025-01-01 09:00:00",
    "sys_updated_on": "2026-01-01 00:00:00",
}


def _make_config():
    auth_config = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(username="test", password="test"),
    )
    return ServerConfig(instance_url="https://dev99999.service-now.com", auth=auth_config)


def _make_auth_manager():
    auth_manager = MagicMock(spec=AuthManager)
    auth_manager.get_headers.return_value = {"Authorization": "Bearer FAKE"}
    auth_manager.instance_url = "https://dev99999.service-now.com"
    return auth_manager


class TestFormatContract(IsolatedAsyncioTestCase):
    def test_all_fields_mapped(self):
        result = _format_contract(FAKE_CONTRACT)
        self.assertEqual(result["sys_id"], "con001")
        self.assertEqual(result["number"], "CON0001234")
        self.assertEqual(result["short_description"], "Annual hardware maintenance")
        self.assertEqual(result["vendor"], "Dell Inc.")
        self.assertEqual(result["state"], "active")
        self.assertEqual(result["contract_type"], "Maintenance")
        self.assertEqual(result["category"], "Hardware")
        self.assertEqual(result["start_date"], "2025-01-01")
        self.assertEqual(result["end_date"], "2026-01-01")
        self.assertEqual(result["value"], "50000.00")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["assigned_to"], "Jane Smith")
        self.assertEqual(result["department"], "IT")
        self.assertEqual(result["company"], "Acme Corp")
        self.assertEqual(result["location"], "HQ")
        self.assertEqual(result["created_on"], "2025-01-01 09:00:00")
        self.assertEqual(result["updated_on"], "2026-01-01 00:00:00")

    def test_missing_fields_return_none(self):
        result = _format_contract({})
        for key in ("sys_id", "number", "short_description", "vendor", "state",
                    "contract_type", "category", "start_date", "end_date",
                    "value", "currency", "assigned_to", "department", "company",
                    "location", "created_on", "updated_on"):
            self.assertIsNone(result[key], f"{key} should be None for empty record")

    def test_plain_string_ref_fields(self):
        record = dict(FAKE_CONTRACT)
        record["vendor"] = "Some Vendor"
        record["assigned_to"] = "plain_user"
        result = _format_contract(record)
        self.assertEqual(result["vendor"], "Some Vendor")
        self.assertEqual(result["assigned_to"], "plain_user")

    def test_ref_field_falls_back_to_value(self):
        record = dict(FAKE_CONTRACT)
        record["vendor"] = {"display_value": "", "value": "raw_vendor_id"}
        result = _format_contract(record)
        self.assertEqual(result["vendor"], "raw_vendor_id")


class TestListAssetContracts(IsolatedAsyncioTestCase):
    def setUp(self):
        self.auth = _make_auth_manager()
        self.config = _make_config()

    def _mock_response(self, data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {"result": data}
        resp.raise_for_status.return_value = None
        return resp

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_returns_contracts(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        result = await list_asset_contracts(self.auth, self.config, {})
        self.assertTrue(result["success"])
        self.assertEqual(len(result["contracts"]), 1)
        self.assertEqual(result["contracts"][0]["number"], "CON0001234")

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_empty_result(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([])
        result = await list_asset_contracts(self.auth, self.config, {})
        self.assertTrue(result["success"])
        self.assertEqual(result["contracts"], [])
        self.assertEqual(result["count"], 0)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_vendor_filter_applied(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await list_asset_contracts(self.auth, self.config, {"vendor": "Dell"})
        call_kwargs = mock_make_request.call_args
        query = call_kwargs[1]["params"].get("sysparm_query", "")
        self.assertIn("vendor.nameLIKEDell", query)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_state_filter_applied(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await list_asset_contracts(self.auth, self.config, {"state": "active"})
        call_kwargs = mock_make_request.call_args
        query = call_kwargs[1]["params"].get("sysparm_query", "")
        self.assertIn("state=active", query)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_contract_type_filter(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await list_asset_contracts(self.auth, self.config, {"contract_type": "Maintenance"})
        call_kwargs = mock_make_request.call_args
        query = call_kwargs[1]["params"].get("sysparm_query", "")
        self.assertIn("contract_type.nameLIKEMaintenance", query)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_short_description_filter(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await list_asset_contracts(self.auth, self.config, {"short_description": "hardware"})
        call_kwargs = mock_make_request.call_args
        query = call_kwargs[1]["params"].get("sysparm_query", "")
        self.assertIn("short_descriptionLIKEhardware", query)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_start_date_from_filter(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await list_asset_contracts(self.auth, self.config, {"start_date_from": "2025-01-01"})
        call_kwargs = mock_make_request.call_args
        query = call_kwargs[1]["params"].get("sysparm_query", "")
        self.assertIn("start_date>=2025-01-01", query)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_end_date_before_filter(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await list_asset_contracts(self.auth, self.config, {"end_date_before": "2026-12-31"})
        call_kwargs = mock_make_request.call_args
        query = call_kwargs[1]["params"].get("sysparm_query", "")
        self.assertIn("end_date<=2026-12-31", query)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_raw_query_filter(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await list_asset_contracts(self.auth, self.config, {"query": "active=true"})
        call_kwargs = mock_make_request.call_args
        query = call_kwargs[1]["params"].get("sysparm_query", "")
        self.assertIn("active=true", query)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_pagination_params(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await list_asset_contracts(self.auth, self.config, {"limit": 5, "offset": 10})
        call_kwargs = mock_make_request.call_args
        qp = call_kwargs[1]["params"]
        self.assertEqual(qp["sysparm_limit"], 5)
        self.assertEqual(qp["sysparm_offset"], 10)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_http_error(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([], 500)
        mock_make_request.return_value.raise_for_status.side_effect = httpx.HTTPError(
            "Server Error"
        )
        result = await list_asset_contracts(self.auth, self.config, {})
        self.assertFalse(result["success"])
        self.assertIn("Error listing asset contracts", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_connection_error(self, mock_make_request):
        mock_make_request.side_effect = httpx.ConnectError("timeout")
        result = await list_asset_contracts(self.auth, self.config, {})
        self.assertFalse(result["success"])
        self.assertIn("Error listing asset contracts", result["message"])

    async def test_list_no_instance_url(self):
        auth = MagicMock(spec=AuthManager)
        auth.get_instance_url = MagicMock(return_value=None)
        auth.instance_url = None
        config = MagicMock(spec=ServerConfig)
        config.instance_url = None
        result = await list_asset_contracts(auth, config, {})
        self.assertFalse(result["success"])

    async def test_list_no_headers(self):
        auth = MagicMock(spec=AuthManager)
        auth.get_instance_url = MagicMock(return_value="https://dev.service-now.com")
        auth.instance_url = "https://dev.service-now.com"
        auth.get_headers = MagicMock(return_value=None)
        auth.get_headers_async = AsyncMock(return_value=None)
        config = MagicMock(spec=ServerConfig)
        config.instance_url = "https://dev.service-now.com"
        result = await list_asset_contracts(auth, config, {})
        self.assertFalse(result["success"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_has_more_pagination(self, mock_make_request):
        contracts = [dict(FAKE_CONTRACT)] * 5
        mock_make_request.return_value = self._mock_response(contracts)
        result = await list_asset_contracts(self.auth, self.config, {"limit": 5, "offset": 0})
        self.assertTrue(result["success"])
        self.assertIn("has_more", result)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_list_multiple_filters_combined(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await list_asset_contracts(
            self.auth,
            self.config,
            {"vendor": "Dell", "state": "active", "start_date_from": "2025-01-01"},
        )
        call_kwargs = mock_make_request.call_args
        query = call_kwargs[1]["params"].get("sysparm_query", "")
        self.assertIn("vendor.nameLIKEDell", query)
        self.assertIn("state=active", query)
        self.assertIn("start_date>=2025-01-01", query)


class TestGetAssetContract(IsolatedAsyncioTestCase):
    def setUp(self):
        self.auth = _make_auth_manager()
        self.config = _make_config()

    def _mock_response(self, data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {"result": data}
        resp.raise_for_status.return_value = None
        return resp

    async def test_no_identifier_returns_error(self):
        result = await get_asset_contract(self.auth, self.config, {})
        self.assertFalse(result["success"])
        self.assertIn("required", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_get_by_sys_id_success(self, mock_make_request):
        mock_make_request.return_value = self._mock_response(FAKE_CONTRACT)
        result = await get_asset_contract(self.auth, self.config, {"sys_id": "con001"})
        self.assertTrue(result["success"])
        self.assertEqual(result["contract"]["number"], "CON0001234")

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_get_by_sys_id_404(self, mock_make_request):
        resp = MagicMock()
        resp.status_code = 404
        mock_make_request.return_value = resp
        result = await get_asset_contract(self.auth, self.config, {"sys_id": "missing001"})
        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_get_by_sys_id_empty_result(self, mock_make_request):
        mock_make_request.return_value = self._mock_response({})
        result = await get_asset_contract(self.auth, self.config, {"sys_id": "con001"})
        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_get_by_number_success(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        result = await get_asset_contract(self.auth, self.config, {"number": "CON0001234"})
        self.assertTrue(result["success"])
        self.assertEqual(result["contract"]["number"], "CON0001234")

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_get_by_number_not_found(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([])
        result = await get_asset_contract(self.auth, self.config, {"number": "CON9999"})
        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_get_by_number_query_includes_number(self, mock_make_request):
        mock_make_request.return_value = self._mock_response([FAKE_CONTRACT])
        await get_asset_contract(self.auth, self.config, {"number": "CON0001234"})
        call_kwargs = mock_make_request.call_args
        qp = call_kwargs[1]["params"]
        self.assertIn("number=CON0001234", qp.get("sysparm_query", ""))
        self.assertEqual(qp.get("sysparm_limit"), "1")

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_get_http_error(self, mock_make_request):
        mock_make_request.return_value = self._mock_response({}, 500)
        mock_make_request.return_value.status_code = 500
        mock_make_request.return_value.raise_for_status.side_effect = httpx.HTTPError(
            "Server Error"
        )
        result = await get_asset_contract(self.auth, self.config, {"sys_id": "con001"})
        self.assertFalse(result["success"])
        self.assertIn("Error retrieving asset contract", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_get_connection_error(self, mock_make_request):
        mock_make_request.side_effect = httpx.ConnectError("timeout")
        result = await get_asset_contract(self.auth, self.config, {"sys_id": "con001"})
        self.assertFalse(result["success"])
        self.assertIn("Error retrieving asset contract", result["message"])

    async def test_get_no_instance_url(self):
        auth = MagicMock(spec=AuthManager)
        auth.get_instance_url = MagicMock(return_value=None)
        auth.instance_url = None
        config = MagicMock(spec=ServerConfig)
        config.instance_url = None
        result = await get_asset_contract(auth, config, {"sys_id": "con001"})
        self.assertFalse(result["success"])

    async def test_get_no_headers(self):
        auth = MagicMock(spec=AuthManager)
        auth.get_instance_url = MagicMock(return_value="https://dev.service-now.com")
        auth.instance_url = "https://dev.service-now.com"
        auth.get_headers = MagicMock(return_value=None)
        auth.get_headers_async = AsyncMock(return_value=None)
        config = MagicMock(spec=ServerConfig)
        config.instance_url = "https://dev.service-now.com"
        result = await get_asset_contract(auth, config, {"sys_id": "con001"})
        self.assertFalse(result["success"])


class TestCreateAssetContract(IsolatedAsyncioTestCase):
    def setUp(self):
        self.auth = _make_auth_manager()
        self.config = _make_config()

    def _mock_response(self, data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {"result": data}
        resp.raise_for_status.return_value = None
        return resp

    async def test_missing_short_description_returns_error(self):
        result = await create_asset_contract(self.auth, self.config, {})
        self.assertFalse(result["success"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_create_success_returns_sys_id_and_contract(self, mock_make_request):
        mock_make_request.return_value = self._mock_response(FAKE_CONTRACT)
        result = await create_asset_contract(
            self.auth, self.config, {"short_description": "Annual maintenance"}
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "con001")
        self.assertIn("contract", result)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_create_posts_to_contract_table(self, mock_make_request):
        mock_make_request.return_value = self._mock_response(FAKE_CONTRACT)
        await create_asset_contract(
            self.auth, self.config, {"short_description": "Test contract"}
        )
        call_args = mock_make_request.call_args
        self.assertEqual(call_args[0][0], "POST")
        self.assertIn("alm_contract", call_args[0][1])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_create_includes_optional_fields_in_body(self, mock_make_request):
        mock_make_request.return_value = self._mock_response(FAKE_CONTRACT)
        await create_asset_contract(
            self.auth,
            self.config,
            {
                "short_description": "Test",
                "vendor": "vendor001",
                "start_date": "2026-01-01",
                "end_date": "2027-01-01",
                "value": "99000",
                "currency": "USD",
                "state": "draft",
            },
        )
        body = mock_make_request.call_args[1]["json"]
        self.assertEqual(body["vendor"], "vendor001")
        self.assertEqual(body["start_date"], "2026-01-01")
        self.assertEqual(body["end_date"], "2027-01-01")
        self.assertEqual(body["value"], "99000")
        self.assertEqual(body["currency"], "USD")
        self.assertEqual(body["state"], "draft")

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_create_omits_none_fields_from_body(self, mock_make_request):
        mock_make_request.return_value = self._mock_response(FAKE_CONTRACT)
        await create_asset_contract(
            self.auth, self.config, {"short_description": "Minimal contract"}
        )
        body = mock_make_request.call_args[1]["json"]
        self.assertNotIn("vendor", body)
        self.assertNotIn("start_date", body)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_create_http_error(self, mock_make_request):
        mock_make_request.return_value = self._mock_response({}, 400)
        mock_make_request.return_value.raise_for_status.side_effect = httpx.HTTPError(
            "Bad Request"
        )
        result = await create_asset_contract(
            self.auth, self.config, {"short_description": "Test"}
        )
        self.assertFalse(result["success"])
        self.assertIn("Error creating asset contract", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_create_connection_error(self, mock_make_request):
        mock_make_request.side_effect = httpx.ConnectError("timeout")
        result = await create_asset_contract(
            self.auth, self.config, {"short_description": "Test"}
        )
        self.assertFalse(result["success"])
        self.assertIn("Error creating asset contract", result["message"])

    async def test_create_no_instance_url(self):
        auth = MagicMock(spec=AuthManager)
        auth.instance_url = None
        config = MagicMock(spec=ServerConfig)
        config.instance_url = None
        result = await create_asset_contract(auth, config, {"short_description": "Test"})
        self.assertFalse(result["success"])

    async def test_create_no_headers(self):
        auth = MagicMock(spec=AuthManager)
        auth.instance_url = "https://dev.service-now.com"
        auth.get_headers = MagicMock(return_value=None)
        auth.get_headers_async = AsyncMock(return_value=None)
        config = MagicMock(spec=ServerConfig)
        config.instance_url = "https://dev.service-now.com"
        result = await create_asset_contract(auth, config, {"short_description": "Test"})
        self.assertFalse(result["success"])


class TestUpdateAssetContract(IsolatedAsyncioTestCase):
    def setUp(self):
        self.auth = _make_auth_manager()
        self.config = _make_config()

    def _mock_response(self, data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {"result": data}
        resp.raise_for_status.return_value = None
        return resp

    async def test_missing_sys_id_returns_error(self):
        result = await update_asset_contract(
            self.auth, self.config, {"short_description": "Updated"}
        )
        self.assertFalse(result["success"])

    async def test_no_update_fields_returns_error(self):
        result = await update_asset_contract(self.auth, self.config, {"sys_id": "con001"})
        self.assertFalse(result["success"])
        self.assertIn("No fields", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_update_success(self, mock_make_request):
        mock_make_request.return_value = self._mock_response(FAKE_CONTRACT)
        result = await update_asset_contract(
            self.auth, self.config, {"sys_id": "con001", "state": "active"}
        )
        self.assertTrue(result["success"])
        self.assertIn("contract", result)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_update_patches_correct_url(self, mock_make_request):
        mock_make_request.return_value = self._mock_response(FAKE_CONTRACT)
        await update_asset_contract(
            self.auth, self.config, {"sys_id": "con001", "value": "12000"}
        )
        call_args = mock_make_request.call_args
        self.assertEqual(call_args[0][0], "PATCH")
        self.assertIn("con001", call_args[0][1])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_update_sends_only_provided_fields(self, mock_make_request):
        mock_make_request.return_value = self._mock_response(FAKE_CONTRACT)
        await update_asset_contract(
            self.auth,
            self.config,
            {"sys_id": "con001", "short_description": "Revised", "currency": "EUR"},
        )
        body = mock_make_request.call_args[1]["json"]
        self.assertEqual(body["short_description"], "Revised")
        self.assertEqual(body["currency"], "EUR")
        self.assertNotIn("vendor", body)

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_update_404_returns_not_found(self, mock_make_request):
        resp = MagicMock()
        resp.status_code = 404
        mock_make_request.return_value = resp
        result = await update_asset_contract(
            self.auth, self.config, {"sys_id": "missing001", "state": "expired"}
        )
        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_update_http_error(self, mock_make_request):
        resp = MagicMock()
        resp.status_code = 500
        resp.raise_for_status.side_effect = httpx.HTTPError("Server Error")
        mock_make_request.return_value = resp
        result = await update_asset_contract(
            self.auth, self.config, {"sys_id": "con001", "state": "active"}
        )
        self.assertFalse(result["success"])
        self.assertIn("Error updating asset contract", result["message"])

    @patch(

        "servicenow_mcp.tools.contract_tools._make_request_async",

        new_callable=AsyncMock,

    )
    async def test_update_connection_error(self, mock_make_request):
        mock_make_request.side_effect = httpx.ConnectError("timeout")
        result = await update_asset_contract(
            self.auth, self.config, {"sys_id": "con001", "state": "active"}
        )
        self.assertFalse(result["success"])
        self.assertIn("Error updating asset contract", result["message"])

    async def test_update_no_instance_url(self):
        auth = MagicMock(spec=AuthManager)
        auth.instance_url = None
        config = MagicMock(spec=ServerConfig)
        config.instance_url = None
        result = await update_asset_contract(
            auth, config, {"sys_id": "con001", "state": "active"}
        )
        self.assertFalse(result["success"])

    async def test_update_no_headers(self):
        auth = MagicMock(spec=AuthManager)
        auth.instance_url = "https://dev.service-now.com"
        auth.get_headers = MagicMock(return_value=None)
        auth.get_headers_async = AsyncMock(return_value=None)
        config = MagicMock(spec=ServerConfig)
        config.instance_url = "https://dev.service-now.com"
        result = await update_asset_contract(
            auth, config, {"sys_id": "con001", "state": "active"}
        )
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()

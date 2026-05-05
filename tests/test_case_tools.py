
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from servicenow_mcp.tools.case_tools import (
    list_cases,
    get_case_by_number,
    search_cases,
    ListCasesParams,
    GetCaseByNumberParams,
    SearchCasesParams,
)
from servicenow_mcp.utils.config import ServerConfig, AuthConfig, AuthType, BasicAuthConfig
from servicenow_mcp.auth.auth_manager import AuthManager


def _make_config():
    auth_config = AuthConfig(type=AuthType.BASIC, basic=BasicAuthConfig(username='test', password='test'))
    return ServerConfig(instance_url="https://dev12345.service-now.com", auth=auth_config)


def _make_auth():
    auth_manager = MagicMock(spec=AuthManager)
    auth_manager.get_headers_async = AsyncMock(return_value={"Authorization": "Bearer FAKE_TOKEN"})
    return auth_manager


def _make_response(json_body=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_body or {})
    return resp


SAMPLE_CASE = {
    "sys_id": "abc123",
    "number": "CS0017600",
    "short_description": "Levy | Wrigley Field | Shift4 Inquiry",
    "description": "Customer needs help with Shift4 integration",
    "state": "New",
    "priority": "3 - Moderate",
    "category": "Inquiry",
    "subcategory": "General",
    "assigned_to": "Jane Smith",
    "contact_type": "email",
    "sys_created_on": "2025-01-15 10:00:00",
    "sys_updated_on": "2025-01-16 08:30:00",
}

SAMPLE_CASE_DICT_ASSIGNED = {
    **SAMPLE_CASE,
    "assigned_to": {"display_value": "Jane Smith", "value": "user_sys_id_123"},
}


class TestListCases(IsolatedAsyncioTestCase):

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_cases_success(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": [SAMPLE_CASE]})

        result = await list_cases(_make_config(), _make_auth(), ListCasesParams())

        self.assertTrue(result["success"])
        self.assertEqual(len(result["cases"]), 1)
        self.assertEqual(result["cases"][0]["number"], "CS0017600")
        call_args = mock_get.call_args
        self.assertIn("/table/task", call_args[0][0])
        self.assertIn("sys_class_name=sn_customerservice_case", call_args[1]["params"]["sysparm_query"])

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_cases_with_filters(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": [SAMPLE_CASE]})

        params = ListCasesParams(
            state="New",
            priority="3 - Moderate",
            category="Inquiry",
            contact_type="email",
            created_after="2025-01-01",
        )
        result = await list_cases(_make_config(), _make_auth(), params)

        self.assertTrue(result["success"])
        query = mock_get.call_args[1]["params"]["sysparm_query"]
        self.assertIn("state=New", query)
        self.assertIn("priority=3 - Moderate", query)
        self.assertIn("category=Inquiry", query)
        self.assertIn("contact_type=email", query)
        self.assertIn("sys_created_on>=2025-01-01", query)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_cases_empty_results(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": []})

        result = await list_cases(_make_config(), _make_auth(), ListCasesParams())

        self.assertTrue(result["success"])
        self.assertEqual(result["cases"], [])
        self.assertEqual(result["message"], "Found 0 cases")

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_cases_request_error(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("Connection timeout")

        result = await list_cases(_make_config(), _make_auth(), ListCasesParams())

        self.assertFalse(result["success"])
        self.assertIn("Failed to list cases", result["message"])
        self.assertEqual(result["cases"], [])

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_cases_limit_cap(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": []})

        await list_cases(_make_config(), _make_auth(), ListCasesParams(limit=500))

        call_params = mock_get.call_args[1]["params"]
        self.assertEqual(call_params["sysparm_limit"], 200)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_cases_assigned_to_dict_handling(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": [SAMPLE_CASE_DICT_ASSIGNED]})

        result = await list_cases(_make_config(), _make_auth(), ListCasesParams())

        self.assertTrue(result["success"])
        self.assertEqual(result["cases"][0]["assigned_to"], "Jane Smith")


class TestGetCaseByNumber(IsolatedAsyncioTestCase):

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_case_by_number_success(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": [SAMPLE_CASE]})

        params = GetCaseByNumberParams(case_number="CS0017600")
        result = await get_case_by_number(_make_config(), _make_auth(), params)

        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "Case CS0017600 found")
        self.assertEqual(result["case"]["number"], "CS0017600")
        self.assertEqual(result["case"]["short_description"], "Levy | Wrigley Field | Shift4 Inquiry")
        query = mock_get.call_args[1]["params"]["sysparm_query"]
        self.assertIn("sys_class_name=sn_customerservice_case", query)
        self.assertIn("number=CS0017600", query)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_case_by_number_not_found(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": []})

        params = GetCaseByNumberParams(case_number="CS9999999")
        result = await get_case_by_number(_make_config(), _make_auth(), params)

        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "Case not found: CS9999999")

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_case_by_number_request_error(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        params = GetCaseByNumberParams(case_number="CS0017600")
        result = await get_case_by_number(_make_config(), _make_auth(), params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to fetch case", result["message"])


class TestSearchCases(IsolatedAsyncioTestCase):

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_search_cases_success(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": [SAMPLE_CASE]})

        params = SearchCasesParams(search_text="Shift4")
        result = await search_cases(_make_config(), _make_auth(), params)

        self.assertTrue(result["success"])
        self.assertEqual(len(result["cases"]), 1)
        self.assertIn("Shift4", result["message"])
        query = mock_get.call_args[1]["params"]["sysparm_query"]
        self.assertIn("short_descriptionLIKEShift4", query)
        self.assertIn("descriptionLIKEShift4", query)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_search_cases_with_filters(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": []})

        params = SearchCasesParams(
            search_text="Shift4",
            state="New",
            priority="3 - Moderate",
            created_after="2025-01-01",
        )
        result = await search_cases(_make_config(), _make_auth(), params)

        self.assertTrue(result["success"])
        query = mock_get.call_args[1]["params"]["sysparm_query"]
        self.assertIn("state=New", query)
        self.assertIn("priority=3 - Moderate", query)
        self.assertIn("sys_created_on>=2025-01-01", query)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_search_cases_limit_cap(self, mock_get):
        mock_get.return_value = _make_response(json_body={"result": []})

        await search_cases(_make_config(), _make_auth(), SearchCasesParams(search_text="test", limit=999))

        call_params = mock_get.call_args[1]["params"]
        self.assertEqual(call_params["sysparm_limit"], 200)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_search_cases_request_error(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("Server error")

        params = SearchCasesParams(search_text="test")
        result = await search_cases(_make_config(), _make_auth(), params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to search cases", result["message"])
        self.assertEqual(result["cases"], [])

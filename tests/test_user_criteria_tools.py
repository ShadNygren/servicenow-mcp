"""
Tests for the User Criteria tools.
"""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from servicenow_mcp.tools.user_criteria_tools import (
    CreateUserCriteriaParams,
    UserCriteriaResponse,
    create_user_criteria,
)
from servicenow_mcp.utils.config import AuthConfig, AuthType, BasicAuthConfig, ServerConfig


def _make_response(json_body=None, status_code=200, raise_exc=None):
    """Build a MagicMock that mimics an httpx.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.headers = {}
    if raise_exc is not None:
        mock.raise_for_status = MagicMock(side_effect=raise_exc)
    else:
        mock.raise_for_status = MagicMock()
    mock.json = MagicMock(return_value=json_body or {})
    return mock


class TestCreateUserCriteria(IsolatedAsyncioTestCase):
    """Tests for the create_user_criteria function."""

    def setUp(self):
        self.config = ServerConfig(
            instance_url="https://test.service-now.com",
            timeout=10,
            auth=AuthConfig(
                type=AuthType.BASIC,
                basic=BasicAuthConfig(username="test_user", password="test_password"),
            ),
        )
        self.auth_manager = MagicMock()
        # Phase 9.2: tools now call get_headers_async, not get_headers.
        self.auth_manager.get_headers_async = AsyncMock(
            return_value={
                "Content-Type": "application/json",
                "Authorization": "Basic dGVzdF91c2VyOnRlc3RfcGFzc3dvcmQ=",
            }
        )

    # ------------------------------------------------------------------
    # Success paths
    # ------------------------------------------------------------------

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_minimal(self, mock_post):
        """Create a user criteria with only the required name field."""
        mock_post.return_value = _make_response(
            json_body={
                "result": {
                    "sys_id": "uc_001",
                    "name": "IT Staff Only",
                    "active": "true",
                    "match_all": "false",
                }
            }
        )

        params = CreateUserCriteriaParams(name="IT Staff Only")
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        self.assertEqual(result.criteria_id, "uc_001")
        self.assertIn("IT Staff Only", result.message)
        self.assertIn("created successfully", result.message)

        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["name"], "IT Staff Only")
        self.assertEqual(sent["active"], "true")
        self.assertEqual(sent["match_all"], "false")
        for field in ("role", "user", "group", "department", "company", "location", "script"):
            self.assertNotIn(field, sent)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_with_role(self, mock_post):
        """Create a user criteria scoped to a specific role."""
        mock_post.return_value = _make_response(
            json_body={"result": {"sys_id": "uc_002", "name": "ITIL Users"}}
        )

        params = CreateUserCriteriaParams(name="ITIL Users", role="role_sys_id_itil")
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        self.assertEqual(result.criteria_id, "uc_002")

        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["role"], "role_sys_id_itil")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_with_group(self, mock_post):
        """Create a user criteria scoped to a user group."""
        mock_post.return_value = _make_response(
            json_body={"result": {"sys_id": "uc_003", "name": "Help Desk Group"}}
        )

        params = CreateUserCriteriaParams(name="Help Desk Group", group="group_sys_id_helpdesk")
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["group"], "group_sys_id_helpdesk")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_with_all_optional_fields(self, mock_post):
        """Create a user criteria with all optional fields populated."""
        mock_post.return_value = _make_response(
            json_body={"result": {"sys_id": "uc_004", "name": "Complex Criteria"}}
        )

        params = CreateUserCriteriaParams(
            name="Complex Criteria",
            active=True,
            match_all=True,
            role="role_id",
            user="user_id",
            group="group_id",
            department="dept_id",
            company="company_id",
            location="location_id",
        )
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["match_all"], "true")
        self.assertEqual(sent["role"], "role_id")
        self.assertEqual(sent["user"], "user_id")
        self.assertEqual(sent["group"], "group_id")
        self.assertEqual(sent["department"], "dept_id")
        self.assertEqual(sent["company"], "company_id")
        self.assertEqual(sent["location"], "location_id")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_with_script(self, mock_post):
        """Create a user criteria that uses an advanced script."""
        mock_post.return_value = _make_response(
            json_body={"result": {"sys_id": "uc_005", "name": "Scripted Criteria"}}
        )

        script = "return gs.getUser().getRecord().getValue('vip') == 'true';"
        params = CreateUserCriteriaParams(name="Scripted Criteria", script=script)
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["script"], script)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_inactive(self, mock_post):
        """Create a user criteria that starts inactive."""
        mock_post.return_value = _make_response(
            json_body={
                "result": {"sys_id": "uc_006", "name": "Draft Criteria", "active": "false"}
            }
        )

        params = CreateUserCriteriaParams(name="Draft Criteria", active=False)
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["active"], "false")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_response_contains_details(self, mock_post):
        """Verify the full result payload is available in response.details."""
        payload = {
            "sys_id": "uc_007",
            "name": "My Criteria",
            "active": "true",
            "match_all": "false",
        }
        mock_post.return_value = _make_response(json_body={"result": payload})

        params = CreateUserCriteriaParams(name="My Criteria")
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertIsNotNone(result.details)
        self.assertEqual(result.details["sys_id"], "uc_007")
        self.assertEqual(result.details["name"], "My Criteria")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_api_url_correct(self, mock_post):
        """Verify the correct ServiceNow table endpoint is called."""
        mock_post.return_value = _make_response(json_body={"result": {"sys_id": "uc_008"}})

        params = CreateUserCriteriaParams(name="URL Check")
        await create_user_criteria(self.config, self.auth_manager, params)

        call_url = mock_post.call_args.args[0]
        self.assertEqual(
            call_url, "https://test.service-now.com/api/now/table/user_criteria"
        )

    # ------------------------------------------------------------------
    # Failure paths
    # ------------------------------------------------------------------

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_http_error_returns_failure(self, mock_post):
        """HTTP 4xx/5xx should return a failed response, not raise."""
        mock_post.return_value = _make_response(
            status_code=403,
            raise_exc=httpx.HTTPStatusError(
                "403 Forbidden",
                request=httpx.Request("POST", "https://test.service-now.com/x"),
                response=httpx.Response(403),
            ),
        )

        params = CreateUserCriteriaParams(name="Forbidden Criteria")
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertFalse(result.success)
        self.assertIn("Failed to create user criteria", result.message)
        self.assertIsNone(result.criteria_id)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_connection_error_returns_failure(self, mock_post):
        """Network-level errors should return a failed response."""
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        params = CreateUserCriteriaParams(name="Network Error Criteria")
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertFalse(result.success)
        self.assertIn("Failed to create user criteria", result.message)
        self.assertIsNone(result.criteria_id)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_timeout_error_returns_failure(self, mock_post):
        """Timeout errors should return a failed response."""
        mock_post.side_effect = httpx.ReadTimeout("Request timed out")

        params = CreateUserCriteriaParams(name="Timeout Criteria")
        result = await create_user_criteria(self.config, self.auth_manager, params)

        self.assertFalse(result.success)
        self.assertIn("Failed to create user criteria", result.message)

    # ------------------------------------------------------------------
    # Pydantic model validation (no I/O — unchanged from sync version)
    # ------------------------------------------------------------------

    def test_params_defaults(self):
        """Verify CreateUserCriteriaParams defaults are applied correctly."""
        params = CreateUserCriteriaParams(name="Defaults Test")
        self.assertEqual(params.name, "Defaults Test")
        self.assertTrue(params.active)
        self.assertFalse(params.match_all)
        self.assertIsNone(params.role)
        self.assertIsNone(params.user)
        self.assertIsNone(params.group)
        self.assertIsNone(params.department)
        self.assertIsNone(params.company)
        self.assertIsNone(params.location)
        self.assertIsNone(params.script)

    def test_response_model_success(self):
        """Verify UserCriteriaResponse can be constructed for a success case."""
        resp = UserCriteriaResponse(
            success=True,
            message="Created",
            criteria_id="abc123",
            details={"sys_id": "abc123"},
        )
        self.assertTrue(resp.success)
        self.assertEqual(resp.criteria_id, "abc123")

    def test_response_model_failure(self):
        """Verify UserCriteriaResponse can be constructed for a failure case."""
        resp = UserCriteriaResponse(
            success=False,
            message="Something went wrong",
        )
        self.assertFalse(resp.success)
        self.assertIsNone(resp.criteria_id)
        self.assertIsNone(resp.details)

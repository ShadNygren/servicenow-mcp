"""
Tests for the UI policy tools.
"""

import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from servicenow_mcp.tools.ui_policy_tools import (
    CreateUIPolicyParams,
    UIPolicyResponse,
    create_ui_policy,
    CreateUIPolicyActionParams,
    UIPolicyActionResponse,
    create_ui_policy_action,
)
from servicenow_mcp.utils.config import AuthConfig, AuthType, BasicAuthConfig, ServerConfig


def _make_response(json_body=None, raise_exc=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    if raise_exc is not None:
        resp.raise_for_status = MagicMock(side_effect=raise_exc)
    else:
        resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_body or {})
    return resp


class TestCreateUIPolicy(IsolatedAsyncioTestCase):
    """Tests for the create_ui_policy function."""

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
        self.auth_manager.get_headers_async = AsyncMock(
            return_value={"Content-Type": "application/json"}
        )

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_ui_policy_minimal(self, mock_post):
        """Create a UI policy with only required fields."""
        mock_post.return_value = _make_response(
            json_body={
                "result": {
                    "sys_id": "ui_pol_001",
                    "name": "Hide field on low priority",
                    "table_name": "incident",
                    "active": "true",
                }
            }
        )

        params = CreateUIPolicyParams(
            name="Hide field on low priority",
            table_name="incident",
        )
        result = await create_ui_policy(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        self.assertEqual(result.policy_id, "ui_pol_001")
        self.assertIn("created successfully", result.message)

        call_args = mock_post.call_args
        sent_data = call_args.kwargs["json"]
        self.assertEqual(sent_data["name"], "Hide field on low priority")
        self.assertEqual(sent_data["table_name"], "incident")
        self.assertEqual(sent_data["active"], "true")
        self.assertEqual(sent_data["on_load"], "true")
        self.assertEqual(sent_data["reverse_if_false"], "true")
        self.assertEqual(sent_data["run_scripts"], "false")
        self.assertNotIn("conditions", sent_data)
        self.assertNotIn("short_description", sent_data)
        self.assertNotIn("catalog_item", sent_data)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_ui_policy_with_all_fields(self, mock_post):
        """Create a UI policy with all optional fields populated."""
        mock_post.return_value = _make_response(
            json_body={
                "result": {
                    "sys_id": "ui_pol_002",
                    "name": "Require approval notes",
                    "table_name": "change_request",
                }
            }
        )

        params = CreateUIPolicyParams(
            name="Require approval notes",
            table_name="change_request",
            active=True,
            on_load=False,
            reverse_if_false=False,
            conditions="risk=3^state=2",
            short_description="Make notes mandatory on high-risk changes",
            run_scripts=True,
        )
        result = await create_ui_policy(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        self.assertEqual(result.policy_id, "ui_pol_002")

        sent_data = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_data["conditions"], "risk=3^state=2")
        self.assertEqual(sent_data["short_description"], "Make notes mandatory on high-risk changes")
        self.assertEqual(sent_data["on_load"], "false")
        self.assertEqual(sent_data["reverse_if_false"], "false")
        self.assertEqual(sent_data["run_scripts"], "true")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_ui_policy_for_catalog_item(self, mock_post):
        """Create a catalog-scoped UI policy with a catalog_item_id."""
        mock_post.return_value = _make_response(
            json_body={
                "result": {
                    "sys_id": "ui_pol_003",
                    "name": "Show notes on select",
                    "table_name": "sc_cat_item",
                    "catalog_item": "cat_item_abc",
                }
            }
        )

        params = CreateUIPolicyParams(
            name="Show notes on select",
            table_name="sc_cat_item",
            catalog_item_id="cat_item_abc",
            conditions="selection=yes",
        )
        result = await create_ui_policy(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        sent_data = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_data["catalog_item"], "cat_item_abc")
        self.assertEqual(sent_data["conditions"], "selection=yes")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_ui_policy_http_error(self, mock_post):
        """Returns failure response on HTTP error."""
        mock_post.return_value = _make_response(
            raise_exc=httpx.HTTPStatusError(
                "403 Forbidden",
                request=httpx.Request("POST", "https://test.service-now.com/x"),
                response=httpx.Response(403),
            )
        )

        params = CreateUIPolicyParams(name="Bad policy", table_name="incident")
        result = await create_ui_policy(self.config, self.auth_manager, params)

        self.assertFalse(result.success)
        self.assertIn("Failed to create UI policy", result.message)
        self.assertIsNone(result.policy_id)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_ui_policy_connection_error(self, mock_post):
        """Returns failure response on connection error."""
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        params = CreateUIPolicyParams(name="Unreachable policy", table_name="incident")
        result = await create_ui_policy(self.config, self.auth_manager, params)

        self.assertFalse(result.success)
        self.assertIn("Failed to create UI policy", result.message)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_ui_policy_inactive(self, mock_post):
        """Create an inactive UI policy."""
        mock_post.return_value = _make_response(
            json_body={
                "result": {"sys_id": "ui_pol_004", "name": "Draft policy", "active": "false"}
            }
        )

        params = CreateUIPolicyParams(name="Draft policy", table_name="problem", active=False)
        result = await create_ui_policy(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        sent_data = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_data["active"], "false")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_ui_policy_posts_to_correct_endpoint(self, mock_post):
        """Verifies the request targets sys_ui_policy table."""
        mock_post.return_value = _make_response(json_body={"result": {"sys_id": "x"}})

        params = CreateUIPolicyParams(name="P", table_name="incident")
        await create_ui_policy(self.config, self.auth_manager, params)

        url = mock_post.call_args.args[0]
        self.assertIn("/api/now/table/sys_ui_policy", url)

    def test_ui_policy_response_model(self):
        """UIPolicyResponse can be constructed with all fields."""
        r = UIPolicyResponse(
            success=True,
            message="ok",
            policy_id="abc",
            details={"key": "value"},
        )
        self.assertTrue(r.success)
        self.assertEqual(r.policy_id, "abc")

    def test_create_ui_policy_params_defaults(self):
        """Default values for optional boolean fields."""
        params = CreateUIPolicyParams(name="P", table_name="incident")
        self.assertTrue(params.active)
        self.assertTrue(params.on_load)
        self.assertTrue(params.reverse_if_false)
        self.assertFalse(params.run_scripts)
        self.assertIsNone(params.conditions)
        self.assertIsNone(params.short_description)
        self.assertIsNone(params.catalog_item_id)


class TestCreateUIPolicyAction(IsolatedAsyncioTestCase):
    """Tests for the create_ui_policy_action function."""

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
        self.auth_manager.get_headers_async = AsyncMock(
            return_value={"Content-Type": "application/json"}
        )

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_action_defaults(self, mock_post):
        """Create an action with only required fields; behaviour fields default to leave_alone."""
        mock_post.return_value = _make_response(
            json_body={
                "result": {
                    "sys_id": "action_001",
                    "ui_policy": "pol_001",
                    "field_name": "priority",
                }
            }
        )

        params = CreateUIPolicyActionParams(
            ui_policy_id="pol_001",
            field_name="priority",
        )
        result = await create_ui_policy_action(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        self.assertEqual(result.action_id, "action_001")
        self.assertIn("priority", result.message)
        self.assertIn("created successfully", result.message)

        sent_data = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_data["ui_policy"], "pol_001")
        self.assertEqual(sent_data["field_name"], "priority")
        self.assertEqual(sent_data["mandatory"], "leave_alone")
        self.assertEqual(sent_data["visible"], "leave_alone")
        self.assertEqual(sent_data["disabled"], "leave_alone")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_action_make_mandatory_and_visible(self, mock_post):
        """Create an action that forces a field to be mandatory and visible."""
        mock_post.return_value = _make_response(
            json_body={"result": {"sys_id": "action_002", "field_name": "approval_notes"}}
        )

        params = CreateUIPolicyActionParams(
            ui_policy_id="pol_002",
            field_name="approval_notes",
            mandatory="true",
            visible="true",
            disabled="false",
        )
        result = await create_ui_policy_action(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        self.assertEqual(result.action_id, "action_002")

        sent_data = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_data["mandatory"], "true")
        self.assertEqual(sent_data["visible"], "true")
        self.assertEqual(sent_data["disabled"], "false")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_action_hide_field(self, mock_post):
        """Create an action that hides a field and makes it read-only."""
        mock_post.return_value = _make_response(
            json_body={"result": {"sys_id": "action_003", "field_name": "close_code"}}
        )

        params = CreateUIPolicyActionParams(
            ui_policy_id="pol_003",
            field_name="close_code",
            visible="false",
            disabled="true",
        )
        result = await create_ui_policy_action(self.config, self.auth_manager, params)

        self.assertTrue(result.success)
        sent_data = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_data["visible"], "false")
        self.assertEqual(sent_data["disabled"], "true")

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_action_posts_to_correct_endpoint(self, mock_post):
        """Verifies the request targets sys_ui_policy_action table."""
        mock_post.return_value = _make_response(json_body={"result": {"sys_id": "x"}})

        params = CreateUIPolicyActionParams(ui_policy_id="pol_x", field_name="state")
        await create_ui_policy_action(self.config, self.auth_manager, params)

        url = mock_post.call_args.args[0]
        self.assertIn("/api/now/table/sys_ui_policy_action", url)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_action_http_error(self, mock_post):
        """Returns failure response on HTTP error."""
        mock_post.return_value = _make_response(
            raise_exc=httpx.HTTPStatusError(
                "403 Forbidden",
                request=httpx.Request("POST", "https://test.service-now.com/x"),
                response=httpx.Response(403),
            )
        )

        params = CreateUIPolicyActionParams(ui_policy_id="pol_x", field_name="state")
        result = await create_ui_policy_action(self.config, self.auth_manager, params)

        self.assertFalse(result.success)
        self.assertIn("Failed to create UI policy action", result.message)
        self.assertIsNone(result.action_id)

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_action_connection_error(self, mock_post):
        """Returns failure response on connection error."""
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        params = CreateUIPolicyActionParams(ui_policy_id="pol_x", field_name="state")
        result = await create_ui_policy_action(self.config, self.auth_manager, params)

        self.assertFalse(result.success)
        self.assertIn("Failed to create UI policy action", result.message)

    def test_action_params_defaults(self):
        """Default behaviour values are leave_alone."""
        params = CreateUIPolicyActionParams(ui_policy_id="p", field_name="f")
        self.assertEqual(params.mandatory, "leave_alone")
        self.assertEqual(params.visible, "leave_alone")
        self.assertEqual(params.disabled, "leave_alone")

    def test_action_response_model(self):
        """UIPolicyActionResponse can be constructed with all fields."""
        r = UIPolicyActionResponse(
            success=True,
            message="ok",
            action_id="abc",
            details={"key": "value"},
        )
        self.assertTrue(r.success)
        self.assertEqual(r.action_id, "abc")

    def test_action_params_invalid_behaviour_rejected(self):
        """Invalid behaviour literal values are rejected by Pydantic."""
        with self.assertRaises(Exception):
            CreateUIPolicyActionParams(
                ui_policy_id="p",
                field_name="f",
                mandatory="maybe",  # not a valid FieldBehaviour
            )

    @patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
    async def test_create_action_result_details_populated(self, mock_post):
        """Details field in response contains the full ServiceNow result."""
        payload = {
            "sys_id": "action_010",
            "ui_policy": "pol_010",
            "field_name": "category",
            "mandatory": "true",
        }
        mock_post.return_value = _make_response(json_body={"result": payload})

        params = CreateUIPolicyActionParams(
            ui_policy_id="pol_010",
            field_name="category",
            mandatory="true",
        )
        result = await create_ui_policy_action(self.config, self.auth_manager, params)

        self.assertEqual(result.details, payload)


if __name__ == "__main__":
    unittest.main()

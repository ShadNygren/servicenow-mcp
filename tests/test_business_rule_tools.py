"""
Tests for the business rule tools.

This module contains tests for the business rule tools in the ServiceNow MCP server.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.business_rule_tools import (
    CreateBusinessRuleParams,
    ListBusinessRulesParams,
    GetBusinessRuleParams,
    UpdateBusinessRuleParams,
    DeleteBusinessRuleParams,
    create_business_rule,
    list_business_rules,
    get_business_rule,
    update_business_rule,
    delete_business_rule,
)
from servicenow_mcp.utils.config import ServerConfig, AuthConfig, AuthType, BasicAuthConfig


class TestBusinessRuleTools(unittest.TestCase):
    """Tests for the business rule tools."""

    def setUp(self):
        """Set up test fixtures."""
        auth_config = AuthConfig(
            type=AuthType.BASIC,
            basic=BasicAuthConfig(
                username="test_user",
                password="test_password",
            ),
        )
        self.server_config = ServerConfig(
            instance_url="https://test.service-now.com",
            auth=auth_config,
        )
        self.auth_manager = MagicMock(spec=AuthManager)
        self.auth_manager.get_headers.return_value = {
            "Authorization": "Bearer test",
            "Content-Type": "application/json",
        }

    def _mock_response(self, status_code=200, json_data=None):
        """Create a mock response object."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data or {}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    # ------------------------------------------------------------------
    # create_business_rule
    # ------------------------------------------------------------------

    @patch("requests.post")
    def test_create_business_rule_success(self, mock_post):
        """Test successfully creating a business rule."""
        mock_post.return_value = self._mock_response(
            status_code=201,
            json_data={
                "result": {
                    "sys_id": "abc123",
                    "name": "Validate CI",
                    "collection": "cmdb_ci",
                    "when": "before",
                    "active": "true",
                }
            },
        )

        params = CreateBusinessRuleParams(
            name="Validate CI",
            table="cmdb_ci",
            script="current.update();",
            when="before",
            insert=True,
            update=True,
            active=True,
            description="Validates CI records before insert/update",
        )
        result = create_business_rule(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "abc123")
        self.assertEqual(result["name"], "Validate CI")
        self.assertEqual(result["table"], "cmdb_ci")
        self.assertIn("Created business rule", result["message"])

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(
            args[0],
            "https://test.service-now.com/api/now/table/sys_script",
        )
        self.assertEqual(kwargs["json"]["name"], "Validate CI")
        self.assertEqual(kwargs["json"]["collection"], "cmdb_ci")
        self.assertEqual(kwargs["json"]["script"], "current.update();")
        self.assertEqual(kwargs["json"]["when"], "before")
        self.assertEqual(kwargs["json"]["action_insert"], "true")
        self.assertEqual(kwargs["json"]["action_update"], "true")
        self.assertEqual(kwargs["json"]["comments"], "Validates CI records before insert/update")

    @patch("requests.post")
    def test_create_business_rule_error(self, mock_post):
        """Test creating a business rule with a RequestException."""
        mock_post.side_effect = requests.RequestException("Connection error")

        params = CreateBusinessRuleParams(
            name="Failing Rule",
            table="incident",
            script="gs.log('test');",
        )
        result = create_business_rule(self.server_config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to create business rule", result["message"])
        self.assertIsNone(result["sys_id"])
        self.assertEqual(result["record"], {})

    # ------------------------------------------------------------------
    # list_business_rules
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_list_business_rules_success(self, mock_get):
        """Test successfully listing business rules."""
        mock_get.return_value = self._mock_response(
            json_data={
                "result": [
                    {
                        "sys_id": "rule1",
                        "name": "Rule One",
                        "collection": "incident",
                        "when": "after",
                        "action_insert": "true",
                        "action_update": "false",
                        "action_delete": "false",
                        "action_query": "false",
                        "order": "100",
                        "active": "true",
                        "filter_condition": "",
                        "sys_updated_on": "2024-01-01 00:00:00",
                    },
                    {
                        "sys_id": "rule2",
                        "name": "Rule Two",
                        "collection": "incident",
                        "when": "before",
                        "action_insert": "false",
                        "action_update": "true",
                        "action_delete": "false",
                        "action_query": "false",
                        "order": "200",
                        "active": "true",
                        "filter_condition": "priority=1",
                        "sys_updated_on": "2024-02-01 00:00:00",
                    },
                ]
            },
        )

        params = ListBusinessRulesParams(
            table="incident",
            active_only=True,
            limit=10,
            offset=0,
        )
        result = list_business_rules(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["rules"]), 2)
        self.assertEqual(result["rules"][0]["sys_id"], "rule1")
        self.assertEqual(result["rules"][0]["name"], "Rule One")
        self.assertEqual(result["rules"][1]["sys_id"], "rule2")

        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertIn("collection=incident", kwargs["params"]["sysparm_query"])
        self.assertIn("active=true", kwargs["params"]["sysparm_query"])

    # ------------------------------------------------------------------
    # get_business_rule
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_get_business_rule_success(self, mock_get):
        """Test successfully getting a single business rule."""
        mock_get.return_value = self._mock_response(
            json_data={
                "result": {
                    "sys_id": "abc123",
                    "name": "Validate CI",
                    "collection": "cmdb_ci",
                    "script": "current.update();",
                    "when": "before",
                    "action_insert": "true",
                    "action_update": "true",
                    "action_delete": "false",
                    "action_query": "false",
                    "order": "100",
                    "active": "true",
                    "filter_condition": "",
                    "comments": "Validates CI records",
                    "sys_updated_on": "2024-01-01 00:00:00",
                }
            },
        )

        params = GetBusinessRuleParams(sys_id="abc123")
        result = get_business_rule(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertIn("Retrieved business rule", result["message"])
        rule = result["rule"]
        self.assertEqual(rule["sys_id"], "abc123")
        self.assertEqual(rule["name"], "Validate CI")
        self.assertEqual(rule["table"], "cmdb_ci")
        self.assertEqual(rule["script"], "current.update();")
        self.assertEqual(rule["description"], "Validates CI records")

        mock_get.assert_called_once()
        args, _ = mock_get.call_args
        self.assertIn("abc123", args[0])

    # ------------------------------------------------------------------
    # update_business_rule
    # ------------------------------------------------------------------

    @patch("requests.patch")
    def test_update_business_rule_success(self, mock_patch):
        """Test successfully updating a business rule."""
        mock_patch.return_value = self._mock_response(
            json_data={
                "result": {
                    "sys_id": "abc123",
                    "name": "Validate CI v2",
                    "active": "true",
                }
            },
        )

        params = UpdateBusinessRuleParams(
            sys_id="abc123",
            name="Validate CI v2",
            script="current.setValue('state', 'active'); current.update();",
            active=True,
        )
        result = update_business_rule(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "abc123")
        self.assertIn("Updated business rule", result["message"])

        mock_patch.assert_called_once()
        args, kwargs = mock_patch.call_args
        self.assertIn("abc123", args[0])
        self.assertEqual(kwargs["json"]["name"], "Validate CI v2")
        self.assertEqual(kwargs["json"]["active"], "true")

    # ------------------------------------------------------------------
    # delete_business_rule
    # ------------------------------------------------------------------

    @patch("requests.delete")
    def test_delete_business_rule_success(self, mock_delete):
        """Test successfully deleting a business rule."""
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status.return_value = None
        mock_delete.return_value = mock_resp

        params = DeleteBusinessRuleParams(sys_id="abc123")
        result = delete_business_rule(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "abc123")
        self.assertIn("Deleted business rule", result["message"])

        mock_delete.assert_called_once()
        args, _ = mock_delete.call_args
        self.assertEqual(
            args[0],
            "https://test.service-now.com/api/now/table/sys_script/abc123",
        )


if __name__ == "__main__":
    unittest.main()

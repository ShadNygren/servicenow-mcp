import unittest
from unittest.mock import MagicMock, patch

import requests

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.rest_message_tools import (
    CreateHttpMethodParams,
    CreateRestMessageParams,
    DeleteRestMessageParams,
    GetRestMessageParams,
    ListHttpMethodsParams,
    ListRestMessagesParams,
    UpdateRestMessageParams,
    create_http_method,
    create_rest_message,
    delete_rest_message,
    get_rest_message,
    list_http_methods,
    list_rest_messages,
    update_rest_message,
)
from servicenow_mcp.utils.config import AuthConfig, AuthType, BasicAuthConfig, ServerConfig


class TestRestMessageTools(unittest.TestCase):

    def setUp(self):
        self.auth_config = AuthConfig(
            type=AuthType.BASIC,
            basic=BasicAuthConfig(username="test", password="test"),
        )
        self.config = ServerConfig(
            instance_url="https://dev12345.service-now.com",
            auth=self.auth_config,
        )
        self.auth_manager = MagicMock(spec=AuthManager)
        self.auth_manager.get_headers.return_value = {
            "Authorization": "Bearer FAKE_TOKEN"
        }

    # ------------------------------------------------------------------
    # create_rest_message
    # ------------------------------------------------------------------

    @patch("requests.post")
    def test_create_rest_message_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "result": {
                "sys_id": "abc123",
                "name": "FNT Command API",
                "rest_endpoint": "https://fnt-host/api",
                "authentication_type": "no_authentication",
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        params = CreateRestMessageParams(
            name="FNT Command API",
            rest_endpoint="https://fnt-host/api",
        )
        result = create_rest_message(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "abc123")
        self.assertEqual(result["name"], "FNT Command API")
        self.assertIn("Created REST Message", result["message"])
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_create_rest_message_error(self, mock_post):
        mock_post.side_effect = requests.RequestException("Connection error")

        params = CreateRestMessageParams(
            name="FNT Command API",
            rest_endpoint="https://fnt-host/api",
        )
        result = create_rest_message(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to create REST Message", result["message"])
        self.assertIsNone(result["sys_id"])

    # ------------------------------------------------------------------
    # list_rest_messages
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_list_rest_messages_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                {
                    "sys_id": "abc123",
                    "name": "FNT Command API",
                    "rest_endpoint": "https://fnt-host/api",
                    "authentication_type": "no_authentication",
                    "description": "FNT integration",
                    "use_mid_server": "false",
                    "sys_updated_on": "2025-06-25 10:00:00",
                },
                {
                    "sys_id": "def456",
                    "name": "Another API",
                    "rest_endpoint": "https://other-host/api",
                    "authentication_type": "basic",
                    "description": "",
                    "use_mid_server": "false",
                    "sys_updated_on": "2025-06-26 12:00:00",
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        params = ListRestMessagesParams(limit=20, offset=0)
        result = list_rest_messages(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["rest_messages"]), 2)
        self.assertEqual(result["rest_messages"][0]["sys_id"], "abc123")
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_list_rest_messages_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("Timeout")

        params = ListRestMessagesParams()
        result = list_rest_messages(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to list REST Messages", result["message"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["rest_messages"], [])

    # ------------------------------------------------------------------
    # get_rest_message
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_get_rest_message_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "sys_id": "abc123",
                "name": "FNT Command API",
                "rest_endpoint": "https://fnt-host/api",
                "authentication_type": "no_authentication",
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        params = GetRestMessageParams(sys_id="abc123")
        result = get_rest_message(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["rest_message"]["sys_id"], "abc123")
        self.assertEqual(result["rest_message"]["name"], "FNT Command API")
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_get_rest_message_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("Not found")

        params = GetRestMessageParams(sys_id="abc123")
        result = get_rest_message(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to get REST Message", result["message"])
        self.assertEqual(result["rest_message"], {})

    # ------------------------------------------------------------------
    # update_rest_message
    # ------------------------------------------------------------------

    @patch("requests.patch")
    def test_update_rest_message_success(self, mock_patch):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "sys_id": "abc123",
                "name": "Updated API",
                "rest_endpoint": "https://fnt-host/api/v2",
                "authentication_type": "basic",
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_patch.return_value = mock_response

        params = UpdateRestMessageParams(
            sys_id="abc123",
            name="Updated API",
            rest_endpoint="https://fnt-host/api/v2",
        )
        result = update_rest_message(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "abc123")
        self.assertIn("Updated REST Message", result["message"])
        mock_patch.assert_called_once()

    @patch("requests.patch")
    def test_update_rest_message_error(self, mock_patch):
        mock_patch.side_effect = requests.RequestException("Server error")

        params = UpdateRestMessageParams(sys_id="abc123", name="Updated API")
        result = update_rest_message(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to update REST Message", result["message"])
        self.assertEqual(result["record"], {})

    # ------------------------------------------------------------------
    # delete_rest_message
    # ------------------------------------------------------------------

    @patch("requests.delete")
    def test_delete_rest_message_success(self, mock_delete):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status.return_value = None
        mock_delete.return_value = mock_response

        params = DeleteRestMessageParams(sys_id="abc123")
        result = delete_rest_message(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "abc123")
        self.assertIn("Deleted REST Message", result["message"])
        mock_delete.assert_called_once()

    @patch("requests.delete")
    def test_delete_rest_message_error(self, mock_delete):
        mock_delete.side_effect = requests.RequestException("Forbidden")

        params = DeleteRestMessageParams(sys_id="abc123")
        result = delete_rest_message(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to delete REST Message", result["message"])
        self.assertEqual(result["sys_id"], "abc123")

    # ------------------------------------------------------------------
    # create_http_method
    # ------------------------------------------------------------------

    @patch("requests.post")
    def test_create_http_method_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "result": {
                "sys_id": "method789",
                "function_name": "Update CI",
                "http_method": "PUT",
                "rest_endpoint": "/object/${elid}",
                "rest_message": "abc123",
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        params = CreateHttpMethodParams(
            rest_message_sys_id="abc123",
            name="Update CI",
            http_method="PUT",
            rest_endpoint="/object/${elid}",
        )
        result = create_http_method(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "method789")
        self.assertEqual(result["name"], "Update CI")
        self.assertEqual(result["http_method"], "PUT")
        self.assertIn("Created HTTP Method", result["message"])
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_create_http_method_error(self, mock_post):
        mock_post.side_effect = requests.RequestException("Connection refused")

        params = CreateHttpMethodParams(
            rest_message_sys_id="abc123",
            name="Update CI",
            http_method="PUT",
            rest_endpoint="/object/${elid}",
        )
        result = create_http_method(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to create HTTP Method", result["message"])
        self.assertIsNone(result["sys_id"])

    # ------------------------------------------------------------------
    # list_http_methods
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_list_http_methods_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                {
                    "sys_id": "method789",
                    "function_name": "Update CI",
                    "http_method": "PUT",
                    "rest_endpoint": "/object/${elid}",
                    "authentication_type": "",
                    "sys_updated_on": "2025-06-25 10:00:00",
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        params = ListHttpMethodsParams(rest_message_sys_id="abc123")
        result = list_http_methods(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(len(result["methods"]), 1)
        self.assertEqual(result["methods"][0]["sys_id"], "method789")
        self.assertEqual(result["methods"][0]["name"], "Update CI")
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_list_http_methods_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("Timeout")

        params = ListHttpMethodsParams(rest_message_sys_id="abc123")
        result = list_http_methods(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to list HTTP Methods", result["message"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["methods"], [])


if __name__ == "__main__":
    unittest.main()

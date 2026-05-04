import unittest
from unittest.mock import MagicMock, patch

import requests

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.oauth_tools import (
    CreateOAuthEntityParams,
    CreateOAuthProfileParams,
    DeleteOAuthEntityParams,
    GetOAuthEntityParams,
    ListOAuthEntitiesParams,
    ListOAuthProfilesParams,
    UpdateOAuthEntityParams,
    create_oauth_entity,
    create_oauth_profile,
    delete_oauth_entity,
    get_oauth_entity,
    list_oauth_entities,
    list_oauth_profiles,
    update_oauth_entity,
)
from servicenow_mcp.utils.config import AuthConfig, AuthType, BasicAuthConfig, ServerConfig


class TestOAuthTools(unittest.TestCase):

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
    # create_oauth_entity
    # ------------------------------------------------------------------

    @patch("requests.post")
    def test_create_oauth_entity_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "result": {
                "sys_id": "oauth_entity_001",
                "name": "FNT Command OAuth",
                "client_id": "my_client_id",
                "token_url": "https://fnt-host/api/oauth/token",
                "default_grant_type": "client_credentials",
                "active": "true",
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        params = CreateOAuthEntityParams(
            name="FNT Command OAuth",
            client_id="my_client_id",
            client_secret="my_client_secret",
            token_url="https://fnt-host/api/oauth/token",
        )
        result = create_oauth_entity(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "oauth_entity_001")
        self.assertEqual(result["name"], "FNT Command OAuth")
        self.assertIn("Created OAuth Entity", result["message"])
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_create_oauth_entity_error(self, mock_post):
        mock_post.side_effect = requests.RequestException("Connection error")

        params = CreateOAuthEntityParams(
            name="FNT Command OAuth",
            client_id="my_client_id",
            client_secret="my_client_secret",
            token_url="https://fnt-host/api/oauth/token",
        )
        result = create_oauth_entity(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to create OAuth Entity", result["message"])
        self.assertIsNone(result["sys_id"])

    # ------------------------------------------------------------------
    # list_oauth_entities
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_list_oauth_entities_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                {
                    "sys_id": "oauth_entity_001",
                    "name": "FNT Command OAuth",
                    "client_id": "my_client_id",
                    "token_url": "https://fnt-host/api/oauth/token",
                    "auth_url": "",
                    "default_grant_type": "client_credentials",
                    "active": "true",
                    "sys_updated_on": "2025-06-25 10:00:00",
                },
                {
                    "sys_id": "oauth_entity_002",
                    "name": "Other OAuth App",
                    "client_id": "other_client",
                    "token_url": "https://other-host/token",
                    "auth_url": "",
                    "default_grant_type": "password",
                    "active": "true",
                    "sys_updated_on": "2025-06-26 12:00:00",
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        params = ListOAuthEntitiesParams(limit=20, offset=0)
        result = list_oauth_entities(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["entities"]), 2)
        self.assertEqual(result["entities"][0]["sys_id"], "oauth_entity_001")
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_list_oauth_entities_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("Timeout")

        params = ListOAuthEntitiesParams()
        result = list_oauth_entities(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to list OAuth Entities", result["message"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["entities"], [])

    # ------------------------------------------------------------------
    # get_oauth_entity
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_get_oauth_entity_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "sys_id": "oauth_entity_001",
                "name": "FNT Command OAuth",
                "client_id": "my_client_id",
                "token_url": "https://fnt-host/api/oauth/token",
                "default_grant_type": "client_credentials",
                "active": "true",
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        params = GetOAuthEntityParams(sys_id="oauth_entity_001")
        result = get_oauth_entity(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["entity"]["sys_id"], "oauth_entity_001")
        self.assertEqual(result["entity"]["name"], "FNT Command OAuth")
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_get_oauth_entity_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("Not found")

        params = GetOAuthEntityParams(sys_id="oauth_entity_001")
        result = get_oauth_entity(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to get OAuth Entity", result["message"])
        self.assertEqual(result["entity"], {})

    # ------------------------------------------------------------------
    # update_oauth_entity
    # ------------------------------------------------------------------

    @patch("requests.patch")
    def test_update_oauth_entity_success(self, mock_patch):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "sys_id": "oauth_entity_001",
                "name": "Updated OAuth App",
                "client_id": "new_client_id",
                "token_url": "https://fnt-host/api/oauth/token",
                "default_grant_type": "client_credentials",
                "active": "true",
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_patch.return_value = mock_response

        params = UpdateOAuthEntityParams(
            sys_id="oauth_entity_001",
            name="Updated OAuth App",
            client_id="new_client_id",
        )
        result = update_oauth_entity(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "oauth_entity_001")
        self.assertIn("Updated OAuth Entity", result["message"])
        mock_patch.assert_called_once()

    @patch("requests.patch")
    def test_update_oauth_entity_error(self, mock_patch):
        mock_patch.side_effect = requests.RequestException("Server error")

        params = UpdateOAuthEntityParams(
            sys_id="oauth_entity_001",
            name="Updated OAuth App",
        )
        result = update_oauth_entity(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to update OAuth Entity", result["message"])
        self.assertEqual(result["record"], {})

    # ------------------------------------------------------------------
    # delete_oauth_entity
    # ------------------------------------------------------------------

    @patch("requests.delete")
    def test_delete_oauth_entity_success(self, mock_delete):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status.return_value = None
        mock_delete.return_value = mock_response

        params = DeleteOAuthEntityParams(sys_id="oauth_entity_001")
        result = delete_oauth_entity(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "oauth_entity_001")
        self.assertIn("Deleted OAuth Entity", result["message"])
        mock_delete.assert_called_once()

    @patch("requests.delete")
    def test_delete_oauth_entity_error(self, mock_delete):
        mock_delete.side_effect = requests.RequestException("Forbidden")

        params = DeleteOAuthEntityParams(sys_id="oauth_entity_001")
        result = delete_oauth_entity(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to delete OAuth Entity", result["message"])
        self.assertEqual(result["sys_id"], "oauth_entity_001")

    # ------------------------------------------------------------------
    # create_oauth_profile
    # ------------------------------------------------------------------

    @patch("requests.post")
    def test_create_oauth_profile_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "result": {
                "sys_id": "profile_001",
                "name": "FNT Production Profile",
                "oauth_entity": "oauth_entity_001",
                "grant_type": "client_credentials",
                "default": "true",
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        params = CreateOAuthProfileParams(
            oauth_entity_sys_id="oauth_entity_001",
            name="FNT Production Profile",
            grant_type="client_credentials",
        )
        result = create_oauth_profile(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "profile_001")
        self.assertEqual(result["name"], "FNT Production Profile")
        self.assertIn("Created OAuth Profile", result["message"])
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_create_oauth_profile_error(self, mock_post):
        mock_post.side_effect = requests.RequestException("Connection refused")

        params = CreateOAuthProfileParams(
            oauth_entity_sys_id="oauth_entity_001",
            name="FNT Production Profile",
            grant_type="client_credentials",
        )
        result = create_oauth_profile(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to create OAuth Profile", result["message"])
        self.assertIsNone(result["sys_id"])

    # ------------------------------------------------------------------
    # list_oauth_profiles
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_list_oauth_profiles_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                {
                    "sys_id": "profile_001",
                    "name": "FNT Production Profile",
                    "oauth_entity": "oauth_entity_001",
                    "grant_type": "client_credentials",
                    "default": "true",
                    "sys_updated_on": "2025-06-25 10:00:00",
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        params = ListOAuthProfilesParams(oauth_entity_sys_id="oauth_entity_001")
        result = list_oauth_profiles(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(len(result["profiles"]), 1)
        self.assertEqual(result["profiles"][0]["sys_id"], "profile_001")
        self.assertEqual(result["profiles"][0]["name"], "FNT Production Profile")
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_list_oauth_profiles_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("Timeout")

        params = ListOAuthProfilesParams()
        result = list_oauth_profiles(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to list OAuth Profiles", result["message"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["profiles"], [])


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import MagicMock, patch
from servicenow_mcp.utils.config import ServerConfig, AuthConfig, AuthType, BasicAuthConfig
from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.table_api_tools import (
    TableGetRecordsParams,
    TableGetRecordParams,
    TableCreateRecordParams,
    TableUpdateRecordParams,
    TableDeleteRecordParams,
    table_get_records,
    table_get_record,
    table_create_record,
    table_update_record,
    table_delete_record,
)
import requests


class TestTableApiTools(unittest.TestCase):

    def setUp(self):
        self.auth_config = AuthConfig(type=AuthType.BASIC, basic=BasicAuthConfig(username='test', password='test'))

    def _create_config_and_auth(self):
        config = ServerConfig(instance_url="https://dev12345.service-now.com", auth=self.auth_config)
        auth_manager = MagicMock(spec=AuthManager)
        auth_manager.get_headers.return_value = {"Authorization": "Bearer FAKE_TOKEN"}
        return config, auth_manager

    @patch('requests.get')
    def test_table_get_records_success(self, mock_get):
        config, auth_manager = self._create_config_and_auth()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                {"sys_id": "abc123", "number": "INC0010001", "short_description": "First incident"},
                {"sys_id": "def456", "number": "INC0010002", "short_description": "Second incident"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = TableGetRecordsParams(table="incident", query="active=true", limit=10)
        result = table_get_records(config, auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["table"], "incident")
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][0]["sys_id"], "abc123")
        self.assertIn("Retrieved 2 records", result["message"])

    @patch('requests.get')
    def test_table_get_record_success(self, mock_get):
        config, auth_manager = self._create_config_and_auth()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "sys_id": "abc123",
                "number": "INC0010001",
                "short_description": "Test incident",
                "state": "1",
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = TableGetRecordParams(table="incident", sys_id="abc123")
        result = table_get_record(config, auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["table"], "incident")
        self.assertEqual(result["record"]["sys_id"], "abc123")
        self.assertEqual(result["record"]["number"], "INC0010001")
        self.assertIn("Retrieved record abc123", result["message"])

    @patch('requests.post')
    def test_table_create_record_success(self, mock_post):
        config, auth_manager = self._create_config_and_auth()

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "result": {
                "sys_id": "new789",
                "name": "My CI",
                "serial_number": "SN123",
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        params = TableCreateRecordParams(
            table="cmdb_ci",
            data={"name": "My CI", "serial_number": "SN123"},
        )
        result = table_create_record(config, auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["table"], "cmdb_ci")
        self.assertEqual(result["sys_id"], "new789")
        self.assertEqual(result["record"]["name"], "My CI")
        self.assertIn("Created record new789", result["message"])

    @patch('requests.patch')
    def test_table_update_record_success(self, mock_patch):
        config, auth_manager = self._create_config_and_auth()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "sys_id": "abc123",
                "short_description": "Updated description",
                "state": "2",
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_patch.return_value = mock_response

        params = TableUpdateRecordParams(
            table="incident",
            sys_id="abc123",
            data={"short_description": "Updated description", "state": "2"},
        )
        result = table_update_record(config, auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["table"], "incident")
        self.assertEqual(result["sys_id"], "abc123")
        self.assertEqual(result["record"]["short_description"], "Updated description")
        self.assertIn("Updated record abc123", result["message"])

    @patch('requests.delete')
    def test_table_delete_record_success(self, mock_delete):
        config, auth_manager = self._create_config_and_auth()

        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = MagicMock()
        mock_delete.return_value = mock_response

        params = TableDeleteRecordParams(table="incident", sys_id="abc123")
        result = table_delete_record(config, auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["table"], "incident")
        self.assertEqual(result["sys_id"], "abc123")
        self.assertIn("Deleted record abc123", result["message"])

    @patch('requests.get')
    def test_table_get_records_error(self, mock_get):
        config, auth_manager = self._create_config_and_auth()

        mock_get.side_effect = requests.RequestException("Connection timeout")

        params = TableGetRecordsParams(table="incident")
        result = table_get_records(config, auth_manager, params)

        self.assertFalse(result["success"])
        self.assertEqual(result["table"], "incident")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["records"], [])
        self.assertIn("Failed to get records", result["message"])
        self.assertIn("Connection timeout", result["message"])


if __name__ == '__main__':
    unittest.main()

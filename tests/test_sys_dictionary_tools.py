import unittest
from unittest.mock import MagicMock, patch
from servicenow_mcp.utils.config import ServerConfig, AuthConfig, AuthType, BasicAuthConfig
from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.sys_dictionary_tools import (
    CreateFieldParams,
    ListFieldsParams,
    UpdateFieldParams,
    create_field,
    list_fields,
    update_field,
)
import requests


class TestSysDictionaryTools(unittest.TestCase):

    def setUp(self):
        self.auth_config = AuthConfig(type=AuthType.BASIC, basic=BasicAuthConfig(username='test', password='test'))

    def _create_config_and_auth(self):
        config = ServerConfig(instance_url="https://dev12345.service-now.com", auth=self.auth_config)
        auth_manager = MagicMock(spec=AuthManager)
        auth_manager.get_headers.return_value = {"Authorization": "Bearer FAKE_TOKEN"}
        return config, auth_manager

    @patch('requests.post')
    def test_create_field_success(self, mock_post):
        config, auth_manager = self._create_config_and_auth()

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "result": {
                "sys_id": "field001",
                "name": "cmdb_ci",
                "element": "u_fnt_elid",
                "column_label": "FNT ELID",
                "internal_type": "string",
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        params = CreateFieldParams(
            table_name="cmdb_ci",
            column_label="FNT ELID",
            column_name="u_fnt_elid",
            column_type="string",
            max_length=100,
        )
        result = create_field(config, auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "field001")
        self.assertEqual(result["table_name"], "cmdb_ci")
        self.assertEqual(result["column_name"], "u_fnt_elid")
        self.assertIn("Created field", result["message"])
        self.assertEqual(result["record"]["element"], "u_fnt_elid")

    @patch('requests.get')
    def test_list_fields_success(self, mock_get):
        config, auth_manager = self._create_config_and_auth()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                {
                    "sys_id": "field001",
                    "name": "cmdb_ci",
                    "element": "u_fnt_elid",
                    "column_label": "FNT ELID",
                    "internal_type": "string",
                    "max_length": "100",
                    "mandatory": "false",
                    "read_only": "false",
                    "active": "true",
                    "default_value": "",
                    "comments": "FNT integration field",
                    "reference": "",
                },
                {
                    "sys_id": "field002",
                    "name": "cmdb_ci",
                    "element": "name",
                    "column_label": "Name",
                    "internal_type": "string",
                    "max_length": "255",
                    "mandatory": "true",
                    "read_only": "false",
                    "active": "true",
                    "default_value": "",
                    "comments": "",
                    "reference": "",
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = ListFieldsParams(table_name="cmdb_ci")
        result = list_fields(config, auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["table_name"], "cmdb_ci")
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["fields"]), 2)
        self.assertEqual(result["fields"][0]["column_name"], "u_fnt_elid")
        self.assertEqual(result["fields"][1]["column_name"], "name")
        self.assertIn("Found 2 fields", result["message"])

    @patch('requests.get')
    def test_list_fields_custom_only(self, mock_get):
        config, auth_manager = self._create_config_and_auth()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                {
                    "sys_id": "field001",
                    "name": "cmdb_ci",
                    "element": "u_fnt_elid",
                    "column_label": "FNT ELID",
                    "internal_type": "string",
                    "max_length": "100",
                    "mandatory": "false",
                    "read_only": "false",
                    "active": "true",
                    "default_value": "",
                    "comments": "",
                    "reference": "",
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = ListFieldsParams(table_name="cmdb_ci", custom_only=True)
        result = list_fields(config, auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["fields"][0]["column_name"], "u_fnt_elid")

        # Verify the query includes the custom-only filter
        call_args = mock_get.call_args
        query_params = call_args[1]["params"]
        self.assertIn("elementSTARTSWITHu_", query_params["sysparm_query"])

    @patch('requests.patch')
    def test_update_field_success(self, mock_patch):
        config, auth_manager = self._create_config_and_auth()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "sys_id": "field001",
                "column_label": "Updated Label",
                "mandatory": "true",
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_patch.return_value = mock_response

        params = UpdateFieldParams(
            sys_id="field001",
            column_label="Updated Label",
            mandatory=True,
        )
        result = update_field(config, auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "field001")
        self.assertIn("Updated field definition", result["message"])
        self.assertEqual(result["record"]["column_label"], "Updated Label")

    def test_update_field_no_changes(self):
        config, auth_manager = self._create_config_and_auth()

        params = UpdateFieldParams(sys_id="field001")
        result = update_field(config, auth_manager, params)

        self.assertFalse(result["success"])
        self.assertEqual(result["sys_id"], "field001")
        self.assertIn("No fields to update", result["message"])
        self.assertEqual(result["record"], {})


if __name__ == '__main__':
    unittest.main()

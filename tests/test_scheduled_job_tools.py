"""
Tests for the scheduled job tools.

This module contains tests for the scheduled job tools in the ServiceNow MCP server.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.scheduled_job_tools import (
    CreateScheduledJobParams,
    ListScheduledJobsParams,
    GetScheduledJobParams,
    UpdateScheduledJobParams,
    DeleteScheduledJobParams,
    create_scheduled_job,
    list_scheduled_jobs,
    get_scheduled_job,
    update_scheduled_job,
    delete_scheduled_job,
)
from servicenow_mcp.utils.config import ServerConfig, AuthConfig, AuthType, BasicAuthConfig


class TestScheduledJobTools(unittest.TestCase):
    """Tests for the scheduled job tools."""

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
    # create_scheduled_job
    # ------------------------------------------------------------------

    @patch("requests.post")
    def test_create_scheduled_job_success(self, mock_post):
        """Test successfully creating a scheduled job."""
        mock_post.return_value = self._mock_response(
            status_code=201,
            json_data={
                "result": {
                    "sys_id": "job123",
                    "name": "Nightly Import",
                    "run_type": "daily",
                    "active": "true",
                }
            },
        )

        params = CreateScheduledJobParams(
            name="Nightly Import",
            script="gs.log('Running nightly import');",
            run_type="daily",
            time_of_day="02:00:00",
            active=True,
            description="Runs nightly data import",
        )
        result = create_scheduled_job(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "job123")
        self.assertEqual(result["name"], "Nightly Import")
        self.assertEqual(result["run_type"], "daily")
        self.assertIn("Created scheduled job", result["message"])

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(
            args[0],
            "https://test.service-now.com/api/now/table/sysauto_script",
        )
        self.assertEqual(kwargs["json"]["name"], "Nightly Import")
        self.assertEqual(kwargs["json"]["run_type"], "daily")
        self.assertEqual(kwargs["json"]["run_time"], "02:00:00")
        self.assertEqual(kwargs["json"]["comments"], "Runs nightly data import")

    @patch("requests.post")
    def test_create_scheduled_job_error(self, mock_post):
        """Test creating a scheduled job with a RequestException."""
        mock_post.side_effect = requests.RequestException("Connection error")

        params = CreateScheduledJobParams(
            name="Failing Job",
            script="gs.log('fail');",
            run_type="daily",
        )
        result = create_scheduled_job(self.server_config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Failed to create scheduled job", result["message"])
        self.assertIsNone(result["sys_id"])
        self.assertEqual(result["record"], {})

    # ------------------------------------------------------------------
    # list_scheduled_jobs
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_list_scheduled_jobs_success(self, mock_get):
        """Test successfully listing scheduled jobs."""
        mock_get.return_value = self._mock_response(
            json_data={
                "result": [
                    {
                        "sys_id": "job1",
                        "name": "Daily Cleanup",
                        "run_type": "daily",
                        "run_time": "03:00:00",
                        "run_dayofweek": "",
                        "run_dayofmonth": "",
                        "run_period": "",
                        "run_start": "",
                        "active": "true",
                        "sys_updated_on": "2024-01-01 00:00:00",
                    },
                    {
                        "sys_id": "job2",
                        "name": "Weekly Report",
                        "run_type": "weekly",
                        "run_time": "08:00:00",
                        "run_dayofweek": "monday",
                        "run_dayofmonth": "",
                        "run_period": "",
                        "run_start": "",
                        "active": "true",
                        "sys_updated_on": "2024-02-01 00:00:00",
                    },
                ]
            },
        )

        params = ListScheduledJobsParams(
            active_only=True,
            limit=10,
            offset=0,
        )
        result = list_scheduled_jobs(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["jobs"]), 2)
        self.assertEqual(result["jobs"][0]["sys_id"], "job1")
        self.assertEqual(result["jobs"][0]["name"], "Daily Cleanup")
        self.assertEqual(result["jobs"][1]["sys_id"], "job2")
        self.assertEqual(result["jobs"][1]["run_type"], "weekly")

        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertIn("active=true", kwargs["params"]["sysparm_query"])

    # ------------------------------------------------------------------
    # get_scheduled_job
    # ------------------------------------------------------------------

    @patch("requests.get")
    def test_get_scheduled_job_success(self, mock_get):
        """Test successfully getting a single scheduled job."""
        mock_get.return_value = self._mock_response(
            json_data={
                "result": {
                    "sys_id": "job123",
                    "name": "Nightly Import",
                    "script": "gs.log('Running nightly import');",
                    "run_type": "daily",
                    "run_time": "02:00:00",
                    "run_dayofweek": "",
                    "run_dayofmonth": "",
                    "run_period": "",
                    "run_start": "",
                    "active": "true",
                    "conditional": "false",
                    "condition": "",
                    "comments": "Runs nightly data import",
                    "sys_updated_on": "2024-01-01 00:00:00",
                }
            },
        )

        params = GetScheduledJobParams(sys_id="job123")
        result = get_scheduled_job(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertIn("Retrieved scheduled job", result["message"])
        job = result["job"]
        self.assertEqual(job["sys_id"], "job123")
        self.assertEqual(job["name"], "Nightly Import")
        self.assertEqual(job["script"], "gs.log('Running nightly import');")
        self.assertEqual(job["run_type"], "daily")
        self.assertEqual(job["description"], "Runs nightly data import")

        mock_get.assert_called_once()
        args, _ = mock_get.call_args
        self.assertIn("job123", args[0])

    # ------------------------------------------------------------------
    # update_scheduled_job
    # ------------------------------------------------------------------

    @patch("requests.patch")
    def test_update_scheduled_job_success(self, mock_patch):
        """Test successfully updating a scheduled job."""
        mock_patch.return_value = self._mock_response(
            json_data={
                "result": {
                    "sys_id": "job123",
                    "name": "Nightly Import v2",
                    "active": "true",
                }
            },
        )

        params = UpdateScheduledJobParams(
            sys_id="job123",
            name="Nightly Import v2",
            time_of_day="04:00:00",
            active=True,
        )
        result = update_scheduled_job(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "job123")
        self.assertIn("Updated scheduled job", result["message"])

        mock_patch.assert_called_once()
        args, kwargs = mock_patch.call_args
        self.assertIn("job123", args[0])
        self.assertEqual(kwargs["json"]["name"], "Nightly Import v2")
        self.assertEqual(kwargs["json"]["run_time"], "04:00:00")
        self.assertEqual(kwargs["json"]["active"], "true")

    # ------------------------------------------------------------------
    # delete_scheduled_job
    # ------------------------------------------------------------------

    @patch("requests.delete")
    def test_delete_scheduled_job_success(self, mock_delete):
        """Test successfully deleting a scheduled job."""
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status.return_value = None
        mock_delete.return_value = mock_resp

        params = DeleteScheduledJobParams(sys_id="job123")
        result = delete_scheduled_job(self.server_config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_id"], "job123")
        self.assertIn("Deleted scheduled job", result["message"])

        mock_delete.assert_called_once()
        args, _ = mock_delete.call_args
        self.assertEqual(
            args[0],
            "https://test.service-now.com/api/now/table/sysauto_script/job123",
        )


if __name__ == "__main__":
    unittest.main()

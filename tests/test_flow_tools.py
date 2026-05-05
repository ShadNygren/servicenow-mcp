"""
Tests for Phase 5 Flow Designer extension tools.

Covers: list_flows, get_flow, get_flow_triggers, get_flow_actions,
get_flow_version, publish_flow.
"""

import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.tools.flow_tools import (
    GetFlowActionsParams,
    GetFlowParams,
    GetFlowTriggersParams,
    GetFlowVersionParams,
    ListFlowsParams,
    PublishFlowParams,
    get_flow,
    get_flow_actions,
    get_flow_triggers,
    get_flow_version,
    list_flows,
    publish_flow,
)
from servicenow_mcp.utils.config import AuthConfig, AuthType, BasicAuthConfig, ServerConfig


class TestFlowExtensionTools(IsolatedAsyncioTestCase):
    """Tests for Phase 5 Flow Designer read and publish tools."""

    def setUp(self):
        self.auth_config = AuthConfig(
            type=AuthType.BASIC,
            basic=BasicAuthConfig(username="test_user", password="test_password"),
        )
        self.config = ServerConfig(
            instance_url="https://test.service-now.com",
            auth=self.auth_config,
        )
        self.auth_manager = MagicMock(spec=AuthManager)
        self.auth_manager.get_headers_async = AsyncMock(return_value={"Authorization": "Bearer FAKE_TOKEN"})

    # --- list_flows ---

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_flows_success(self, mock_get):
        """Test listing flows returns results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": [
                {"sys_id": "flow1", "name": "Incident Escalation", "status": "published"},
                {"sys_id": "flow2", "name": "Approval Flow", "status": "draft"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = ListFlowsParams()
        result = await list_flows(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["flows"][0]["name"], "Incident Escalation")

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_flows_with_filters(self, mock_get):
        """Test that type, status, and scope filters build correct query."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = ListFlowsParams(flow_type="flow", status="published", scope="global")
        result = await list_flows(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        call_kwargs = mock_get.call_args[1]["params"]
        query = call_kwargs["sysparm_query"]
        self.assertIn("flow_type=flow", query)
        self.assertIn("status=published", query)
        self.assertIn("sys_scope=global", query)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_flows_with_name_filter(self, mock_get):
        """Test that name filter is applied as LIKE match."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = ListFlowsParams(name_filter="Incident")
        result = await list_flows(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        call_kwargs = mock_get.call_args[1]["params"]
        self.assertIn("nameLIKEIncident", call_kwargs["sysparm_query"])

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_list_flows_http_error(self, mock_get):
        """Test list_flows handles HTTP errors."""
        mock_get.side_effect = httpx.HTTPStatusError(
            "500 error",
            request=httpx.Request("POST", "https://test.service-now.com/x"),
            response=httpx.Response(500),
        )
        result = await list_flows(self.config, self.auth_manager, ListFlowsParams())
        self.assertFalse(result["success"])
        self.assertIn("Error listing flows", result["message"])

    # --- get_flow ---

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_success(self, mock_get):
        """Test getting a flow by sys_id."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "sys_id": "flow1",
                "name": "Incident Escalation",
                "status": "published",
                "active": "true",
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = GetFlowParams(flow_sys_id="flow1")
        result = await get_flow(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["flow"]["sys_id"], "flow1")
        called_url = mock_get.call_args[0][0]
        self.assertIn("flow1", called_url)
        self.assertIn("sys_hub_flow", called_url)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_http_error(self, mock_get):
        """Test get_flow handles HTTP errors."""
        mock_get.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=httpx.Request("POST", "https://test.service-now.com/x"),
            response=httpx.Response(404),
        )
        result = await get_flow(self.config, self.auth_manager, GetFlowParams(flow_sys_id="missing"))
        self.assertFalse(result["success"])
        self.assertIn("Error getting flow", result["message"])

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_sends_sysparm_fields(self, mock_get):
        """get_flow must send sysparm_fields and must not request blob fields."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"sys_id": "flow1"}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        await get_flow(self.config, self.auth_manager, GetFlowParams(flow_sys_id="flow1"))

        call_params = mock_get.call_args[1]["params"]
        self.assertIn("sysparm_fields", call_params)
        fields = call_params["sysparm_fields"]
        self.assertIn("sys_id", fields)
        self.assertIn("name", fields)
        self.assertIn("master_snapshot", fields)
        # Blob fields must be excluded
        self.assertNotIn("outputs", fields)
        self.assertNotIn("acls", fields)
        self.assertNotIn("run_with_roles", fields)
        self.assertNotIn("annotation", fields)

    # --- get_flow_triggers ---

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_triggers_success(self, mock_get):
        """Test getting trigger instances for a flow."""
        v1_response = MagicMock()
        v1_response.json.return_value = {
            "result": [{"sys_id": "trig1", "name": "Created", "flow": "flow1"}]
        }
        v1_response.raise_for_status = MagicMock()
        v2_empty = MagicMock()
        v2_empty.json.return_value = {"result": []}
        v2_empty.raise_for_status = MagicMock()
        mock_get.side_effect = [v1_response, v2_empty]

        params = GetFlowTriggersParams(flow_sys_id="flow1")
        result = await get_flow_triggers(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["triggers"][0]["name"], "Created")
        urls = [call[0][0] for call in mock_get.call_args_list]
        self.assertTrue(any("sys_hub_trigger_instance" in u for u in urls))

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_triggers_empty(self, mock_get):
        """Test getting triggers when none exist returns empty list."""
        empty = MagicMock()
        empty.json.return_value = {"result": []}
        empty.raise_for_status = MagicMock()
        mock_get.side_effect = [empty, empty]

        result = await get_flow_triggers(self.config, self.auth_manager, GetFlowTriggersParams(flow_sys_id="flow1"))
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_triggers_http_error(self, mock_get):
        """Test get_flow_triggers handles HTTP errors."""
        mock_get.side_effect = httpx.HTTPStatusError(
            "403 Forbidden",
            request=httpx.Request("POST", "https://test.service-now.com/x"),
            response=httpx.Response(403),
        )
        result = await get_flow_triggers(self.config, self.auth_manager, GetFlowTriggersParams(flow_sys_id="flow1"))
        self.assertFalse(result["success"])

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_triggers_queries_both_generations(self, mock_get):
        """get_flow_triggers must query both V1 and V2 trigger tables and merge results."""
        v1_response = MagicMock()
        v1_response.json.return_value = {
            "result": [{"sys_id": "trig1", "name": "Created", "sys_class_name": "sys_hub_trigger_instance"}]
        }
        v1_response.raise_for_status = MagicMock()
        v2_response = MagicMock()
        v2_response.json.return_value = {
            "result": [{"sys_id": "trig2", "name": "Record Created", "sys_class_name": "sys_hub_trigger_instance_v2"}]
        }
        v2_response.raise_for_status = MagicMock()
        mock_get.side_effect = [v1_response, v2_response]

        result = await get_flow_triggers(self.config, self.auth_manager, GetFlowTriggersParams(flow_sys_id="flow1"))

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(mock_get.call_count, 2)
        urls = [call[0][0] for call in mock_get.call_args_list]
        self.assertTrue(any("sys_hub_trigger_instance" in u and "v2" not in u for u in urls))
        self.assertTrue(any("sys_hub_trigger_instance_v2" in u for u in urls))

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_triggers_sends_correct_fields(self, mock_get):
        """get_flow_triggers must send sysparm_fields with correct architecture field names."""
        empty = MagicMock()
        empty.json.return_value = {"result": []}
        empty.raise_for_status = MagicMock()
        mock_get.side_effect = [empty, empty]

        await get_flow_triggers(self.config, self.auth_manager, GetFlowTriggersParams(flow_sys_id="flow1"))

        first_params = mock_get.call_args_list[0][1]["params"]
        self.assertIn("sysparm_fields", first_params)
        fields = first_params["sysparm_fields"]
        self.assertIn("trigger_inputs", fields)      # correct field name per architecture
        self.assertIn("trigger_definition", fields)
        self.assertNotIn("inputs", fields.split(","))  # must not use wrong field name

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_triggers_pagination_params(self, mock_get):
        """GetFlowTriggersParams limit/offset are sent as sysparm_limit/sysparm_offset."""
        empty = MagicMock()
        empty.json.return_value = {"result": []}
        empty.raise_for_status = MagicMock()
        mock_get.side_effect = [empty, empty]

        await get_flow_triggers(
            self.config, self.auth_manager,
            GetFlowTriggersParams(flow_sys_id="flow1", limit=5, offset=10)
        )

        first_params = mock_get.call_args_list[0][1]["params"]
        self.assertEqual(first_params["sysparm_limit"], 5)
        self.assertEqual(first_params["sysparm_offset"], 10)

    # --- get_flow_actions ---

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_actions_success(self, mock_get):
        """Test getting flow components in list mode."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": [
                {"sys_id": "comp1", "display_text": "Look Up Record", "sys_class_name": "sys_hub_action_instance", "order": "100"},
                {"sys_id": "comp2", "display_text": "Update Record", "sys_class_name": "sys_hub_action_instance_v2", "order": "200"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = GetFlowActionsParams(flow_sys_id="flow1")
        result = await get_flow_actions(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertIn("components", result)
        called_url = mock_get.call_args[0][0]
        self.assertIn("sys_hub_flow_component", called_url)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_actions_http_error(self, mock_get):
        """Test get_flow_actions handles HTTP errors."""
        mock_get.side_effect = httpx.HTTPStatusError(
            "500 error",
            request=httpx.Request("POST", "https://test.service-now.com/x"),
            response=httpx.Response(500),
        )
        result = await get_flow_actions(self.config, self.auth_manager, GetFlowActionsParams(flow_sys_id="flow1"))
        self.assertFalse(result["success"])

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_actions_list_mode_queries_component_table(self, mock_get):
        """List mode must query sys_hub_flow_component (not sys_hub_action_instance)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": [
                {"sys_id": "comp1", "order": "100", "display_text": "Look Up Record", "sys_class_name": "sys_hub_action_instance"},
                {"sys_id": "comp2", "order": "200", "display_text": "If Age > 18", "sys_class_name": "sys_hub_flow_logic"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = GetFlowActionsParams(flow_sys_id="flow1")
        result = await get_flow_actions(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)
        self.assertIn("components", result)          # renamed from "actions"
        self.assertNotIn("actions", result)
        called_url = mock_get.call_args[0][0]
        self.assertIn("sys_hub_flow_component", called_url)
        self.assertNotIn("sys_hub_action_instance", called_url)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_actions_list_mode_sysparm_fields(self, mock_get):
        """List mode sysparm_fields must include sys_class_name for routing."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        await get_flow_actions(self.config, self.auth_manager, GetFlowActionsParams(flow_sys_id="flow1"))

        call_params = mock_get.call_args[1]["params"]
        self.assertIn("sysparm_fields", call_params)
        fields = call_params["sysparm_fields"]
        self.assertIn("sys_class_name", fields)
        self.assertIn("order", fields)
        self.assertIn("display_text", fields)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_actions_list_mode_pagination(self, mock_get):
        """List mode passes limit and offset as sysparm_limit/sysparm_offset."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        await get_flow_actions(
            self.config, self.auth_manager,
            GetFlowActionsParams(flow_sys_id="flow1", limit=10, offset=20)
        )

        call_params = mock_get.call_args[1]["params"]
        self.assertEqual(call_params["sysparm_limit"], 10)
        self.assertEqual(call_params["sysparm_offset"], 20)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_actions_detail_mode_action_instance(self, mock_get):
        """Detail mode routes sys_hub_action_instance to the correct child table."""
        comp_response = MagicMock()
        comp_response.json.return_value = {
            "result": {
                "sys_id": "comp1",
                "sys_class_name": "sys_hub_action_instance",
                "flow": "flow1",
                "order": "100",
                "display_text": "Look Up Record",
            }
        }
        comp_response.raise_for_status = MagicMock()
        detail_response = MagicMock()
        detail_response.json.return_value = {
            "result": {
                "sys_id": "comp1",
                "action_type": {"value": "atype1", "display_value": "Look Up Records"},
                "action_inputs": {},
            }
        }
        detail_response.raise_for_status = MagicMock()
        mock_get.side_effect = [comp_response, detail_response]

        params = GetFlowActionsParams(flow_sys_id="flow1", component_sys_id="comp1")
        result = await get_flow_actions(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_class_name"], "sys_hub_action_instance")
        self.assertIn("detail", result)
        self.assertEqual(mock_get.call_count, 2)
        detail_url = mock_get.call_args_list[1][0][0]
        self.assertIn("sys_hub_action_instance", detail_url)
        self.assertIn("comp1", detail_url)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_actions_detail_mode_flow_logic(self, mock_get):
        """Detail mode routes sys_hub_flow_logic to the correct child table."""
        comp_response = MagicMock()
        comp_response.json.return_value = {
            "result": {
                "sys_id": "comp2",
                "sys_class_name": "sys_hub_flow_logic",
                "flow": "flow1",
                "order": "200",
                "display_text": "If Priority = 1",
            }
        }
        comp_response.raise_for_status = MagicMock()
        detail_response = MagicMock()
        detail_response.json.return_value = {
            "result": {
                "sys_id": "comp2",
                "decision_table": {"value": "dt1", "display_value": "Priority Decision"},
                "logic_definition": {"value": "ld1"},
            }
        }
        detail_response.raise_for_status = MagicMock()
        mock_get.side_effect = [comp_response, detail_response]

        params = GetFlowActionsParams(flow_sys_id="flow1", component_sys_id="comp2")
        result = await get_flow_actions(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["sys_class_name"], "sys_hub_flow_logic")
        detail_url = mock_get.call_args_list[1][0][0]
        self.assertIn("sys_hub_flow_logic", detail_url)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_actions_detail_mode_unsupported_class(self, mock_get):
        """Detail mode returns failure for unsupported sys_class_name (e.g. sys_hub_flow_stage)."""
        comp_response = MagicMock()
        comp_response.json.return_value = {
            "result": {
                "sys_id": "stage1",
                "sys_class_name": "sys_hub_flow_stage",
                "flow": "flow1",
                "order": "50",
                "display_text": "Investigation",
            }
        }
        comp_response.raise_for_status = MagicMock()
        mock_get.return_value = comp_response

        params = GetFlowActionsParams(flow_sys_id="flow1", component_sys_id="stage1")
        result = await get_flow_actions(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("sys_hub_flow_stage", result["message"])
        self.assertEqual(mock_get.call_count, 1)  # no second call attempted

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_actions_detail_mode_child_table_error(self, mock_get):
        """Detail mode returns failure when the child table fetch raises HTTPError."""
        comp_response = MagicMock()
        comp_response.json.return_value = {
            "result": {
                "sys_id": "comp1",
                "sys_class_name": "sys_hub_action_instance",
                "flow": "flow1",
                "order": "100",
                "display_text": "Look Up Record",
            }
        }
        comp_response.raise_for_status = MagicMock()
        mock_get.side_effect = [comp_response, httpx.HTTPStatusError(
            "500 Server Error",
            request=httpx.Request("POST", "https://test.service-now.com/x"),
            response=httpx.Response(500),
        )]

        params = GetFlowActionsParams(flow_sys_id="flow1", component_sys_id="comp1")
        result = await get_flow_actions(self.config, self.auth_manager, params)

        self.assertFalse(result["success"])
        self.assertIn("Error fetching component detail", result["message"])
        self.assertEqual(mock_get.call_count, 2)  # both calls attempted

    # --- get_flow_version ---

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_version_latest(self, mock_get):
        """Test getting the latest flow version."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": [
                {"sys_id": "ver1", "flow": "flow1", "published": "false", "annotation": ""}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = GetFlowVersionParams(flow_sys_id="flow1")
        result = await get_flow_version(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertEqual(result["version"]["sys_id"], "ver1")
        call_kwargs = mock_get.call_args[1]["params"]
        self.assertNotIn("published=true", call_kwargs.get("sysparm_query", ""))

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_version_published_only(self, mock_get):
        """Test getting only the published flow version adds published=true filter."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": [{"sys_id": "ver2", "published": "true"}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        params = GetFlowVersionParams(flow_sys_id="flow1", published_only=True)
        result = await get_flow_version(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        call_kwargs = mock_get.call_args[1]["params"]
        self.assertIn("published=true", call_kwargs["sysparm_query"])

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_version_not_found(self, mock_get):
        """No sys_hub_flow_version and no snapshot returns failure."""
        empty = MagicMock()
        empty.json.return_value = {"result": []}
        empty.raise_for_status = MagicMock()
        mock_get.side_effect = [empty, empty]

        result = await get_flow_version(self.config, self.auth_manager, GetFlowVersionParams(flow_sys_id="flow1"))
        self.assertFalse(result["success"])
        self.assertIn("No", result["message"])
        self.assertEqual(mock_get.call_count, 2)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_version_snapshot_fallback(self, mock_get):
        """When version table is empty, use sys_hub_flow_snapshot if present."""
        ver_empty = MagicMock()
        ver_empty.json.return_value = {"result": []}
        ver_empty.raise_for_status = MagicMock()
        snap_row = MagicMock()
        snap_row.json.return_value = {
            "result": [{"sys_id": "snap1", "flow": "flow1", "annotation": "pkg"}]
        }
        snap_row.raise_for_status = MagicMock()
        mock_get.side_effect = [ver_empty, snap_row]

        result = await get_flow_version(self.config, self.auth_manager, GetFlowVersionParams(flow_sys_id="flow1"))
        self.assertTrue(result["success"])
        self.assertTrue(result.get("snapshot_fallback"))
        self.assertEqual(result["version"]["sys_id"], "snap1")
        self.assertEqual(mock_get.call_count, 2)

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_version_http_error(self, mock_get):
        """Test get_flow_version handles HTTP errors."""
        mock_get.side_effect = httpx.HTTPStatusError(
            "500 error",
            request=httpx.Request("POST", "https://test.service-now.com/x"),
            response=httpx.Response(500),
        )
        result = await get_flow_version(self.config, self.auth_manager, GetFlowVersionParams(flow_sys_id="flow1"))
        self.assertFalse(result["success"])

    @patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock)
    async def test_get_flow_version_excludes_payload(self, mock_get):
        """get_flow_version must request sysparm_fields and must exclude the payload blob."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": [{"sys_id": "ver1", "flow": "flow1"}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        await get_flow_version(self.config, self.auth_manager, GetFlowVersionParams(flow_sys_id="flow1"))

        # call_args_list[0] is the sys_hub_flow_version query
        first_call_params = mock_get.call_args_list[0][1]["params"]
        self.assertIn("sysparm_fields", first_call_params)
        fields = first_call_params["sysparm_fields"]
        self.assertNotIn("payload", fields)
        self.assertIn("sys_id", fields)
        self.assertIn("annotation", fields)

    # --- publish_flow ---

    @patch.object(httpx.AsyncClient, "patch", new_callable=AsyncMock)
    async def test_publish_flow_success(self, mock_patch):
        """Test publishing a flow sets active=true and status=published."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"sys_id": "flow1", "active": "true", "status": "published"}
        }
        mock_response.raise_for_status = MagicMock()
        mock_patch.return_value = mock_response

        params = PublishFlowParams(flow_sys_id="flow1")
        result = await publish_flow(self.config, self.auth_manager, params)

        self.assertTrue(result["success"])
        self.assertIn("published", result["message"])
        sent_data = mock_patch.call_args[1]["json"]
        self.assertEqual(sent_data["active"], "true")
        self.assertEqual(sent_data["status"], "published")

    @patch.object(httpx.AsyncClient, "patch", new_callable=AsyncMock)
    async def test_publish_flow_http_error(self, mock_patch):
        """Test publish_flow handles HTTP errors and provides fallback hint."""
        mock_patch.side_effect = httpx.HTTPStatusError(
            "403 Forbidden",
            request=httpx.Request("POST", "https://test.service-now.com/x"),
            response=httpx.Response(403),
        )
        result = await publish_flow(self.config, self.auth_manager, PublishFlowParams(flow_sys_id="flow1"))
        self.assertFalse(result["success"])
        # Error message should suggest background script fallback
        self.assertIn("FlowDesignerAPI.publishFlow", result["message"])

    @patch.object(httpx.AsyncClient, "patch", new_callable=AsyncMock)
    async def test_publish_flow_hits_sys_hub_flow(self, mock_patch):
        """Test that publish_flow sends PATCH to sys_hub_flow not sys_hub_flow_version."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"sys_id": "flow1"}}
        mock_response.raise_for_status = MagicMock()
        mock_patch.return_value = mock_response

        await publish_flow(self.config, self.auth_manager, PublishFlowParams(flow_sys_id="flow1"))
        called_url = mock_patch.call_args[0][0]
        self.assertIn("sys_hub_flow/flow1", called_url)
        self.assertNotIn("sys_hub_flow_version", called_url)


if __name__ == "__main__":
    unittest.main()

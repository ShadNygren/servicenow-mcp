"""
Flow Designer tools for the ServiceNow MCP server.

Creates Flow Designer flows via the internal /api/now/processflow/ API, which is the
only mechanism capable of writing trigger instances and action instances (the standard
Table API cannot write sys_hub_flow_snapshot, which has sys_policy=read).

API sequence for create_flow:
  1. POST /api/now/processflow/flow                         — create flow shell
  2. POST /api/now/processflow/versioning/create_version    — initial autosave
  3. Resolve trigger_definition_id (if not supplied)
  4. Build trigger + action instance payloads
  5. PUT  /api/now/processflow/flow                         — save trigger + action instances
  6. POST /api/now/processflow/versioning/create_version    — final Save version
  7. PATCH /api/now/table/sys_hub_flow_version              — set fTriggerType='Record' and inject choices into version payload
  8. DELETE /api/now/table/sys_hub_flow_safe_edit           — release Flow Designer edit lock
"""

import json
import logging
import time
import uuid
from typing import Any, Literal

import requests
from pydantic import BaseModel, Field, field_validator

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter models
# ---------------------------------------------------------------------------


class TriggerInputParam(BaseModel):
    """A single trigger input name/value pair.

    All values must be strings — the ServiceNow processflow API serialises
    every input value as a string, including booleans ('0'/'1') and integers.
    """

    name: str = Field(..., description="Trigger input name (e.g. 'table', 'condition')")
    value: str = Field(..., description="Trigger input value (all values are strings)")


class TriggerInstanceParam(BaseModel):
    """Trigger configuration for a flow.

    Convenience fields 'table' and 'condition' are converted to trigger inputs
    automatically. Provide 'inputs' directly to override all trigger inputs.
    Note: 'inputs' must be a non-empty list to take effect — an empty list is
    treated the same as None (convenience fields are used instead).
    """

    type: str = Field(
        ...,
        description=(
            "Trigger type string. Common values: 'record_create', "
            "'record_create_or_update', 'record_update', 'recurrence'. "
            "Verify available types via GET /api/now/hub/triggerpicker/basic on the instance."
        ),
    )
    trigger_definition_id: str | None = Field(
        None,
        description=(
            "sys_id of the trigger type definition (sys_hub_trigger_definition — V2 trigger catalog). "
            "If omitted, create_flow will resolve it automatically from the 'type' field "
            "by querying sys_hub_trigger_type.base_trigger on the instance. "
            "Call list_trigger_types to discover available sys_ids explicitly."
        ),
    )
    name: str | None = Field(
        None,
        description=(
            "Display name for the trigger (e.g. 'Created', 'Created or Updated'). "
            "Defaults to the type value if omitted."
        ),
    )
    table: str | None = Field(
        None,
        description=(
            "Table name to trigger on (e.g. 'incident'). "
            "Convenience field — sets the 'table' trigger input. "
            "Ignored if 'inputs' is provided."
        ),
    )
    condition: str | None = Field(
        None,
        description=(
            "Encoded query condition (e.g. 'active=true'). "
            "Convenience field — sets the 'condition' trigger input. "
            "Ignored if 'inputs' is provided."
        ),
    )
    inputs: list[TriggerInputParam] | None = Field(
        None,
        description=(
            "Full trigger input list. If provided and non-empty, overrides 'table' and 'condition'. "
            "An empty list ([]) is treated as None — convenience fields are used instead. "
            "Only 'table' is mandatory for record triggers."
        ),
    )

    @field_validator("inputs")
    @classmethod
    def normalize_empty_inputs(cls, v: list[TriggerInputParam] | None) -> list[TriggerInputParam] | None:
        """Treat an explicitly empty inputs list the same as None.

        Prevents inputs=[] from silently discarding table and condition convenience fields.
        """
        if v is not None and len(v) == 0:
            return None
        return v


class ActionInputParam(BaseModel):
    """A single action input parameter with its parameter definition sys_id."""

    id: str = Field(
        ...,
        description=(
            "Parameter definition sys_id (sys_hub_action_input.sys_id). "
            "Must exactly match the action type's input parameter definition. "
            "Example — Look Up Record 'table' input: 'd909f99587003300663ca1bb36cb0ba4'."
        ),
    )
    name: str = Field(..., description="Input parameter name (e.g. 'table', 'conditions')")
    value: str = Field(..., description="Input value — all values are strings, including booleans ('0'/'1') and integers")


class ActionInstanceParam(BaseModel):
    """One action step to add to the flow."""

    action_type_sys_id: str = Field(
        ...,
        description=(
            "sys_id of the action type definition (sys_hub_action_type_definition). "
            "Known values: Look Up Record='9d09f99587003300663ca1bb36cb0ba3', "
            "Create Record='02f0b88cc3c632002841b63b12d3aeff'. "
            "Discover others via GET /api/now/hub/actionpicker/most-popular."
        ),
    )
    name: str = Field(..., description="Display name for this action step (e.g. 'Look Up Record')")
    order: int = Field(
        1,
        description=(
            "Execution order, 1-based integer. Must be unique across all actions in the flow — "
            "duplicate order values will result in undefined rendering order in the UI."
        ),
    )
    internal_name: str | None = Field(
        None,
        description=(
            "Internal name of the action type (e.g. 'look_up_record'). "
            "Written into the PUT payload; leave None if unknown."
        ),
    )
    parent_action_type_id: str | None = Field(
        None,
        description=(
            "Parent action type sys_id. "
            "For Look Up Record: 'b93f42810b30030085c083eb37673a63'. "
            "Leave empty if unknown — the platform will resolve it."
        ),
    )
    inputs: list[ActionInputParam] = Field(
        default_factory=list,
        description=(
            "Input parameters for this action. Each input requires the exact parameter "
            "definition sys_id ('id' field) from the action type. "
            "See flow-designer-api.md memory for known parameter definition IDs."
        ),
    )


class ListTriggerTypesParams(BaseModel):
    """Parameters for list_trigger_types (no required inputs).

    Kept for interface consistency with the (config, auth_manager, params) tool signature.
    """
    pass


class TriggerTypeInfo(BaseModel):
    """One trigger type definition.

    sys_id is the sys_hub_trigger_definition sys_id (V2 trigger catalog), obtained
    by traversing sys_hub_trigger_type.base_trigger. Use this value as
    trigger_definition_id in create_flow.
    """
    sys_id: str
    name: str
    type_string: str | None = None
    """Mapped type string (e.g. 'record_create') for use as create_flow trigger.type.
    May be None for non-standard or scoped-app trigger types not in the built-in map.
    """


class ListTriggerTypesResult(BaseModel):
    """Result from list_trigger_types."""
    trigger_types: list[TriggerTypeInfo]
    message: str


class CreateFlowParams(BaseModel):
    """Parameters for creating a Flow Designer flow."""

    name: str = Field(..., description="Flow name as it will appear in Flow Designer")
    description: str | None = Field(None, description="Flow description")
    scope: str = Field(
        "global",
        description="Application scope. Use 'global' for global scope or provide a scope sys_id.",
    )
    run_as: Literal["user", "system"] = Field(
        "user",
        description="Execution context: 'user' (runs as the triggering user) or 'system'.",
    )
    access: Literal["public", "package_private", "private"] = Field(
        "public",
        description="Access level: 'public', 'package_private', or 'private'.",
    )
    flow_priority: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        "MEDIUM",
        description="Flow priority: 'LOW', 'MEDIUM', or 'HIGH'.",
    )
    trigger: TriggerInstanceParam | None = Field(
        None,
        description=(
            "Trigger configuration. If omitted the flow is created as a subflow "
            "(no trigger, callable by other flows or the REST API)."
        ),
    )
    actions: list[ActionInstanceParam] = Field(
        default_factory=list,
        description=(
            "Action steps to add to the flow. Each action requires exact parameter "
            "definition sys_ids for its inputs — these are instance-specific values "
            "from sys_hub_action_input. See flow-designer-api.md memory "
            "for confirmed IDs for Look Up Record and Create Record."
        ),
    )


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class CreateFlowResponse(BaseModel):
    """Response from create_flow.

    When success=False but flow_sys_id is populated, the flow shell was partially
    created. The caller should inspect flow_sys_id to clean up or retry in Flow Designer.
    """

    success: bool = Field(..., description="Whether the flow was created successfully")
    message: str = Field(..., description="Human-readable result description")
    flow_sys_id: str | None = Field(None, description="sys_id of the created flow (sys_hub_flow)")
    flow_name: str | None = Field(None, description="Name of the created flow")
    flow_internal_name: str | None = Field(None, description="Auto-generated internal name of the flow")


class CloneFlowParams(BaseModel):
    """Parameters for clone_flow — duplicate an existing flow with a new sys_id."""

    source_flow_sys_id: str = Field(..., description="sys_id of the flow to clone (sys_hub_flow)")
    name: str = Field(..., description="Display name for the new flow")
    description: str | None = Field(
        None,
        description="Description for the new flow; if omitted, copied from the source flow table row when available",
    )
    scope: str | None = Field(
        None,
        description="Application scope (sys_id or 'global'); defaults from source flow when omitted",
    )
    run_as: Literal["user", "system"] | None = Field(
        None,
        description="Run-as context; defaults from source flow when omitted",
    )
    access: Literal["public", "package_private", "private"] | None = Field(
        None,
        description="Access level; defaults from source flow when omitted",
    )
    flow_priority: Literal["LOW", "MEDIUM", "HIGH"] | None = Field(
        None,
        description="Flow priority; defaults from source flow when omitted",
    )


class CloneFlowResponse(BaseModel):
    """Response from clone_flow."""

    success: bool = Field(..., description="Whether the clone completed")
    message: str = Field(..., description="Human-readable result")
    flow_sys_id: str | None = Field(None, description="sys_id of the new flow")
    flow_name: str | None = Field(None, description="Name of the new flow")
    flow_internal_name: str | None = Field(None, description="Internal name of the new flow")
    source_flow_sys_id: str | None = Field(None, description="sys_id of the source flow")


class ListArtifactsParams(BaseModel):
    """Common pagination/filter parameters for flow artifacts."""

    limit: int = Field(20, ge=1, le=200, description="Maximum number of records to return")
    offset: int = Field(0, ge=0, description="Zero-based record offset")
    query: str | None = Field(
        None,
        description="Additional encoded query fragment appended with '^'",
    )
    active: bool | None = Field(
        None,
        description="Optional active-state filter",
    )


class ListSubflowsParams(ListArtifactsParams):
    """Parameters for list_subflows."""


class ListActionsParams(ListArtifactsParams):
    """Parameters for list_actions."""


class GetArtifactParams(BaseModel):
    """Common lookup parameter for flow artifacts."""

    sys_id: str = Field(..., description="sys_id of the artifact")


class GetSubflowParams(GetArtifactParams):
    """Parameters for get_subflow."""


class GetActionParams(GetArtifactParams):
    """Parameters for get_action."""


class CreateArtifactParams(BaseModel):
    """Common create parameters for flow/subflow/action artifacts."""

    name: str = Field(..., description="Artifact display name")
    description: str | None = Field(None, description="Artifact description")
    scope: str = Field("global", description="Application scope sys_id or 'global'")
    run_as: Literal["user", "system"] = Field(
        "user",
        description="Execution context",
    )
    access: Literal["public", "package_private", "private"] = Field(
        "public",
        description="Artifact access level",
    )
    flow_priority: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        "MEDIUM",
        description="Default run priority",
    )


class CreateSubflowParams(CreateArtifactParams):
    """Parameters for create_subflow."""


class CreateActionParams(CreateArtifactParams):
    """Parameters for create_action."""


class UpdateArtifactParams(BaseModel):
    """Common update parameters for flow/subflow/action artifacts."""

    sys_id: str = Field(..., description="sys_id of the artifact to update")
    name: str | None = Field(None, description="Updated name")
    description: str | None = Field(None, description="Updated description")
    run_as: Literal["user", "system"] | None = Field(None, description="Updated execution context")
    access: Literal["public", "package_private", "private"] | None = Field(
        None, description="Updated access level"
    )
    flow_priority: Literal["LOW", "MEDIUM", "HIGH"] | None = Field(
        None, description="Updated run priority"
    )
    active: bool | None = Field(None, description="Updated active state")


class UpdateFlowParams(UpdateArtifactParams):
    """Parameters for update_flow."""


class UpdateSubflowParams(UpdateArtifactParams):
    """Parameters for update_subflow."""


class UpdateActionParams(UpdateArtifactParams):
    """Parameters for update_action."""


class PublishArtifactParams(BaseModel):
    """Common publish parameters for flow/subflow/action artifacts."""

    sys_id: str = Field(..., description="sys_id of the artifact to publish")
    annotation: str | None = Field("", description="Optional publish note/annotation")


class PublishSubflowParams(PublishArtifactParams):
    """Parameters for publish_subflow."""


class PublishActionParams(PublishArtifactParams):
    """Parameters for publish_action."""


# ---------------------------------------------------------------------------
# Action Type Catalog — list_action_types, list_action_type_inputs
# ---------------------------------------------------------------------------


class ListActionTypesParams(BaseModel):
    """Parameters for list_action_types."""

    query: str = Field(
        ...,
        min_length=1,
        description=(
            "Search string to filter action types by name or internal_name. "
            "Examples: 'Look Up Record', 'Create Record', 'Send Email'. "
            "Returns up to limit results matching the name CONTAINS query."
        ),
    )
    limit: int = Field(25, ge=1, le=200, description="Maximum number of results to return")


class ActionTypeSummary(BaseModel):
    """One action type from the action type catalog."""

    definition_sys_id: str = Field(
        ...,
        description=(
            "sys_hub_action_type_definition.sys_id — pass to list_action_type_inputs "
            "to get input parameter definitions."
        ),
    )
    base_sys_id: str = Field(
        ...,
        description=(
            "sys_hub_action_type_base.sys_id — use as ActionInstanceParam.action_type_sys_id "
            "when calling add_steps_to_flow or create_flow."
        ),
    )
    name: str = Field(..., description="Display name (e.g. 'Look Up Record')")
    internal_name: str | None = Field(None, description="Internal name (e.g. 'glide_record_lookup')")
    spoke: str | None = Field(None, description="Spoke name (e.g. 'ServiceNow Core')")
    description: str | None = Field(None, description="Action description")


class ListActionTypesResult(BaseModel):
    """Result from list_action_types."""

    action_types: list[ActionTypeSummary]
    message: str


class ListActionTypeInputsParams(BaseModel):
    """Parameters for list_action_type_inputs."""

    action_type_sys_id: str = Field(
        ...,
        description=(
            "sys_id of the action type definition (sys_hub_action_type_definition). "
            "Use definition_sys_id from list_action_types to find this value."
        ),
    )


class ActionTypeInput(BaseModel):
    """One input parameter definition on an action type."""

    sys_id: str = Field(..., description="sys_hub_action_input.sys_id — use as ActionInputParam.id in create_flow/add_steps_to_flow")
    name: str = Field(..., description="Input parameter logical name from the 'element' field (e.g. 'table', 'conditions') — use as the key when setting values")
    label: str = Field(..., description="Display label shown in Flow Designer")
    type: str = Field(..., description="Field type (e.g. 'table_name', 'conditions', 'string')")
    mandatory: bool = Field(False, description="Whether this input is required")
    default_value: str | None = Field(None, description="Default value if any")
    order: int = Field(0, description="Display order in Flow Designer")


class ListActionTypeInputsResult(BaseModel):
    """Result from list_action_type_inputs."""

    action_type_sys_id: str
    inputs: list[ActionTypeInput]
    message: str


class ListFlowLogicTypesParams(BaseModel):
    """Parameters for list_flow_logic_types (no required inputs)."""
    pass


class FlowLogicType(BaseModel):
    """One flow logic step type (e.g. If, Switch, For Each)."""

    sys_id: str = Field(..., description="sys_id of this logic type — use when building flow logic steps")
    name: str = Field(..., description="Display name (e.g. 'If', 'Switch', 'For Each')")
    label: str | None = Field(None, description="UI label if different from name")
    type_string: str | None = Field(None, description="Internal type string (e.g. 'if', 'switch', 'for_each')")


class ListFlowLogicTypesResult(BaseModel):
    """Result from list_flow_logic_types."""

    logic_types: list[FlowLogicType]
    message: str


class AddStepsToFlowParams(BaseModel):
    """Parameters for add_steps_to_flow."""

    flow_sys_id: str = Field(
        ...,
        description="sys_id of the existing flow to modify (sys_hub_flow). Flow must be in draft state or will be set to draft on edit.",
    )
    actions: list[ActionInstanceParam] = Field(
        default_factory=list,
        description=(
            "Action steps to append. Order values must not conflict with existing steps — "
            "use get_flow_actions to inspect current orders before calling this tool."
        ),
    )


class AddStepsToFlowResponse(BaseModel):
    """Response from add_steps_to_flow."""

    success: bool
    message: str
    flow_sys_id: str | None = None
    steps_added: int = 0


class AddSubflowStepToFlowParams(BaseModel):
    """Parameters for add_subflow_step_to_flow."""

    flow_sys_id: str = Field(
        ...,
        description="sys_id of the parent flow to modify (sys_hub_flow, type=flow).",
    )
    subflow_sys_id: str = Field(
        ...,
        description="sys_id of the subflow to invoke (sys_hub_flow where type=subflow).",
    )
    name: str = Field(..., description="Display label for this step in the parent flow")
    order: int = Field(
        ...,
        ge=1,
        description=(
            "Execution order (1-based). Must be unique across action, logic, and subflow steps — "
            "inspect existing orders via processflow GET or get_flow_actions before calling."
        ),
    )
    inputs: list[ActionInputParam] = Field(
        default_factory=list,
        description=(
            "Values for the subflow's input variables. Each 'id' must be sys_hub_flow_input.sys_id "
            "for the subflow (use list_flow_io on subflow_sys_id)."
        ),
    )


class AddSubflowStepToFlowResponse(BaseModel):
    """Response from add_subflow_step_to_flow."""

    success: bool
    message: str
    flow_sys_id: str | None = None
    subflow_step_id: str | None = Field(None, description="Generated step id in the subFlowInstances array")


class RemoveStepsFromFlowParams(BaseModel):
    """Parameters for remove_steps_from_flow."""

    flow_sys_id: str = Field(
        ...,
        description="sys_id of the flow to modify (sys_hub_flow).",
    )
    step_ids: list[str] = Field(
        ...,
        description=(
            "List of step id values to remove. Each id must match a step's 'id' field "
            "in actionInstances, flowLogicInstances, or subFlowInstances. "
            "Use get_flow_actions, processflow GET, or get_flow_version to discover ids."
        ),
    )


class RemoveStepsFromFlowResponse(BaseModel):
    """Response from remove_steps_from_flow."""

    success: bool
    message: str
    flow_sys_id: str | None = None
    steps_removed: int = 0


class LogicInputParam(BaseModel):
    """A single input for a logic step (e.g. condition expression)."""

    name: str = Field(..., description="Input parameter name (e.g. 'condition_name')")
    value: str = Field(..., description="Input value")


class AddLogicToFlowParams(BaseModel):
    """Parameters for add_logic_to_flow."""

    flow_sys_id: str = Field(
        ...,
        description="sys_id of the existing flow to modify (sys_hub_flow).",
    )
    logic_type_sys_id: str = Field(
        ...,
        description=(
            "sys_id of the logic type definition. Get this from list_flow_logic_types. "
            "The sys_id returned by that tool IS the definitionId for the flowLogicInstance. "
            "Common values on most instances: "
            "If=af4e1945c3e232002841b63b12d3ae3e, "
            "Else=1f781bf3c32232002841b63b12d3aee6, "
            "End=d176605ea76103004f27b0d2187901c7."
        ),
    )
    name: str = Field(
        ...,
        description=(
            "Display name for the logic step as shown in Flow Designer "
            "(e.g. 'If: incident is high priority', 'For Each: record in list')."
        ),
    )
    order: int = Field(
        ...,
        ge=1,
        description=(
            "Execution order (1-based). Must not conflict with existing steps. "
            "Use get_flow_version to inspect current orders."
        ),
    )
    parent_ui_id: str | None = Field(
        None,
        description=(
            "uiUniqueIdentifier of the parent logic block. Required for nested blocks "
            "(Else, End must reference their parent If's uiUniqueIdentifier). "
            "Leave None for top-level logic blocks."
        ),
    )
    inputs: list[LogicInputParam] = Field(
        default_factory=list,
        description=(
            "Logic step inputs, e.g. condition expressions. "
            "For If blocks: use name='condition_name', value='<encoded_query>'."
        ),
    )


class AddLogicToFlowResponse(BaseModel):
    """Response from add_logic_to_flow."""

    success: bool
    message: str
    flow_sys_id: str | None = None
    logic_step_id: str | None = None


class ListActionTypeOutputsParams(BaseModel):
    """Parameters for list_action_type_outputs."""

    action_type_sys_id: str = Field(
        ...,
        description=(
            "sys_id of the action type definition (sys_hub_action_type_definition). "
            "Use definition_sys_id from list_action_types. "
            "This is the same sys_id used for list_action_type_inputs."
        ),
    )


class ActionTypeOutput(BaseModel):
    """One output variable definition on an action type."""

    sys_id: str
    element: str = Field(..., description="Logical output variable name (data pill identifier)")
    label: str = Field(..., description="Display label shown in Flow Designer")
    internal_type: str = Field(..., description="Field type (e.g. 'GlideRecord', 'boolean', 'string')")
    mandatory: bool = False
    default_value: str | None = None
    order: int = 0


class ListActionTypeOutputsResult(BaseModel):
    """Result from list_action_type_outputs."""

    action_type_sys_id: str
    outputs: list[ActionTypeOutput]
    message: str


class FlowIOVariable(BaseModel):
    """One input or output variable on a flow/subflow."""

    sys_id: str
    element: str = Field(..., description="Logical variable name (data pill identifier)")
    label: str = Field(..., description="Display label shown in Flow Designer")
    internal_type: str = Field(..., description="Field type (e.g. 'string', 'GlideRecord', 'boolean')")
    mandatory: bool = False
    default_value: str | None = None
    order: int = 0


class ListFlowIOParams(BaseModel):
    """Parameters for list_flow_io."""

    flow_sys_id: str = Field(
        ...,
        description=(
            "sys_id of the flow or subflow (sys_hub_flow). "
            "For flows: returns output variables produced by the flow. "
            "For subflows: returns both input variables the caller must provide "
            "and output variables the subflow produces."
        ),
    )


class ListFlowIOResult(BaseModel):
    """Result from list_flow_io."""

    flow_sys_id: str
    inputs: list[FlowIOVariable]
    outputs: list[FlowIOVariable]
    message: str


class ExecuteFlowParams(BaseModel):
    """Parameters for execute_flow."""

    flow_sys_id: str = Field(
        ...,
        description=(
            "sys_id of the flow to execute (sys_hub_flow). "
            "The flow must be in draft or published state. "
            "Draft flows can be executed for testing without publishing."
        ),
    )
    inputs: dict[str, str] | None = Field(
        None,
        description=(
            "Optional input values for the flow execution. "
            "Key is the input variable element name, value is the string value. "
            "Use list_flow_io to discover required input names."
        ),
    )


class ExecuteFlowResponse(BaseModel):
    """Response from execute_flow."""

    success: bool
    message: str
    execution_id: str | None = None
    execution_source: str | None = Field(
        None,
        description="How execution was started: 'processflow_test' (REST) or 'script' (GlideFlowAPI fallback).",
    )


class UpdateFlowTriggerParams(BaseModel):
    """Parameters for update_flow_trigger — replace the flow's trigger with a new configuration."""

    flow_sys_id: str = Field(..., description="sys_id of the flow (sys_hub_flow, type=flow)")
    trigger: TriggerInstanceParam = Field(
        ...,
        description="New trigger configuration (same shape as create_flow). Replaces all entries in triggerInstances.",
    )


class UpdateFlowTriggerResponse(BaseModel):
    """Response from update_flow_trigger."""

    success: bool
    message: str
    flow_sys_id: str | None = None


class FlowExecutionStepDetail(BaseModel):
    """One step row from runtime execution (typically sys_hub_flow_stage_context)."""

    sys_id: str
    name: str | None = None
    state: str | None = None
    started: str | None = None
    ended: str | None = None
    output: str | None = None
    error: str | None = None


class GetFlowExecutionDetailParams(BaseModel):
    """Parameters for get_flow_execution_detail."""

    execution_sys_id: str = Field(
        ...,
        description=(
            "sys_id of the flow execution record (sys_hub_flow_context). "
            "Use get_flow_execution_history or execute_flow to obtain this value."
        ),
    )


class GetFlowExecutionDetailResult(BaseModel):
    """Result from get_flow_execution_detail."""

    success: bool
    message: str
    execution_sys_id: str | None = None
    name: str | None = None
    state: str | None = None
    started: str | None = None
    ended: str | None = None
    error: str | None = None
    flow: str | None = None
    steps: list[FlowExecutionStepDetail] = Field(default_factory=list)


class DeleteArtifactParams(BaseModel):
    """Common delete parameter — sys_id of the artifact to delete."""

    sys_id: str = Field(..., description="sys_id of the artifact to delete")


class DeleteFlowParams(DeleteArtifactParams):
    """Parameters for delete_flow."""


class DeleteSubflowParams(DeleteArtifactParams):
    """Parameters for delete_subflow."""


class DeleteActionParams(DeleteArtifactParams):
    """Parameters for delete_action."""


class DeleteArtifactResponse(BaseModel):
    """Response from delete_* tools."""

    success: bool
    message: str
    sys_id: str | None = None


class GetFlowExecutionHistoryParams(BaseModel):
    """Parameters for get_flow_execution_history."""

    flow_sys_id: str = Field(..., description="sys_id of the flow to get execution history for")
    limit: int = Field(20, ge=1, le=100, description="Maximum number of executions to return")
    state: str | None = Field(
        None,
        description="Optional state filter. Common values: 'complete', 'error', 'running', 'cancelled'.",
    )


class FlowExecution(BaseModel):
    """Summary of one flow execution from sys_hub_flow_context."""

    sys_id: str
    name: str | None = None
    state: str | None = None
    started: str | None = None
    ended: str | None = None
    error: str | None = None


class GetFlowExecutionHistoryResult(BaseModel):
    """Result from get_flow_execution_history."""

    executions: list[FlowExecution]
    count: int
    message: str


class ArtifactSummary(BaseModel):
    """Compact artifact summary used by list_* tools."""

    sys_id: str
    name: str
    artifact_type: str
    description: str | None = None
    active: bool = False
    published: bool = False
    internal_name: str | None = None


class ListArtifactsResponse(BaseModel):
    """List response model for artifact list tools."""

    artifacts: list[ArtifactSummary]
    count: int
    message: str


class GetArtifactResponse(BaseModel):
    """Get response model for artifact read tools."""

    artifact: dict[str, Any] | None = None
    message: str


class MutationResponse(BaseModel):
    """Response model for create/update/publish operations."""

    success: bool
    message: str
    sys_id: str | None = None
    name: str | None = None


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

# Maps the user-facing type string to the display name stored in sys_hub_trigger_type.name (V1 catalog)
_TRIGGER_TYPE_NAME_MAP = {
    "record_create": "Created",
    "record_create_or_update": "Created or Updated",
    "record_update": "Updated",
    "recurrence": "Recurrence",
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "repeat": "Repeat",
    "run_once": "Run Once",
    "email": "Inbound Email",
    "rest": "Trigger Rest",
    "service_catalog": "Service Catalog",
    "knowledge_management": "Knowledge Management",
    "sla_task": "SLA Task",
    "analytics": "Proactive Analytics",
}

_TRUNCATE_BODY_AT = 2000
_TRUNCATE_SUFFIX = "...[truncated]"


def _truncate_body(text: str) -> str:
    """Truncate an error response body with a visible marker."""
    if len(text) > _TRUNCATE_BODY_AT:
        return text[:_TRUNCATE_BODY_AT] + _TRUNCATE_SUFFIX
    return text


def _err_body(e: requests.RequestException) -> str:
    """Extract and truncate the response body from a RequestException, or ''."""
    if e.response is not None:
        return _truncate_body(e.response.text)
    return ""


def _invoke_scripted_js(
    config: ServerConfig,
    auth_manager: AuthManager,
    script: str,
    *,
    log_prefix: str,
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    POST a JavaScript block to the configured scripted execution endpoint.

    Returns:
        (success, message, parsed_json) where parsed_json is from result.output when JSON.
    """
    if not config.script_execution_api_resource_path:
        return (
            False,
            "Script execution API is not configured (script_execution_api_resource_path).",
            None,
        )
    url = f"{config.instance_url.rstrip('/')}{config.script_execution_api_resource_path}"
    try:
        script_response = requests.post(
            url,
            json={"script": script},
            headers=auth_manager.get_headers(),
            timeout=max(config.timeout, 120),
        )
        script_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "%s | script POST failed | error=%s%s",
            log_prefix, e, f" | body={_body}" if _body else "",
        )
        return (
            False,
            f"Failed to run script: {e}" + (f" | response: {_body}" if _body else ""),
            None,
        )

    try:
        payload = script_response.json()
    except Exception:
        return False, "Script execution returned non-JSON response.", None

    result = payload.get("result", payload)
    status = result.get("status", "")
    output_str = result.get("output", "")

    if status == "error":
        return False, f"Script reported error: {output_str}", None

    try:
        data = json.loads(output_str) if output_str else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return False, f"Script output was not valid JSON: {output_str[:500]!r}", None

    if not isinstance(data, dict):
        return False, "Script output JSON was not an object.", None

    return True, "", data


# ---------------------------------------------------------------------------
# Record trigger input parameter definitions
# ---------------------------------------------------------------------------
# Each dict is a parameter definition object used by the Flow Designer renderInput
# component. Values extracted from sys_hub_flow_version.payload of a manually-created
# flow on dev296536 (2026-02-27). These are core platform config, stable within a release.
#
# Ordering note on choices vs defaultChoices:
#   'choices' uses 0-based 'order' values.
#   'defaultChoices' uses 1-based 'order' values for the same entries.
#   This mirrors the exact values observed in the instance payload and is intentional —
#   do not "fix" the 1-based defaultChoices to 0-based.


def _param(
    param_id: str,
    label: str,
    name: str,
    ptype: str,
    order: int,
    mandatory: bool = False,
    maxsize: int = 4000,
    reference: str = "",
    reference_display: str = "",
    dependent_on: str = "",
    default_value: str = "",
    default_display_value: str | None = None,
    attributes: dict[str, str] | None = None,
    choices: list[dict] | None = None,
    default_choices: list[dict] | None = None,
    extended: bool = False,
    choice_option: str = "",
    use_dependent: bool = False,
) -> dict:
    """Build a full parameter definition dict matching the Flow Designer payload schema.

    choices and default_choices are required for 'choice' type inputs so Flow Designer
    renders display labels instead of raw values. Values are confirmed from instance
    payload (sys_hub_flow_version) of a manually-created flow on dev296536 (2026-02-27).
    extended=True places the input under the Advanced Options dropdown in Flow Designer.
    choice_option="3" tells Flow Designer to render the field as a dropdown using choices.
    default_display_value is the human-readable label for the default value shown in the UI.
    """
    d = {
        "children": [],
        "id": param_id,
        "label": label,
        "name": name,
        "type": ptype,
        "order": order,
        "extended": extended,
        "mandatory": mandatory,
        "readOnly": False,
        "hint": "",
        "maxsize": maxsize,
        "reference": reference,
        "reference_display": reference_display,
        "choiceOption": choice_option,
        "table": "",
        "columnName": "",
        "defaultValue": default_value,
        "use_dependent": use_dependent,
        "fShowReferenceFinder": False,
        "local": False,
        "attributes": attributes if attributes is not None else {},
        "ref_qual": "",
        "dependent_on": dependent_on,
        "choices": choices if choices is not None else [],
        "defaultChoices": default_choices if default_choices is not None else [],
    }
    if default_display_value is not None:
        d["defaultDisplayValue"] = default_display_value
    return d


# Ordered list of all 8 standard record trigger inputs.
# Order matches Flow Designer UI: table, condition (always visible),
# then advanced options: run_when_setting, run_when_user_setting,
# run_when_user_list (conditional), run_on_extended, run_flow_in, trigger_strategy.
_RECORD_TRIGGER_INPUTS: list[dict] = [
    _param("cfca92e0c31322002841b63b12d3ae00", "Table",     "table",     "table_name", order=1,   mandatory=True,  maxsize=80,   attributes={"filter_table_source": "RECORD_WATCHER_RESTRICTED"}),
    _param("66aadea0c31322002841b63b12d3aebf", "Condition", "condition", "conditions", order=100, mandatory=False, maxsize=4000, dependent_on="table", use_dependent=True, attributes={"modelDependent": "trigger_inputs", "wants_to_add_conditions": "true"}),
    _param(
        "1e4859f3c7002300f4eba1425a9763f9", "run_when_setting", "run_when_setting", "choice",
        order=200, mandatory=False, maxsize=40, default_value="both",
        extended=True, attributes={"advanced": "true"}, choice_option="3",
        default_display_value="Run for Both Interactive and Non-Interactive Sessions",
        choices=[
            {"label": "Only Run for Non-Interactive Session",                 "value": "non_interactive", "order": 0},
            {"label": "Only Run for User Interactive Session",                "value": "interactive",     "order": 1},
            {"label": "Run for Both Interactive and Non-Interactive Sessions", "value": "both",           "order": 2},
        ],
        default_choices=[
            {"label": "Only Run for Non-Interactive Session",                 "value": "non_interactive", "order": 1},
            {"label": "Only Run for User Interactive Session",                "value": "interactive",     "order": 2},
            {"label": "Run for Both Interactive and Non-Interactive Sessions", "value": "both",           "order": 3},
        ],
    ),
    _param(
        "ed7a5537c7002300f4eba1425a976391", "run_when_user_setting", "run_when_user_setting", "choice",
        order=300, mandatory=False, maxsize=40, default_value="any",
        extended=True, attributes={"advanced": "true"}, choice_option="3",
        default_display_value="Run for any user",
        choices=[
            {"label": "Do not run if triggered by the following users", "value": "not_one_of", "order": 0},
            {"label": "Only Run if triggered by the following users",   "value": "one_of",     "order": 1},
            {"label": "Run for any user",                               "value": "any",        "order": 2},
        ],
        default_choices=[
            {"label": "Do not run if triggered by the following users", "value": "not_one_of", "order": 1},
            {"label": "Only Run if triggered by the following users",   "value": "one_of",     "order": 2},
            {"label": "Run for any user",                               "value": "any",        "order": 3},
        ],
    ),
    _param("f89c5177c7002300f4eba1425a976385", "run_when_user_list", "run_when_user_list", "glide_list", order=400, mandatory=False, maxsize=4000, reference="sys_user", reference_display="User", dependent_on="run_when_user_setting", extended=True, attributes={"advanced": "true"}),
    _param(
        "11ffbef2072200103bf10705afd300c2", "run_on_extended", "run_on_extended", "choice",
        order=500, mandatory=False, maxsize=40, default_value="false",
        extended=True, attributes={"advanced": "true"}, choice_option="3",
        default_display_value="Run only on current table",
        choices=[
            {"label": "Run only on current table",         "value": "false", "order": 0},
            {"label": "Run on current and extended tables", "value": "true",  "order": 1},
        ],
        default_choices=[
            {"label": "Run only on current table",         "value": "false", "order": 1},
            {"label": "Run on current and extended tables", "value": "true",  "order": 2},
        ],
    ),
    _param(
        "3f1b9e4e0f103300b599bca2ff767e21", "run_flow_in", "run_flow_in", "choice",
        order=600, mandatory=False, maxsize=40, default_value="background",
        extended=True, attributes={"advanced": "true"}, choice_option="3",
        default_display_value="Run flow in background (default)",
        choices=[
            {"label": "Run flow in background (default)", "value": "background", "order": 0},
            {"label": "Run flow in foreground",           "value": "foreground", "order": 1},
        ],
        default_choices=[
            {"label": "Run flow in background (default)", "value": "background", "order": 1},
            {"label": "Run flow in foreground",           "value": "foreground", "order": 2},
        ],
    ),
    # "Run Trigger" — controls how often the flow fires per record lifecycle.
    # sys_id confirmed from sys_hub_trigger_input on dev296536 (2026-02-28).
    # Appears as the 8th input in saved flow version payloads; platform injects it
    # with default "once" if omitted, but including it ensures correct Advanced Options rendering.
    _param(
        "2b9def50c31132002841b63b12d3ae5b", "Run Trigger", "trigger_strategy", "choice",
        order=700, mandatory=False, maxsize=40, default_value="once",
        extended=True, attributes={"advanced": "true"}, choice_option="3",
        default_display_value="Once",
        choices=[
            {"label": "Once",                          "value": "once",           "order": 1},
            {"label": "For each unique change",        "value": "unique_changes", "order": 2},
            {"label": "Only if not currently running", "value": "always",         "order": 3},
            {"label": "For every update",              "value": "every",          "order": 4},
        ],
        default_choices=[
            {"label": "Once",                          "value": "once",           "order": 1},
            {"label": "For each unique change",        "value": "unique_changes", "order": 2},
            {"label": "Only if not currently running", "value": "always",         "order": 3},
            {"label": "For every update",              "value": "every",          "order": 4},
        ],
    ),
]
_RECORD_TRIGGER_INPUT_BY_NAME = {p["name"]: p for p in _RECORD_TRIGGER_INPUTS}
_RECORD_TRIGGER_TYPES = {"record_create", "record_create_or_update", "record_update"}


def _lookup_table_label(config: ServerConfig, auth_manager: AuthManager, table_name: str) -> str:
    """Return the display label for a table from sys_db_object (e.g. 'incident' → 'Incident').
    Falls back to title-casing the table name if the lookup fails or returns empty.
    """
    try:
        response = requests.get(
            f"{config.api_url}/table/sys_db_object",
            params={
                "sysparm_query": f"name={table_name}",
                "sysparm_fields": "label",
                "sysparm_limit": 1,
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        records = response.json().get("result", [])
        if records:
            label = records[0].get("label", "")
            if label:
                return label
    except requests.RequestException as e:
        logger.warning("_lookup_table_label | failed | table=%s | error=%s", table_name, e)
    return table_name.replace("_", " ").title()


def list_trigger_types(
    config: ServerConfig,
    auth_manager: AuthManager,
    _params: ListTriggerTypesParams,
) -> ListTriggerTypesResult:
    """
    List all available Flow Designer trigger types from sys_hub_trigger_type.

    Returns sys_hub_trigger_definition sys_ids (V2 trigger catalog) by traversing
    sys_hub_trigger_type.base_trigger. These are the correct ids for create_flow's
    trigger_definition_id field — sys_hub_trigger_instance.trigger_definition references
    sys_hub_trigger_definition, not sys_hub_trigger_type.

    Returns up to 200 trigger types. If your instance has more, use
    list_trigger_types with a direct Table API query and sysparm_offset to paginate.
    """
    try:
        response = requests.get(
            f"{config.api_url}/table/sys_hub_trigger_type",
            params={
                "sysparm_fields": "sys_id,name,internal_name,base_trigger",
                "sysparm_limit": 200,
                "sysparm_orderby": "name",
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("list_trigger_types | request failed | error=%s%s", e, f" | body={_body}" if _body else "")
        return ListTriggerTypesResult(
            trigger_types=[],
            message=f"Failed to fetch trigger types: {e}" + (f" | response: {_body}" if _body else ""),
        )

    records = response.json().get("result", [])
    # Build a reverse map from display name → type string for annotation
    _name_to_type = {v: k for k, v in _TRIGGER_TYPE_NAME_MAP.items()}

    trigger_types = []
    for r in records:
        # base_trigger references sys_hub_trigger_definition — extract its sys_id.
        # The Table API returns reference fields as {value, display_value, link} objects.
        raw_base = r.get("base_trigger")
        trigger_def_id = raw_base.get("value") if isinstance(raw_base, dict) else (raw_base or None)
        if not trigger_def_id:
            logger.warning(
                "list_trigger_types | base_trigger empty for '%s', sys_hub_trigger_type.sys_id used as fallback",
                r.get("name", ""),
            )
        trigger_types.append(TriggerTypeInfo(
            sys_id=trigger_def_id or r["sys_id"],
            name=r.get("name", ""),
            type_string=r.get("internal_name") or _name_to_type.get(r.get("name", "")),
        ))

    logger.info("list_trigger_types | found %d trigger types", len(trigger_types))
    truncation_note = " (result capped at 200 — instance may have more)" if len(trigger_types) == 200 else ""
    return ListTriggerTypesResult(
        trigger_types=trigger_types,
        message=f"Found {len(trigger_types)} trigger type(s){truncation_note}. Use sys_id as trigger_definition_id in create_flow.",
    )


def _resolve_trigger_definition_id(
    config: ServerConfig,
    auth_manager: AuthManager,
    type_str: str,
) -> tuple[str | None, str | None]:
    """
    Resolve a trigger type string (e.g. 'record_create') to its sys_hub_trigger_definition
    sys_id on this instance.

    Queries sys_hub_trigger_type by display name (e.g. 'Created' for 'record_create'),
    then traverses base_trigger to get the sys_hub_trigger_definition sys_id. That is the
    correct value for triggerDefinitionId in the processflow PUT body, since
    sys_hub_trigger_instance.trigger_definition references sys_hub_trigger_definition.

    Returns (sys_hub_trigger_definition_sys_id, None) on success, or (None, error_message)
    on failure. Falls back to sys_hub_trigger_type.sys_id with a warning if base_trigger
    is absent.
    """
    display_name = _TRIGGER_TYPE_NAME_MAP.get(type_str.lower())
    if not display_name:
        # Caller may have passed the display name directly (e.g. "Created").
        # Normalise to title-case so "CREATED" or "created" also resolve correctly.
        display_name = type_str.strip().title()

    try:
        response = requests.get(
            f"{config.api_url}/table/sys_hub_trigger_type",
            params={
                "sysparm_query": f"name={display_name}",
                "sysparm_fields": "sys_id,name,base_trigger",
                "sysparm_limit": 1,
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return None, f"Failed to query sys_hub_trigger_type: {e}" + (f" | body: {_body}" if _body else "")

    records = response.json().get("result", [])
    if not records:
        return None, (
            f"No trigger type found with name='{display_name}' (resolved from type='{type_str}'). "
            f"Call list_trigger_types to see available options."
        )

    rec = records[0]
    # base_trigger references sys_hub_trigger_definition — that sys_id is what the
    # processflow PUT body needs as triggerDefinitionId.
    raw_base = rec.get("base_trigger")
    trigger_def_id = raw_base.get("value") if isinstance(raw_base, dict) else (raw_base or None)

    if trigger_def_id:
        logger.info(
            "_resolve_trigger_definition_id | type=%s | name=%s | trigger_def_id=%s",
            type_str, display_name, trigger_def_id,
        )
        return trigger_def_id, None

    # base_trigger was absent — fall back to sys_hub_trigger_type.sys_id with a warning.
    fallback_id = rec["sys_id"]
    logger.warning(
        "_resolve_trigger_definition_id | base_trigger empty for type=%s name=%s, "
        "using sys_hub_trigger_type.sys_id=%s as fallback — trigger may not attach correctly",
        type_str, display_name, fallback_id,
    )
    return fallback_id, None


def create_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateFlowParams,
) -> CreateFlowResponse:
    """
    Create a new Flow Designer flow in ServiceNow.

    Uses the internal /api/now/processflow/ API (not the Table API), which is the
    only mechanism that can persist trigger instances and action instances. The
    sys_hub_flow_snapshot table is read-only via the Table API.

    Sequence:
      1. POST /processflow/flow                      — create the flow shell
      2. POST /processflow/versioning/create_version — initial autosave
      3. Resolve trigger_definition_id via sys_hub_trigger_type.base_trigger → sys_hub_trigger_definition (if not supplied)
      4. Build trigger + action instance payloads
      5. PUT  /processflow/flow                      — attach trigger and actions
      6. POST /processflow/versioning/create_version — final Save version (type='Save',
         not 'Autosave', so Flow Designer reads advanced options from the saved version)
      7. PATCH sys_hub_flow_version                  — set fTriggerType='Record' in payload
         (a Business Rule overwrites it; patching the serialised payload is the only fix)
      8. DELETE sys_hub_flow_safe_edit               — release the Flow Designer edit lock

    Args:
        config: Server configuration (instance_url, auth, timeout).
        auth_manager: Authentication manager.
        params: Flow creation parameters.

    Returns:
        CreateFlowResponse with success flag, message, and flow identifiers.
        When success=False but flow_sys_id is set, a partial shell was created.
    """
    processflow_base = f"{config.api_url}/processflow"
    headers = auth_manager.get_headers()

    # ------------------------------------------------------------------
    # Step 1: Create the flow shell
    # ------------------------------------------------------------------
    shell_body = {
        "name": params.name,
        "type": "flow",
        "scope": params.scope,
        "runAs": params.run_as,
        "access": params.access,
        "flowPriority": params.flow_priority,
        "status": "draft",
        "active": False,
        "deleted": False,
        "security": {"can_read": True, "can_write": True},
        "scopeName": "",
        "scopeDisplayName": "",
        "userHasRolesAssignedToFlow": True,
        "runWithRoles": {"value": "", "displayValue": ""},
        "description": params.description or "",
        "protection": "",
    }

    try:
        shell_response = requests.post(
            f"{processflow_base}/flow",
            params={
                "param_only_properties": "true",
                "sysparm_transaction_scope": "global",
            },
            json=shell_body,
            headers=headers,
            timeout=config.timeout,
        )
        shell_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("create_flow | shell POST failed | error=%s%s", e, f" | body={_body}" if _body else "")
        return CreateFlowResponse(
            success=False,
            message=f"Failed to create flow shell: {e}" + (f" | response: {_body}" if _body else ""),
        )

    shell_result = shell_response.json()
    flow_data = shell_result.get("result", {}).get("data", {})
    flow_sys_id = flow_data.get("id")
    flow_internal_name = flow_data.get("internalName")

    if not flow_sys_id:
        logger.error(
            "create_flow | shell POST succeeded but no id in response | response=%s",
            shell_result,
        )
        return CreateFlowResponse(
            success=False,
            message=(
                "Flow shell POST returned HTTP 200 but no flow id was found in the response. "
                f"Raw response: {shell_result}"
            ),
        )

    logger.info("create_flow | shell created | flow_sys_id=%s", flow_sys_id)

    # ------------------------------------------------------------------
    # Step 2: Initial autosave version
    # ------------------------------------------------------------------
    autosave_body = {
        "item_sys_id": flow_sys_id,
        "type": "Autosave",
        "annotation": "",
        "favorite": False,
    }
    version_query_params = {"sysparm_transaction_scope": "global"}

    try:
        requests.post(
            f"{processflow_base}/versioning/create_version",
            params=version_query_params,
            json=autosave_body,
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
        logger.info("create_flow | initial autosave created | flow_sys_id=%s", flow_sys_id)
    except requests.RequestException as e:
        _body = _err_body(e)
        # Non-fatal: the shell exists and the PUT can still proceed.
        # Surface the failure in a warning so it is visible if the subsequent PUT fails.
        logger.warning(
            "create_flow | initial autosave failed (non-fatal) | flow_sys_id=%s | error=%s%s",
            flow_sys_id, e, f" | body={_body}" if _body else "",
        )

    # ------------------------------------------------------------------
    # Steps 3–4: Resolve trigger_definition_id, build payloads
    # ------------------------------------------------------------------
    # Resolve the trigger definition id into a local variable — do NOT mutate
    # params.trigger in place, as that would modify the caller's model object.
    trigger_definition_id: str | None = None
    if params.trigger:
        trigger_definition_id = params.trigger.trigger_definition_id
        if not trigger_definition_id:
            resolved_id, resolve_err = _resolve_trigger_definition_id(
                config, auth_manager, params.trigger.type
            )
            if resolve_err:
                return CreateFlowResponse(
                    success=False,
                    message=(
                        f"Flow shell was created (sys_id={flow_sys_id}) but trigger type "
                        f"could not be resolved: {resolve_err}. The draft shell exists in Flow Designer."
                    ),
                    flow_sys_id=flow_sys_id,
                    flow_name=params.name,
                    flow_internal_name=flow_internal_name,
                )
            trigger_definition_id = resolved_id

    trigger_instances = _build_trigger_instances(
        config, auth_manager, params.trigger, flow_sys_id, trigger_definition_id
    )
    action_instances = _build_action_instances(flow_sys_id, params.actions)

    # ------------------------------------------------------------------
    # Step 5: PUT to save trigger + actions onto the flow
    # ------------------------------------------------------------------
    put_body = dict(flow_data)
    put_body["triggerInstances"] = trigger_instances
    put_body["actionInstances"] = action_instances

    try:
        put_response = requests.put(
            f"{processflow_base}/flow",
            params={"sysparm_transaction_scope": "global"},
            json=put_body,
            headers=headers,
            timeout=config.timeout,
        )
        put_response.raise_for_status()
        logger.info(
            "create_flow | PUT saved | flow_sys_id=%s | triggers=%d | actions=%d",
            flow_sys_id, len(trigger_instances), len(action_instances),
        )
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "create_flow | PUT failed | flow_sys_id=%s | error=%s%s",
            flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return CreateFlowResponse(
            success=False,
            message=(
                f"Flow shell was created (sys_id={flow_sys_id}) but the PUT to attach "
                f"trigger/actions failed: {e}. The draft shell exists in Flow Designer."
                + (f" | response: {_body}" if _body else "")
            ),
            flow_sys_id=flow_sys_id,
            flow_name=params.name,
            flow_internal_name=flow_internal_name,
        )

    # ------------------------------------------------------------------
    # Step 6: Final Save version
    # ------------------------------------------------------------------
    # Use type="Save" (not "Autosave") so Flow Designer reads the trigger's
    # advanced options from a proper saved version. Autosave versions cause
    # the advanced options dropdown to render incorrectly (5 items vs 4).
    final_version_body = {
        "item_sys_id": flow_sys_id,
        "type": "Save",
        "annotation": "",
        "favorite": False,
    }
    try:
        requests.post(
            f"{processflow_base}/versioning/create_version",
            params=version_query_params,
            json=final_version_body,
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
        logger.info("create_flow | final Save version created | flow_sys_id=%s", flow_sys_id)
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.warning(
            "create_flow | final Save version failed (non-fatal) | flow_sys_id=%s | error=%s%s",
            flow_sys_id, e, f" | body={_body}" if _body else "",
        )

    # ------------------------------------------------------------------
    # Step 7: Patch fTriggerType='Record' in the saved version payload
    # ------------------------------------------------------------------
    # The processflow PUT cannot set fTriggerType reliably — a Business Rule overwrites
    # it using a sys_hub_trigger_type (V1 catalog) field the service account cannot read.
    # Patching the serialised payload via the Table API is the only reliable fix.
    # Non-fatal: the flow functions correctly; only the trigger label in the UI is affected.
    if params.trigger and params.trigger.type in _RECORD_TRIGGER_TYPES:
        patch_err = _patch_flow_version_trigger_type(config, auth_manager, flow_sys_id)
        if patch_err:
            logger.warning(
                "create_flow | fTriggerType patch failed (non-fatal) | flow_sys_id=%s | error=%s",
                flow_sys_id, patch_err,
            )

    # ------------------------------------------------------------------
    # Step 8: Release Flow Designer edit lock
    # ------------------------------------------------------------------
    # The processflow API writes a sys_hub_flow_safe_edit record that makes the flow
    # appear locked ('being edited by <user>') in the UI. Deleting it via the Table
    # API releases the lock. GraphQL safeEdit does not work for service accounts.
    # Non-fatal: log a warning but do not fail the overall creation response.
    lock_err = _release_flow_edit_lock(config, auth_manager, flow_sys_id)
    if lock_err:
        logger.warning(
            "create_flow | safeEdit lock release failed (non-fatal) | flow_sys_id=%s | error=%s",
            flow_sys_id, lock_err,
        )

    return CreateFlowResponse(
        success=True,
        message=(
            f"Flow '{params.name}' created successfully in draft state. "
            f"sys_id={flow_sys_id}. "
            f"Open in Flow Designer to review, activate, and test."
        ),
        flow_sys_id=flow_sys_id,
        flow_name=params.name,
        flow_internal_name=flow_internal_name,
    )


# ---------------------------------------------------------------------------
# Generic artifact lifecycle tools (flow/subflow/action)
# ---------------------------------------------------------------------------

_ARTIFACT_TYPE_MAP = {
    "flow": "flow",
    "subflow": "subflow",
    "action": "action",
}


def _coerce_bool(value: Any) -> bool:
    """Normalize ServiceNow truthy string/boolean values to bool."""
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes"}


def _build_artifact_query(artifact_type: str, params: ListArtifactsParams) -> str:
    """Build encoded query for sys_hub_flow artifact filtering."""
    clauses = [f"type={artifact_type}"]
    if params.active is not None:
        clauses.append(f"active={str(params.active).lower()}")
    if params.query:
        clauses.append(params.query)
    return "^".join(clauses)


def _list_artifacts(
    config: ServerConfig,
    auth_manager: AuthManager,
    artifact_type: str,
    params: ListArtifactsParams,
) -> ListArtifactsResponse:
    """List flow/subflow/action artifacts from sys_hub_flow."""
    try:
        response = requests.get(
            f"{config.api_url}/table/sys_hub_flow",
            params={
                "sysparm_query": _build_artifact_query(artifact_type, params),
                "sysparm_fields": (
                    "sys_id,name,internal_name,description,type,active,published"
                ),
                "sysparm_limit": params.limit,
                "sysparm_offset": params.offset,
                "sysparm_orderby": "name",
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return ListArtifactsResponse(
            artifacts=[],
            count=0,
            message=f"Failed to list {artifact_type}s: {e}" + (f" | response: {_body}" if _body else ""),
        )

    records = response.json().get("result", [])
    artifacts = [
        ArtifactSummary(
            sys_id=r.get("sys_id", ""),
            name=r.get("name", ""),
            artifact_type=r.get("type", artifact_type),
            description=r.get("description"),
            active=_coerce_bool(r.get("active", False)),
            published=_coerce_bool(r.get("published", False)),
            internal_name=r.get("internal_name"),
        )
        for r in records
    ]
    return ListArtifactsResponse(
        artifacts=artifacts,
        count=len(artifacts),
        message=f"Found {len(artifacts)} {artifact_type}(s).",
    )


def _get_artifact(
    config: ServerConfig,
    auth_manager: AuthManager,
    artifact_type: str,
    sys_id: str,
) -> GetArtifactResponse:
    """Get one flow/subflow/action artifact from sys_hub_flow."""
    try:
        response = requests.get(
            f"{config.api_url}/table/sys_hub_flow/{sys_id}",
            params={
                "sysparm_fields": (
                    "sys_id,name,internal_name,description,type,active,published,"
                    "access,run_as,flow_priority,sys_created_on,sys_updated_on"
                )
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return GetArtifactResponse(
            artifact=None,
            message=f"Failed to get {artifact_type} '{sys_id}': {e}" + (f" | response: {_body}" if _body else ""),
        )

    record = response.json().get("result", {})
    actual_type = record.get("type")
    if actual_type and actual_type != artifact_type:
        return GetArtifactResponse(
            artifact=record,
            message=(
                f"Record '{sys_id}' exists but type is '{actual_type}', not expected '{artifact_type}'."
            ),
        )

    return GetArtifactResponse(
        artifact=record,
        message=f"Retrieved {artifact_type} '{sys_id}'.",
    )


def _create_artifact(
    config: ServerConfig,
    auth_manager: AuthManager,
    artifact_type: str,
    params: CreateArtifactParams,
) -> MutationResponse:
    """Create a flow/subflow/action shell via processflow API."""
    processflow_base = f"{config.api_url}/processflow"
    body = {
        "name": params.name,
        "type": _ARTIFACT_TYPE_MAP[artifact_type],
        "scope": params.scope,
        "runAs": params.run_as,
        "access": params.access,
        "flowPriority": params.flow_priority,
        "status": "draft",
        "active": False,
        "deleted": False,
        "security": {"can_read": True, "can_write": True},
        "scopeName": "",
        "scopeDisplayName": "",
        "userHasRolesAssignedToFlow": True,
        "runWithRoles": {"value": "", "displayValue": ""},
        "description": params.description or "",
        "protection": "",
    }
    try:
        response = requests.post(
            f"{processflow_base}/flow",
            params={
                "param_only_properties": "true",
                "sysparm_transaction_scope": "global",
            },
            json=body,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return MutationResponse(
            success=False,
            message=f"Failed to create {artifact_type}: {e}" + (f" | response: {_body}" if _body else ""),
        )

    data = response.json().get("result", {}).get("data", {})
    artifact_sys_id = data.get("id")
    if not artifact_sys_id:
        return MutationResponse(
            success=False,
            message=f"{artifact_type.capitalize()} shell create returned no sys_id.",
        )

    return MutationResponse(
        success=True,
        message=f"Created {artifact_type} '{params.name}' in draft state.",
        sys_id=artifact_sys_id,
        name=params.name,
    )


def _update_artifact(
    config: ServerConfig,
    auth_manager: AuthManager,
    artifact_type: str,
    params: UpdateArtifactParams,
) -> MutationResponse:
    """Patch mutable fields on a flow/subflow/action record."""
    patch_fields: dict[str, Any] = {}
    if params.name is not None:
        patch_fields["name"] = params.name
    if params.description is not None:
        patch_fields["description"] = params.description
    if params.run_as is not None:
        patch_fields["run_as"] = params.run_as
    if params.access is not None:
        patch_fields["access"] = params.access
    if params.flow_priority is not None:
        patch_fields["flow_priority"] = params.flow_priority
    if params.active is not None:
        patch_fields["active"] = params.active

    if not patch_fields:
        return MutationResponse(
            success=False,
            message=f"No update fields provided for {artifact_type} '{params.sys_id}'.",
            sys_id=params.sys_id,
        )

    try:
        response = requests.patch(
            f"{config.api_url}/table/sys_hub_flow/{params.sys_id}",
            json=patch_fields,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return MutationResponse(
            success=False,
            message=f"Failed to update {artifact_type} '{params.sys_id}': {e}" + (f" | response: {_body}" if _body else ""),
            sys_id=params.sys_id,
        )

    return MutationResponse(
        success=True,
        message=f"Updated {artifact_type} '{params.sys_id}'.",
        sys_id=params.sys_id,
        name=params.name,
    )


def _publish_artifact(
    config: ServerConfig,
    auth_manager: AuthManager,
    artifact_type: str,
    params: PublishArtifactParams,
) -> MutationResponse:
    """Publish a flow/subflow/action via versioning API."""
    processflow_base = f"{config.api_url}/processflow"
    try:
        version_response = requests.post(
            f"{processflow_base}/versioning/create_version",
            params={"sysparm_transaction_scope": "global"},
            json={
                "item_sys_id": params.sys_id,
                "type": "Publish",
                "annotation": params.annotation or "",
                "favorite": False,
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        version_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return MutationResponse(
            success=False,
            message=f"Failed to publish {artifact_type} '{params.sys_id}': {e}" + (f" | response: {_body}" if _body else ""),
            sys_id=params.sys_id,
        )

    # Best effort state sync on the parent record.
    try:
        requests.patch(
            f"{config.api_url}/table/sys_hub_flow/{params.sys_id}",
            json={"active": True, "published": True},
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        ).raise_for_status()
    except requests.RequestException as e:
        logger.warning("_publish_artifact | record patch failed | artifact=%s | sys_id=%s | error=%s", artifact_type, params.sys_id, e)

    return MutationResponse(
        success=True,
        message=f"Published {artifact_type} '{params.sys_id}'.",
        sys_id=params.sys_id,
    )


def update_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateFlowParams,
) -> MutationResponse:
    """Update a flow artifact."""
    return _update_artifact(config, auth_manager, "flow", params)


def create_subflow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateSubflowParams,
) -> MutationResponse:
    """Create a subflow artifact shell."""
    return _create_artifact(config, auth_manager, "subflow", params)


def list_subflows(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListSubflowsParams,
) -> ListArtifactsResponse:
    """List subflow artifacts."""
    return _list_artifacts(config, auth_manager, "subflow", params)


def get_subflow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetSubflowParams,
) -> GetArtifactResponse:
    """Get a subflow artifact by sys_id."""
    return _get_artifact(config, auth_manager, "subflow", params.sys_id)


def update_subflow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateSubflowParams,
) -> MutationResponse:
    """Update a subflow artifact."""
    return _update_artifact(config, auth_manager, "subflow", params)


def publish_subflow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: PublishSubflowParams,
) -> MutationResponse:
    """Publish a subflow artifact."""
    return _publish_artifact(config, auth_manager, "subflow", params)


def create_action(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateActionParams,
) -> MutationResponse:
    """Create a custom action artifact shell."""
    return _create_artifact(config, auth_manager, "action", params)


def list_actions(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListActionsParams,
) -> ListArtifactsResponse:
    """List custom action artifacts."""
    return _list_artifacts(config, auth_manager, "action", params)


def get_action(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetActionParams,
) -> GetArtifactResponse:
    """Get a custom action artifact by sys_id."""
    return _get_artifact(config, auth_manager, "action", params.sys_id)


def update_action(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateActionParams,
) -> MutationResponse:
    """Update a custom action artifact."""
    return _update_artifact(config, auth_manager, "action", params)


def publish_action(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: PublishActionParams,
) -> MutationResponse:
    """Publish a custom action artifact."""
    return _publish_artifact(config, auth_manager, "action", params)


def list_action_types(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListActionTypesParams,
) -> ListActionTypesResult:
    """
    Search the action type catalog for action types matching a name query.

    Returns both definition_sys_id (for list_action_type_inputs) and
    base_sys_id (for ActionInstanceParam.action_type_sys_id in add_steps_to_flow
    and create_flow). These are different sys_ids for the same action — both are
    needed for the full create-and-configure workflow.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Query string and limit.

    Returns:
        ListActionTypesResult with matching action types.
    """
    try:
        response = requests.get(
            f"{config.api_url}/table/sys_hub_action_type_definition",
            params={
                "sysparm_query": f"nameCONTAINS{params.query}^ORinternal_nameCONTAINS{params.query}",
                "sysparm_fields": "sys_id,name,internal_name,action_type_base,spoke,description",
                "sysparm_display_value": "true",
                "sysparm_limit": params.limit,
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "list_action_types | request failed | query=%s | error=%s%s",
            params.query, e, f" | body={_body}" if _body else "",
        )
        return ListActionTypesResult(
            action_types=[],
            message=f"Failed to fetch action types: {e}" + (f" | body: {_body}" if _body else ""),
        )

    records = response.json().get("result", [])
    action_types = []
    for r in records:
        # action_type_base is a reference field; with display_value=true it comes as
        # {"value": "<sys_id>", "display_value": "<name>"} or just a plain string.
        atb = r.get("action_type_base", {})
        base_sys_id = atb.get("value", "") if isinstance(atb, dict) else str(atb or "")
        spoke_field = r.get("spoke", {})
        spoke_name = spoke_field.get("display_value") if isinstance(spoke_field, dict) else str(spoke_field or "")
        action_types.append(ActionTypeSummary(
            definition_sys_id=r["sys_id"],
            base_sys_id=base_sys_id,
            name=r.get("name", ""),
            internal_name=r.get("internal_name") or None,
            spoke=spoke_name or None,
            description=r.get("description") or None,
        ))

    logger.info("list_action_types | query=%s | found %d result(s)", params.query, len(action_types))
    return ListActionTypesResult(
        action_types=action_types,
        message=f"Found {len(action_types)} action type(s) matching '{params.query}'.",
    )


def list_action_type_inputs(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListActionTypeInputsParams,
) -> ListActionTypeInputsResult:
    """
    Return all input parameter definitions for a given action type.

    Queries sys_hub_action_input filtered by definition sys_id and returns
    the sys_id, name, label, type, mandatory flag, and default value for each
    input. The sys_id field maps directly to ActionInputParam.id in
    create_flow and add_steps_to_flow — eliminating the need to hardcode
    instance-specific parameter sys_ids.

    NOTE: The logical name of each input is in the 'element' field (not 'name').
    The query field is 'model=' (not 'action_type=').
    Both verified against live sys_hub_action_input records.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Contains action_type_sys_id (definition sys_id) to query against.

    Returns:
        ListActionTypeInputsResult with the inputs list and a summary message.
    """
    try:
        response = requests.get(
            f"{config.api_url}/table/sys_hub_action_input",
            params={
                # NOTE: The query field is `model`, NOT `action_type` — verified against live instance.
                # `action_type` does not exist on sys_hub_action_input.
                "sysparm_query": f"model={params.action_type_sys_id}",
                "sysparm_fields": "sys_id,element,label,type,mandatory,default_value,order",
                "sysparm_orderby": "order",
                "sysparm_limit": 200,
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "list_action_type_inputs | request failed | action_type=%s | error=%s%s",
            params.action_type_sys_id, e, f" | body={_body}" if _body else "",
        )
        return ListActionTypeInputsResult(
            action_type_sys_id=params.action_type_sys_id,
            inputs=[],
            message=f"Failed to fetch action type inputs: {e}" + (f" | body: {_body}" if _body else ""),
        )

    records = response.json().get("result", [])
    inputs = [
        ActionTypeInput(
            sys_id=r["sys_id"],
            # element = logical name (e.g. "table", "conditions") — NOT the `name` field.
            # Verified against live sys_hub_action_input records.
            name=r.get("element", ""),
            label=r.get("label", ""),
            type=r.get("type", ""),
            mandatory=_coerce_bool(r.get("mandatory", False)),
            default_value=r.get("default_value") or None,
            order=int(r.get("order") or 0),
        )
        for r in records
    ]
    logger.info(
        "list_action_type_inputs | action_type=%s | found %d inputs",
        params.action_type_sys_id, len(inputs),
    )
    return ListActionTypeInputsResult(
        action_type_sys_id=params.action_type_sys_id,
        inputs=inputs,
        message=f"Found {len(inputs)} input(s) for action type {params.action_type_sys_id}.",
    )


def list_flow_logic_types(
    config: ServerConfig,
    auth_manager: AuthManager,
    _params: ListFlowLogicTypesParams,
) -> ListFlowLogicTypesResult:
    """
    List all available Flow Designer logic step types (If, Switch, For Each, etc.).

    Calls GET /api/now/processflow/flow_logic/types. The sys_id values returned
    are the identifiers needed to add flow logic steps to a flow payload.
    """
    try:
        response = requests.get(
            f"{config.api_url}/processflow/flow_logic/types",
            params={"sysparm_transaction_scope": "global"},
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("list_flow_logic_types | request failed | error=%s%s", e, f" | body={_body}" if _body else "")
        return ListFlowLogicTypesResult(
            logic_types=[],
            message=f"Failed to fetch flow logic types: {e}" + (f" | body: {_body}" if _body else ""),
        )

    data = response.json()
    # The API may return {"result": [...]} or a bare list.
    raw = data.get("result", data) if isinstance(data, dict) else data
    logic_types: list[FlowLogicType] = []
    if isinstance(raw, list):
        for t in raw:
            if isinstance(t, dict):
                logic_types.append(FlowLogicType(
                    sys_id=t.get("sys_id") or t.get("id", ""),
                    name=t.get("name") or t.get("label", ""),
                    label=t.get("label"),
                    type_string=t.get("type") or t.get("typeString"),
                ))

    logger.info("list_flow_logic_types | found %d logic type(s)", len(logic_types))
    return ListFlowLogicTypesResult(
        logic_types=logic_types,
        message=f"Found {len(logic_types)} flow logic type(s).",
    )


def add_steps_to_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: AddStepsToFlowParams,
) -> AddStepsToFlowResponse:
    """
    Add action steps to an existing flow using the GET→mutate→PUT pattern.

    Sequence:
      1. GET /processflow/flow/{sys_id}       — fetch current payload
      2. Append new action instances           — built via _build_action_instances
      3. PUT /processflow/flow                 — write back modified payload
      4. POST /processflow/versioning/create_version — save a new version

    The flow must exist. Order values in params.actions must not clash with
    existing steps — use get_flow_actions first to see current orders.
    """
    processflow_base = f"{config.api_url}/processflow"
    headers = auth_manager.get_headers()

    # Step 1: GET current flow payload
    try:
        get_response = requests.get(
            f"{processflow_base}/flow/{params.flow_sys_id}",
            headers=headers,
            timeout=config.timeout,
        )
        get_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("add_steps_to_flow | GET failed | flow_sys_id=%s | error=%s%s", params.flow_sys_id, e, f" | body={_body}" if _body else "")
        return AddStepsToFlowResponse(
            success=False,
            message=f"Failed to fetch flow {params.flow_sys_id}: {e}" + (f" | body: {_body}" if _body else ""),
        )

    flow_data = get_response.json().get("result", {}).get("data", {})
    if not flow_data:
        return AddStepsToFlowResponse(
            success=False,
            message=f"GET /processflow/flow/{params.flow_sys_id} returned no data.",
            flow_sys_id=params.flow_sys_id,
        )

    # Step 2: Append new action instances to existing ones
    new_instances = _build_action_instances(params.flow_sys_id, params.actions)
    flow_data["actionInstances"] = (flow_data.get("actionInstances") or []) + new_instances

    # Step 3: PUT modified payload back
    try:
        put_response = requests.put(
            f"{processflow_base}/flow",
            params={"sysparm_transaction_scope": "global"},
            json=flow_data,
            headers=headers,
            timeout=config.timeout,
        )
        put_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("add_steps_to_flow | PUT failed | flow_sys_id=%s | error=%s%s", params.flow_sys_id, e, f" | body={_body}" if _body else "")
        return AddStepsToFlowResponse(
            success=False,
            message=f"Failed to update flow {params.flow_sys_id}: {e}" + (f" | body: {_body}" if _body else ""),
            flow_sys_id=params.flow_sys_id,
        )

    # Step 4: Save version (non-fatal if it fails)
    try:
        requests.post(
            f"{processflow_base}/versioning/create_version",
            params={"sysparm_transaction_scope": "global"},
            json={
                "item_sys_id": params.flow_sys_id,
                "type": "Save",
                "annotation": "",
                "favorite": False,
            },
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
        logger.info("add_steps_to_flow | version saved | flow_sys_id=%s", params.flow_sys_id)
    except requests.RequestException as e:
        logger.warning("add_steps_to_flow | create_version failed (non-fatal) | flow_sys_id=%s | error=%s", params.flow_sys_id, e)

    logger.info("add_steps_to_flow | success | flow_sys_id=%s | steps_added=%d", params.flow_sys_id, len(params.actions))
    return AddStepsToFlowResponse(
        success=True,
        message=f"Added {len(params.actions)} step(s) to flow {params.flow_sys_id}.",
        flow_sys_id=params.flow_sys_id,
        steps_added=len(params.actions),
    )


def add_subflow_step_to_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: AddSubflowStepToFlowParams,
) -> AddSubflowStepToFlowResponse:
    """
    Add a subflow invocation step to a parent flow.

    Uses GET /processflow/flow/{flow}, appends one entry to ``subFlowInstances``,
    PUT, and create_version (same pattern as add_steps_to_flow). The payload
    field ``subFlowSysId`` references the subflow record; inputs use
    ``sys_hub_flow_input.sys_id`` as ``id`` (see list_flow_io on the subflow).
    """
    parent_check = _get_artifact(config, auth_manager, "flow", params.flow_sys_id)
    if not parent_check.artifact:
        return AddSubflowStepToFlowResponse(
            success=False,
            message=parent_check.message or f"Flow {params.flow_sys_id} not found.",
        )
    ptype = parent_check.artifact.get("type")
    ptype_s = str(ptype.get("value") if isinstance(ptype, dict) else ptype or "").lower()
    if ptype_s and ptype_s != "flow":
        return AddSubflowStepToFlowResponse(
            success=False,
            message=f"flow_sys_id must reference type=flow; got type={ptype_s}.",
        )

    sub_check = _get_artifact(config, auth_manager, "subflow", params.subflow_sys_id)
    if not sub_check.artifact:
        return AddSubflowStepToFlowResponse(
            success=False,
            message=sub_check.message or f"Subflow {params.subflow_sys_id} not found.",
        )
    stype = sub_check.artifact.get("type")
    stype_s = str(stype.get("value") if isinstance(stype, dict) else stype or "").lower()
    if stype_s and stype_s != "subflow":
        return AddSubflowStepToFlowResponse(
            success=False,
            message=f"subflow_sys_id must reference type=subflow; got type={stype_s}.",
        )

    processflow_base = f"{config.api_url}/processflow"
    headers = auth_manager.get_headers()

    try:
        get_response = requests.get(
            f"{processflow_base}/flow/{params.flow_sys_id}",
            headers=headers,
            timeout=config.timeout,
        )
        get_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "add_subflow_step_to_flow | GET failed | flow_sys_id=%s | error=%s%s",
            params.flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return AddSubflowStepToFlowResponse(
            success=False,
            message=f"Failed to fetch flow {params.flow_sys_id}: {e}" + (f" | body: {_body}" if _body else ""),
        )

    flow_data = get_response.json().get("result", {}).get("data", {})
    if not flow_data:
        return AddSubflowStepToFlowResponse(
            success=False,
            message=f"GET /processflow/flow/{params.flow_sys_id} returned no data.",
        )

    new_inst = _build_subflow_instance(
        params.flow_sys_id,
        params.subflow_sys_id,
        params.name,
        params.order,
        params.inputs,
    )
    step_id = new_inst["id"]
    flow_data["subFlowInstances"] = (flow_data.get("subFlowInstances") or []) + [new_inst]

    try:
        put_response = requests.put(
            f"{processflow_base}/flow",
            params={"sysparm_transaction_scope": "global"},
            json=flow_data,
            headers=headers,
            timeout=config.timeout,
        )
        put_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "add_subflow_step_to_flow | PUT failed | flow_sys_id=%s | error=%s%s",
            params.flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return AddSubflowStepToFlowResponse(
            success=False,
            message=f"Failed to update flow: {e}" + (f" | body: {_body}" if _body else ""),
            flow_sys_id=params.flow_sys_id,
        )

    try:
        requests.post(
            f"{processflow_base}/versioning/create_version",
            params={"sysparm_transaction_scope": "global"},
            json={
                "item_sys_id": params.flow_sys_id,
                "type": "Save",
                "annotation": f"Added subflow step '{params.name}' via MCP",
                "favorite": False,
            },
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
    except requests.RequestException as e:
        logger.warning(
            "add_subflow_step_to_flow | create_version failed (non-fatal) | flow_sys_id=%s | error=%s",
            params.flow_sys_id, e,
        )

    logger.info(
        "add_subflow_step_to_flow | success | flow_sys_id=%s | subflow=%s | step_id=%s",
        params.flow_sys_id, params.subflow_sys_id, step_id,
    )
    return AddSubflowStepToFlowResponse(
        success=True,
        message=f"Added subflow step '{params.name}' to flow {params.flow_sys_id}.",
        flow_sys_id=params.flow_sys_id,
        subflow_step_id=step_id,
    )


def update_flow_trigger(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateFlowTriggerParams,
) -> UpdateFlowTriggerResponse:
    """
    Replace the trigger configuration on an existing flow.

    Fetches the processflow payload, replaces ``triggerInstances`` with a new
    instance built from ``params.trigger`` (same semantics as ``create_flow``),
    then PUT, Save version, optional record-trigger version payload patch, and
    safe-edit lock release.
    """
    parent_check = _get_artifact(config, auth_manager, "flow", params.flow_sys_id)
    if not parent_check.artifact:
        return UpdateFlowTriggerResponse(
            success=False,
            message=parent_check.message or "Flow not found.",
        )
    ptype = parent_check.artifact.get("type")
    ptype_s = str(ptype.get("value") if isinstance(ptype, dict) else ptype or "").lower()
    if ptype_s and ptype_s != "flow":
        return UpdateFlowTriggerResponse(
            success=False,
            message=f"flow_sys_id must reference type=flow; got type={ptype_s}.",
        )

    processflow_base = f"{config.api_url}/processflow"
    headers = auth_manager.get_headers()
    version_query_params = {"sysparm_transaction_scope": "global"}

    try:
        get_response = requests.get(
            f"{processflow_base}/flow/{params.flow_sys_id}",
            headers=headers,
            timeout=config.timeout,
        )
        get_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return UpdateFlowTriggerResponse(
            success=False,
            message=f"GET processflow failed: {e}" + (f" | {_body}" if _body else ""),
        )

    flow_data = get_response.json().get("result", {}).get("data", {})
    if not flow_data:
        return UpdateFlowTriggerResponse(success=False, message="GET processflow returned no data.")

    trigger_definition_id: str | None = params.trigger.trigger_definition_id
    if not trigger_definition_id:
        resolved_id, resolve_err = _resolve_trigger_definition_id(
            config, auth_manager, params.trigger.type
        )
        if resolve_err:
            return UpdateFlowTriggerResponse(success=False, message=resolve_err)
        trigger_definition_id = resolved_id

    trigger_instances = _build_trigger_instances(
        config, auth_manager, params.trigger, params.flow_sys_id, trigger_definition_id
    )
    flow_data["triggerInstances"] = trigger_instances

    try:
        requests.put(
            f"{processflow_base}/flow",
            params={"sysparm_transaction_scope": "global"},
            json=flow_data,
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("update_flow_trigger | PUT failed | error=%s%s", e, f" | body={_body}" if _body else "")
        return UpdateFlowTriggerResponse(
            success=False,
            message=f"PUT processflow failed: {e}" + (f" | {_body}" if _body else ""),
        )

    try:
        requests.post(
            f"{processflow_base}/versioning/create_version",
            params=version_query_params,
            json={
                "item_sys_id": params.flow_sys_id,
                "type": "Save",
                "annotation": "Updated trigger via MCP",
                "favorite": False,
            },
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
    except requests.RequestException as e:
        logger.warning("update_flow_trigger | create_version failed (non-fatal) | error=%s", e)

    if params.trigger.type in _RECORD_TRIGGER_TYPES:
        patch_err = _patch_flow_version_trigger_type(config, auth_manager, params.flow_sys_id)
        if patch_err:
            logger.warning("update_flow_trigger | fTriggerType patch failed (non-fatal) | %s", patch_err)

    lock_err = _release_flow_edit_lock(config, auth_manager, params.flow_sys_id)
    if lock_err:
        logger.warning("update_flow_trigger | lock release failed (non-fatal) | %s", lock_err)

    logger.info("update_flow_trigger | success | flow_sys_id=%s", params.flow_sys_id)
    return UpdateFlowTriggerResponse(
        success=True,
        message=f"Updated trigger on flow {params.flow_sys_id}.",
        flow_sys_id=params.flow_sys_id,
    )


def _deep_clone_json(obj: Any) -> Any:
    """Deep copy JSON-serialisable structures."""
    return json.loads(json.dumps(obj))


def _clone_flow_instance_arrays(source_flow_data: dict, new_flow_id: str) -> dict[str, Any]:
    """Build trigger/action/logic/subflow arrays for a cloned flow (new instance ids and flowSysId)."""
    src = _deep_clone_json(source_flow_data)

    ui_map: dict[str, str] = {}

    def collect_uis(arr: list | None) -> None:
        if not arr:
            return
        for inst in arr:
            if isinstance(inst, dict) and inst.get("uiUniqueIdentifier"):
                u = inst["uiUniqueIdentifier"]
                if isinstance(u, str) and u and u not in ui_map:
                    ui_map[u] = uuid.uuid4().hex

    for key in ("actionInstances", "flowLogicInstances", "subFlowInstances"):
        collect_uis(src.get(key))

    def remap_triggers(arr: list | None) -> list[dict]:
        out: list[dict] = []
        if not arr:
            return out
        for inst in arr:
            if not isinstance(inst, dict):
                continue
            n = _deep_clone_json(inst)
            n["id"] = uuid.uuid4().hex
            n["flowSysId"] = new_flow_id
            n.pop("sys_id", None)
            out.append(n)
        return out

    def remap_actions(arr: list | None) -> list[dict]:
        out: list[dict] = []
        if not arr:
            return out
        for inst in arr:
            if not isinstance(inst, dict):
                continue
            n = _deep_clone_json(inst)
            n["id"] = uuid.uuid4().hex
            n["flowSysId"] = new_flow_id
            n.pop("sys_id", None)
            old_u = n.get("uiUniqueIdentifier")
            if isinstance(old_u, str) and old_u:
                n["uiUniqueIdentifier"] = ui_map.get(old_u, uuid.uuid4().hex)
            out.append(n)
        return out

    def remap_logic(arr: list | None) -> list[dict]:
        out: list[dict] = []
        if not arr:
            return out
        for inst in arr:
            if not isinstance(inst, dict):
                continue
            n = _deep_clone_json(inst)
            n["id"] = uuid.uuid4().hex
            n["flowSysId"] = new_flow_id
            n.pop("sys_id", None)
            old_u = n.get("uiUniqueIdentifier")
            if isinstance(old_u, str) and old_u:
                n["uiUniqueIdentifier"] = ui_map.get(old_u, uuid.uuid4().hex)
            par = n.get("parent") or ""
            if isinstance(par, str) and par and par in ui_map:
                n["parent"] = ui_map[par]
            out.append(n)
        return out

    def remap_subflows(arr: list | None) -> list[dict]:
        out: list[dict] = []
        if not arr:
            return out
        for inst in arr:
            if not isinstance(inst, dict):
                continue
            n = _deep_clone_json(inst)
            n["id"] = uuid.uuid4().hex
            n["flowSysId"] = new_flow_id
            n.pop("sys_id", None)
            old_u = n.get("uiUniqueIdentifier")
            if isinstance(old_u, str) and old_u:
                n["uiUniqueIdentifier"] = ui_map.get(old_u, uuid.uuid4().hex)
            out.append(n)
        return out

    return {
        "triggerInstances": remap_triggers(src.get("triggerInstances")),
        "actionInstances": remap_actions(src.get("actionInstances")),
        "flowLogicInstances": remap_logic(src.get("flowLogicInstances")),
        "subFlowInstances": remap_subflows(src.get("subFlowInstances")),
    }


def _fetch_sys_hub_flow_row_for_clone(
    config: ServerConfig, auth_manager: AuthManager, source_sys_id: str
) -> tuple[dict | None, str | None]:
    """Load sys_hub_flow row for clone metadata. Returns (record, error_message)."""
    try:
        response = requests.get(
            f"{config.api_url}/table/sys_hub_flow/{source_sys_id}",
            headers=auth_manager.get_headers(),
            params={
                "sysparm_fields": "sys_id,name,description,type,scope,run_as,access,flow_priority",
            },
            timeout=config.timeout,
        )
        response.raise_for_status()
        return response.json().get("result", {}) or {}, None
    except requests.RequestException as e:
        _body = _err_body(e)
        return None, str(e) + (f" | {_body}" if _body else "")


def _defaults_from_flow_row(rec: dict) -> dict[str, Any]:
    """Map sys_hub_flow row fields to create_flow-style defaults."""
    scope = rec.get("scope")
    if isinstance(scope, dict):
        scope_s = str(scope.get("value") or "global")
    else:
        scope_s = str(scope) if scope else "global"

    run_as: Literal["user", "system"] = "user"
    ra = rec.get("run_as")
    if isinstance(ra, dict):
        rv = str(ra.get("value") or "").lower()
    else:
        rv = str(ra or "").lower()
    if rv == "system" or "system" in rv:
        run_as = "system"

    access: Literal["public", "package_private", "private"] = "public"
    ac = rec.get("access")
    if isinstance(ac, dict):
        av = str(ac.get("value") or "").lower()
    else:
        av = str(ac or "").lower()
    if "package" in av and "private" in av:
        access = "package_private"
    elif "private" in av and "package" not in av:
        access = "private"

    fp: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    pr = rec.get("flow_priority")
    if isinstance(pr, dict):
        pv = str(pr.get("value") or "").upper()
    else:
        pv = str(pr or "").upper()
    if "LOW" in pv:
        fp = "LOW"
    elif "HIGH" in pv:
        fp = "HIGH"

    desc = rec.get("description")
    if isinstance(desc, dict):
        desc_s = str(desc.get("display_value") or desc.get("value") or "")
    else:
        desc_s = str(desc) if desc else ""

    return {
        "scope": scope_s,
        "run_as": run_as,
        "access": access,
        "flow_priority": fp,
        "description": desc_s,
    }


def clone_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CloneFlowParams,
) -> CloneFlowResponse:
    """
    Duplicate an existing Flow Designer flow to a new draft flow (new sys_id).

    Uses GET /processflow/flow/{source}, POST /processflow/flow (new shell), PUT with
    cloned instance arrays (regenerated ids and uiUniqueIdentifier map), then Save
    version. Subflow step references to other flows are preserved by sys_id; complex
    graphs with undocumented cross-step references may require manual fix-up in Flow Designer.
    """
    processflow_base = f"{config.api_url}/processflow"
    headers = auth_manager.get_headers()
    version_query_params = {"sysparm_transaction_scope": "global"}

    row, row_err = _fetch_sys_hub_flow_row_for_clone(config, auth_manager, params.source_flow_sys_id)
    if row is None:
        return CloneFlowResponse(
            success=False,
            message=f"Cannot load source flow {params.source_flow_sys_id}: {row_err}",
            source_flow_sys_id=params.source_flow_sys_id,
        )
    tval = row.get("type")
    if isinstance(tval, dict):
        tstr = str(tval.get("value") or "").lower()
    else:
        tstr = str(tval or "").lower()
    if tstr and tstr != "flow":
        return CloneFlowResponse(
            success=False,
            message=f"clone_flow only supports type=flow; source has type={tstr}. Use a flow sys_id.",
            source_flow_sys_id=params.source_flow_sys_id,
        )

    meta = _defaults_from_flow_row(row)
    scope = params.scope if params.scope is not None else meta["scope"]
    run_as = params.run_as if params.run_as is not None else meta["run_as"]
    access = params.access if params.access is not None else meta["access"]
    flow_priority = params.flow_priority if params.flow_priority is not None else meta["flow_priority"]
    description = params.description if params.description is not None else meta["description"]

    # Step 1: GET source processflow payload
    try:
        get_response = requests.get(
            f"{processflow_base}/flow/{params.source_flow_sys_id}",
            headers=headers,
            timeout=config.timeout,
        )
        get_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("clone_flow | GET source failed | error=%s%s", e, f" | body={_body}" if _body else "")
        return CloneFlowResponse(
            success=False,
            message=f"Failed to fetch source flow payload: {e}" + (f" | {_body}" if _body else ""),
            source_flow_sys_id=params.source_flow_sys_id,
        )

    src_data = get_response.json().get("result", {}).get("data", {})
    if not src_data:
        return CloneFlowResponse(
            success=False,
            message=f"GET /processflow/flow/{params.source_flow_sys_id} returned no data.",
            source_flow_sys_id=params.source_flow_sys_id,
        )

    # Step 2: POST new shell
    shell_body = {
        "name": params.name,
        "type": "flow",
        "scope": scope,
        "runAs": run_as,
        "access": access,
        "flowPriority": flow_priority,
        "status": "draft",
        "active": False,
        "deleted": False,
        "security": {"can_read": True, "can_write": True},
        "scopeName": "",
        "scopeDisplayName": "",
        "userHasRolesAssignedToFlow": True,
        "runWithRoles": {"value": "", "displayValue": ""},
        "description": description or "",
        "protection": "",
    }

    try:
        shell_response = requests.post(
            f"{processflow_base}/flow",
            params={
                "param_only_properties": "true",
                "sysparm_transaction_scope": "global",
            },
            json=shell_body,
            headers=headers,
            timeout=config.timeout,
        )
        shell_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("clone_flow | shell POST failed | error=%s%s", e, f" | body={_body}" if _body else "")
        return CloneFlowResponse(
            success=False,
            message=f"Failed to create flow shell: {e}" + (f" | response: {_body}" if _body else ""),
            source_flow_sys_id=params.source_flow_sys_id,
        )

    shell_result = shell_response.json()
    flow_data = shell_result.get("result", {}).get("data", {})
    new_flow_id = flow_data.get("id")
    flow_internal_name = flow_data.get("internalName")

    if not new_flow_id:
        return CloneFlowResponse(
            success=False,
            message=f"Shell POST returned no flow id. Raw: {shell_result}",
            source_flow_sys_id=params.source_flow_sys_id,
        )

    cloned_arrays = _clone_flow_instance_arrays(src_data, new_flow_id)
    put_body = dict(flow_data)
    put_body["triggerInstances"] = cloned_arrays["triggerInstances"]
    put_body["actionInstances"] = cloned_arrays["actionInstances"]
    put_body["flowLogicInstances"] = cloned_arrays["flowLogicInstances"]
    put_body["subFlowInstances"] = cloned_arrays["subFlowInstances"]

    # Step 3: Initial autosave (non-fatal)
    try:
        requests.post(
            f"{processflow_base}/versioning/create_version",
            params=version_query_params,
            json={
                "item_sys_id": new_flow_id,
                "type": "Autosave",
                "annotation": "",
                "favorite": False,
            },
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
    except requests.RequestException as e:
        logger.warning("clone_flow | initial autosave failed (non-fatal) | flow_sys_id=%s | error=%s", new_flow_id, e)

    # Step 4: PUT cloned content
    try:
        put_response = requests.put(
            f"{processflow_base}/flow",
            params={"sysparm_transaction_scope": "global"},
            json=put_body,
            headers=headers,
            timeout=config.timeout,
        )
        put_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("clone_flow | PUT failed | new_flow_id=%s | error=%s%s", new_flow_id, e, f" | body={_body}" if _body else "")
        return CloneFlowResponse(
            success=False,
            message=(
                f"New flow shell created (sys_id={new_flow_id}) but PUT to copy steps failed: {e}"
                + (f" | {_body}" if _body else "")
            ),
            flow_sys_id=new_flow_id,
            flow_name=params.name,
            flow_internal_name=flow_internal_name,
            source_flow_sys_id=params.source_flow_sys_id,
        )

    # Step 5: Save version
    try:
        requests.post(
            f"{processflow_base}/versioning/create_version",
            params=version_query_params,
            json={
                "item_sys_id": new_flow_id,
                "type": "Save",
                "annotation": "",
                "favorite": False,
            },
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
    except requests.RequestException as e:
        logger.warning("clone_flow | Save version failed (non-fatal) | flow_sys_id=%s | error=%s", new_flow_id, e)

    # Step 6: Patch record trigger payload if applicable
    needs_patch = any(
        isinstance(t, dict) and str(t.get("type") or "") in _RECORD_TRIGGER_TYPES
        for t in (cloned_arrays.get("triggerInstances") or [])
    )
    if needs_patch:
        patch_err = _patch_flow_version_trigger_type(config, auth_manager, new_flow_id)
        if patch_err:
            logger.warning("clone_flow | fTriggerType patch failed (non-fatal) | flow_sys_id=%s | %s", new_flow_id, patch_err)

    lock_err = _release_flow_edit_lock(config, auth_manager, new_flow_id)
    if lock_err:
        logger.warning("clone_flow | safeEdit lock release failed (non-fatal) | flow_sys_id=%s | %s", new_flow_id, lock_err)

    logger.info(
        "clone_flow | success | source=%s | new=%s",
        params.source_flow_sys_id,
        new_flow_id,
    )
    return CloneFlowResponse(
        success=True,
        message=f"Cloned flow to '{params.name}' (draft). New sys_id={new_flow_id}.",
        flow_sys_id=new_flow_id,
        flow_name=params.name,
        flow_internal_name=flow_internal_name,
        source_flow_sys_id=params.source_flow_sys_id,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_trigger_instances(
    config: ServerConfig,
    auth_manager: AuthManager,
    trigger: TriggerInstanceParam | None,
    flow_sys_id: str,
    trigger_definition_id: str | None,
) -> list[dict]:
    """Convert a TriggerInstanceParam into the triggerInstances array for the PUT body.

    For record-based triggers all 8 standard inputs are always included (with default
    values for the 6 advanced inputs). Each input carries a full 'parameter' sub-object
    required by the Flow Designer renderInput component — omitting it causes a
    TypeError crash in the UI.

    A shallow copy of each param_def dict is used to avoid aliasing the module-level
    _RECORD_TRIGGER_INPUTS entries.

    The table input additionally carries displayValue (e.g. 'Incident') and
    displayField so Flow Designer renders the correct label and data pill reference.
    Note: displayField defaults to 'number' which is correct for task-derived tables
    (incident, problem, change, etc.). For non-task tables (sys_user, cmdb_ci, custom)
    this field does not exist and Flow Designer may show an empty data pill reference.

    Args:
        trigger_definition_id: Resolved sys_id for the trigger type. Passed explicitly
            to avoid mutating the caller's TriggerInstanceParam model in place.
    """
    if trigger is None:
        return []

    # Resolve name→value from explicit inputs or convenience fields.
    # TriggerInstanceParam.normalize_empty_inputs ensures inputs=[] is treated as None.
    if trigger.inputs is not None:
        input_values = {i.name: i.value for i in trigger.inputs}
    else:
        input_values = {}
        if trigger.table:
            input_values["table"] = trigger.table
        if trigger.condition:
            input_values["condition"] = trigger.condition

    if trigger.type in _RECORD_TRIGGER_TYPES:
        # Look up the table display label so Flow Designer can render the correct
        # label and data pill (e.g. "Incident" instead of "incident" / "undefined record").
        table_value = input_values.get("table", "")
        table_label = _lookup_table_label(config, auth_manager, table_value) if table_value else ""

        # Always emit all 7 standard inputs in the required order.
        # User-supplied values override the empty default; system inputs default to "".
        # Shallow-copy each param_def to prevent aliasing the module-level list entries.
        built_inputs = []
        for param_def in _RECORD_TRIGGER_INPUTS:
            name = param_def["name"]
            input_obj = {
                "label": param_def["label"],
                "internalType": param_def["type"],
                "mandatory": param_def["mandatory"],
                "fromTemplate": False,
                "order": param_def["order"],
                "valueSysId": "",
                "name": name,
                "value": input_values.get(name, param_def.get("defaultValue", "")),
                "children": [],
                "parameter": dict(param_def),  # shallow copy to avoid aliasing module-level dict
                "scriptActive": False,
            }
            # The table input needs displayValue and displayField for Flow Designer
            # to resolve the correct table label and data pill reference.
            if name == "table" and table_label:
                input_obj["displayValue"] = table_label
                input_obj["displayField"] = "number"  # correct for task-derived tables
            # condition and run_when_setting carry displayField="" in the reference payload.
            elif name in ("condition", "run_when_setting"):
                input_obj["displayField"] = ""
            # All other non-table inputs carry displayValue="" in the reference payload.
            # Required for Flow Designer to render the Advanced Options section correctly.
            else:
                input_obj["displayValue"] = ""
            built_inputs.append(input_obj)
        # Append any caller-supplied inputs not in the standard set
        for name, value in input_values.items():
            if name not in _RECORD_TRIGGER_INPUT_BY_NAME:
                built_inputs.append(_minimal_trigger_input(name, value))
    else:
        # Non-record trigger: emit only what the caller specified, with minimal parameter stub
        built_inputs = [
            _minimal_trigger_input(name, value, _RECORD_TRIGGER_INPUT_BY_NAME.get(name))
            for name, value in input_values.items()
        ]

    return [
        {
            "id": uuid.uuid4().hex,
            "flowSysId": flow_sys_id,
            "remoteSysId": trigger_definition_id or "",
            "name": trigger.name or _TRIGGER_TYPE_NAME_MAP.get(trigger.type, trigger.type),
            "type": trigger.type,
            "triggerDefinitionId": trigger_definition_id,
            "fTriggerType": "Record" if trigger.type in _RECORD_TRIGGER_TYPES else "",
            "deleted": False,
            "comment": "",
            "inputs": built_inputs,
        }
    ]


def _minimal_trigger_input(name: str, value: str, param_def: dict | None = None) -> dict:
    """Build a trigger input object with a minimal parameter stub for unknown input types."""
    p = param_def or _param("", name, name, "string", order=200, maxsize=4000)
    return {
        "label": p["label"],
        "internalType": p["type"],
        "mandatory": p["mandatory"],
        "fromTemplate": False,
        "order": p["order"],
        "valueSysId": "",
        "name": name,
        "value": value,
        "children": [],
        "parameter": dict(p),  # shallow copy to avoid aliasing module-level dict
        "scriptActive": False,
    }


def _patch_flow_version_trigger_type(
    config: ServerConfig,
    auth_manager: AuthManager,
    flow_sys_id: str,
) -> str | None:
    """Patch the latest flow version payload to fix fTriggerType and trigger input choices.

    Two issues are corrected here:
    1. fTriggerType='Record' — the processflow PUT cannot reliably set this field because
       a Business Rule overwrites it using a sys_hub_trigger_type (V1 catalog) lookup the
       service account cannot read.
    2. choices/defaultChoices — the processflow create_version call with a minimal request
       body does not persist choice arrays into the version payload. The Flow Designer UI
       sends full trigger state when it saves; our minimal call does not. This causes the
       advanced options dropdowns to render with no options in the UI.

    Both are patched by reading the latest sys_hub_flow_version.payload, mutating the
    trigger instance data in-place, and writing the corrected payload back via Table API.

    Returns None on success, or an error message string on failure.
    """
    _MAX_ATTEMPTS = 3
    records: list = []
    for _attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            ver_response = requests.get(
                f"{config.api_url}/table/sys_hub_flow_version",
                params={
                    "sysparm_query": f"flow={flow_sys_id}^ORDERBYDESCsys_created_on",
                    "sysparm_fields": "sys_id,payload",
                    "sysparm_limit": 1,
                },
                headers=auth_manager.get_headers(),
                timeout=config.timeout,
            )
            ver_response.raise_for_status()
            records = ver_response.json().get("result", [])
            if records:
                break
            logger.info(
                "_patch_flow_version_trigger_type | no version yet, retrying (%d/%d) | flow_sys_id=%s",
                _attempt, _MAX_ATTEMPTS, flow_sys_id,
            )
            if _attempt < _MAX_ATTEMPTS:
                time.sleep(1)
        except requests.RequestException as e:
            _body = _err_body(e)
            return f"GET sys_hub_flow_version failed: {e}" + (f" | body: {_body}" if _body else "")

    if not records:
        return f"No sys_hub_flow_version found for flow_sys_id={flow_sys_id} after {_MAX_ATTEMPTS} attempts"

    version_sys_id = records[0]["sys_id"]
    payload_str = records[0].get("payload")
    if payload_str is None or payload_str == "":
        return f"sys_hub_flow_version {version_sys_id} has an empty payload — nothing to patch"

    try:
        payload = json.loads(payload_str)
    except (ValueError, TypeError) as exc:
        return f"Failed to parse payload JSON for version {version_sys_id}: {exc}"

    trigger_instances = payload.get("triggerInstances", [])
    if not trigger_instances:
        logger.info(
            "_patch_flow_version_trigger_type | no triggerInstances in payload — skipping | version_sys_id=%s",
            version_sys_id,
        )
        return None

    patched_any = False
    for ti in trigger_instances:
        # ti is a dict reference into payload — mutating it updates payload in place,
        # which is then serialised below. This is intentional, not an aliasing bug.
        if ti.get("fTriggerType") != "Record":
            ti["fTriggerType"] = "Record"
            patched_any = True

        # Inject choices/defaultChoices/choiceOption/defaultDisplayValue into choice-type
        # trigger inputs that are missing them. The processflow PUT does not reliably write
        # these into the version payload — only the UI does. Without this patch Flow Designer
        # renders the advanced options dropdowns with no selectable options and no defaults.
        for inp in ti.get("inputs", []):
            param = inp.get("parameter")
            if not isinstance(param, dict) or param.get("type") != "choice":
                continue
            input_name = inp.get("name") or param.get("name", "")
            known_def = _RECORD_TRIGGER_INPUT_BY_NAME.get(input_name)
            if not known_def:
                continue
            if not param.get("choices"):
                param["choices"] = known_def["choices"]
                patched_any = True
            if not param.get("defaultChoices"):
                param["defaultChoices"] = known_def["defaultChoices"]
                patched_any = True
            if not param.get("choiceOption") and known_def.get("choiceOption"):
                param["choiceOption"] = known_def["choiceOption"]
                patched_any = True
            if "defaultDisplayValue" not in param and "defaultDisplayValue" in known_def:
                param["defaultDisplayValue"] = known_def["defaultDisplayValue"]
                patched_any = True

    if not patched_any:
        logger.info(
            "_patch_flow_version_trigger_type | payload already up-to-date — skipping | version_sys_id=%s",
            version_sys_id,
        )
        return None

    try:
        patch_response = requests.patch(
            f"{config.api_url}/table/sys_hub_flow_version/{version_sys_id}",
            json={"payload": json.dumps(payload)},
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        patch_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return (
            f"PATCH sys_hub_flow_version/{version_sys_id} failed: {e}"
            + (f" | body: {_body}" if _body else "")
        )

    logger.info(
        "_patch_flow_version_trigger_type | patched version payload (fTriggerType + choices) | version_sys_id=%s",
        version_sys_id,
    )
    return None


def _release_flow_edit_lock(
    config: ServerConfig,
    auth_manager: AuthManager,
    flow_sys_id: str,
) -> str | None:
    """Release the Flow Designer edit lock by deleting the sys_hub_flow_safe_edit record.

    Flow Designer writes a lock record to sys_hub_flow_safe_edit when a flow is opened
    for editing (including programmatic creation via processflow). Without deletion the
    flow appears locked ('being edited by <user>') in the UI and cannot be modified.

    GraphQL safeEdit does not work for service accounts (returns data:null). Table API
    DELETE is the reliable alternative, confirmed on dev296536.

    Returns None on success, or an error message string on failure.
    """
    # Step 1: Find the lock record for this flow
    try:
        get_response = requests.get(
            f"{config.api_url}/table/sys_hub_flow_safe_edit",
            params={
                "sysparm_query": f"flow={flow_sys_id}",
                "sysparm_fields": "sys_id",
                "sysparm_limit": 1,
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        get_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return f"GET sys_hub_flow_safe_edit failed: {e}" + (f" | body: {_body}" if _body else "")

    records = get_response.json().get("result", [])
    if not records:
        # No lock record — nothing to delete (may already be absent)
        logger.info("_release_flow_edit_lock | no lock record found | flow_sys_id=%s", flow_sys_id)
        return None

    lock_sys_id = records[0]["sys_id"]

    # Step 2: DELETE the lock record
    try:
        del_response = requests.delete(
            f"{config.api_url}/table/sys_hub_flow_safe_edit/{lock_sys_id}",
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        del_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        return (
            f"DELETE sys_hub_flow_safe_edit/{lock_sys_id} failed: {e}"
            + (f" | body: {_body}" if _body else "")
        )

    logger.info(
        "_release_flow_edit_lock | lock deleted | flow_sys_id=%s | lock_sys_id=%s",
        flow_sys_id, lock_sys_id,
    )
    return None


# ---------------------------------------------------------------------------
# Phase 5 — Flow read + publish tools
# ---------------------------------------------------------------------------


class ListFlowsParams(BaseModel):
    """Parameters for listing Flow Designer flows."""

    limit: int = Field(10, description="Maximum number of records to return")
    offset: int = Field(0, description="Pagination offset")
    flow_type: str | None = Field(
        None,
        description="Filter by flow type: 'flow' or 'subflow'",
    )
    status: str | None = Field(
        None,
        description="Filter by status: 'draft', 'published', 'published_and_draft'",
    )
    scope: str | None = Field(
        None,
        description="Filter by application scope (e.g. 'global' or a scope sys_id)",
    )
    name_filter: str | None = Field(None, description="Filter by name (LIKE match)")


class GetFlowParams(BaseModel):
    """Parameters for getting a single flow's detail view."""

    flow_sys_id: str = Field(..., description="sys_id of the flow (sys_hub_flow)")


class GetFlowTriggersParams(BaseModel):
    """Parameters for getting trigger instances attached to a flow.

    Queries both sys_hub_trigger_instance (V1) and sys_hub_trigger_instance_v2 (V2)
    and merges the results.
    """

    flow_sys_id: str = Field(..., description="sys_id of the flow (sys_hub_flow / sys_hub_flow_base)")
    limit: int = Field(10, description="Maximum number of trigger records to return per table (total may be up to 2× limit when both V1 and V2 return results)")
    offset: int = Field(0, description="Pagination offset")


class GetFlowActionsParams(BaseModel):
    """Parameters for getting flow components (actions, logic steps, etc.).

    List mode (no component_sys_id): queries sys_hub_flow_component for all in-flow elements,
    ordered by execution order. Returns lean fields including sys_class_name for routing.

    Detail mode (component_sys_id provided): fetches full fields for a single component
    from the appropriate child table determined by sys_class_name.
    """

    flow_sys_id: str = Field(..., description="sys_id of the flow (sys_hub_flow / sys_hub_flow_base)")
    component_sys_id: str | None = Field(
        None,
        description=(
            "When provided, returns full detail for a single component. "
            "The tool reads sys_class_name from sys_hub_flow_component, then queries the matching "
            "child table: sys_hub_action_instance, sys_hub_action_instance_v2, "
            "sys_hub_flow_logic, or sys_hub_flow_logic_instance_v2."
        ),
    )
    limit: int = Field(50, description="Maximum number of components to return in list mode")
    offset: int = Field(0, description="Pagination offset for list mode")


class GetFlowVersionParams(BaseModel):
    """Parameters for getting a flow version record.

    Returns the latest version by default. Set published_only=True to return only
    the published version (which may differ from the latest draft).
    """

    flow_sys_id: str = Field(..., description="sys_id of the flow (sys_hub_flow)")
    published_only: bool = Field(
        False,
        description="When True, return only the published version rather than the latest",
    )


class PublishFlowParams(BaseModel):
    """Parameters for publishing (activating) a Flow Designer flow.

    Sets active=true on sys_hub_flow. The platform then marks the current
    draft version as published. The sys_hub_flow_version.published field is
    read-only via the Table API and cannot be set directly.
    """

    flow_sys_id: str = Field(..., description="sys_id of the flow to publish (sys_hub_flow)")


def list_flows(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListFlowsParams,
) -> dict:
    """List Flow Designer flows from sys_hub_flow with optional filters."""
    try:
        url = f"{config.instance_url}/api/now/table/sys_hub_flow"
        headers = auth_manager.get_headers()

        query_parts: list[str] = []
        if params.flow_type is not None:
            query_parts.append(f"flow_type={params.flow_type}")
        if params.status is not None:
            query_parts.append(f"status={params.status}")
        if params.scope is not None:
            query_parts.append(f"sys_scope={params.scope}")
        if params.name_filter is not None:
            query_parts.append(f"nameLIKE{params.name_filter}")

        query_params: dict = {
            "sysparm_limit": params.limit,
            "sysparm_offset": params.offset,
            "sysparm_fields": "sys_id,name,internal_name,flow_type,status,active,sys_scope,sys_created_on,sys_updated_on",
            "sysparm_display_value": "true",
        }
        if query_parts:
            query_params["sysparm_query"] = "^".join(query_parts)

        response = requests.get(url, headers=headers, params=query_params, timeout=config.timeout)
        response.raise_for_status()
        flows = response.json().get("result", [])
        return {"success": True, "flows": flows, "count": len(flows)}
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("list_flows | error=%s%s", e, f" | body={_body}" if _body else "")
        return {"success": False, "message": f"Error listing flows: {e}" + (f" | {_body}" if _body else "")}


def get_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetFlowParams,
) -> dict:
    """Get detail view of a single flow from sys_hub_flow."""
    try:
        url = f"{config.instance_url}/api/now/table/sys_hub_flow/{params.flow_sys_id}"
        headers = auth_manager.get_headers()
        response = requests.get(
            url,
            headers=headers,
            params={
                "sysparm_display_value": "true",
                "sysparm_fields": (
                    "sys_id,name,internal_name,flow_type,status,active,sys_scope,"
                    "run_as,access,natlang,flow_priority,version,"
                    "sys_created_on,sys_updated_on,master_snapshot,latest_snapshot"
                ),
            },
            timeout=config.timeout,
        )
        response.raise_for_status()
        record = response.json().get("result", {})
        return {"success": True, "flow": record}
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("get_flow | flow_sys_id=%s | error=%s%s", params.flow_sys_id, e, f" | body={_body}" if _body else "")
        return {"success": False, "message": f"Error getting flow: {e}" + (f" | {_body}" if _body else "")}


def get_flow_triggers(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetFlowTriggersParams,
) -> dict:
    """Get trigger instances for a flow from sys_hub_trigger_instance (V1) and sys_hub_trigger_instance_v2 (V2).

    Both tables reference sys_hub_flow_base so the flow sys_id is used directly.
    Results from both generations are merged and returned together.
    The limit and offset parameters apply independently to each table query; the merged
    result count can be up to twice the limit value.
    """
    headers = auth_manager.get_headers()
    trigger_fields = "sys_id,name,flow,trigger_type,trigger_definition,trigger_inputs,display_text"

    all_triggers: list[dict] = []
    for table in ("sys_hub_trigger_instance", "sys_hub_trigger_instance_v2"):
        url = f"{config.instance_url}/api/now/table/{table}"
        try:
            response = requests.get(
                url,
                headers=headers,
                params={
                    "sysparm_query": f"flow={params.flow_sys_id}",
                    "sysparm_display_value": "true",
                    "sysparm_fields": trigger_fields,
                    "sysparm_limit": params.limit,
                    "sysparm_offset": params.offset,
                },
                timeout=config.timeout,
            )
            response.raise_for_status()
            all_triggers.extend(response.json().get("result", []))
        except requests.RequestException as e:
            _body = _err_body(e)
            logger.error(
                "get_flow_triggers | table=%s | flow_sys_id=%s | error=%s%s",
                table, params.flow_sys_id, e, f" | body={_body}" if _body else "",
            )
            return {
                "success": False,
                "message": f"Error getting flow triggers: {e}" + (f" | {_body}" if _body else ""),
            }

    return {
        "success": True,
        "flow_sys_id": params.flow_sys_id,
        "triggers": all_triggers,
        "count": len(all_triggers),
    }


# Routing table for get_flow_actions detail mode.
# Maps sys_class_name → sysparm_fields to request from the child table.
_COMPONENT_DETAIL_TABLES: dict[str, str] = {
    "sys_hub_action_instance": (
        "sys_id,flow,order,display_text,action_type,action_type_parent,action_inputs"
    ),
    "sys_hub_action_instance_v2": (
        "sys_id,flow,order,display_text,action_type,action_type_parent,values"
    ),
    "sys_hub_flow_logic": (
        "sys_id,flow,order,display_text,logic_definition,decision_table,inputs"
    ),
    "sys_hub_flow_logic_instance_v2": (
        "sys_id,flow,order,display_text,logic_definition,decision_table,values"
    ),
}


def get_flow_actions(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetFlowActionsParams,
) -> dict:
    """Get flow components in list or detail mode.

    List mode (no component_sys_id): queries sys_hub_flow_component ordered by execution
    order. Returns all step types — actions (V1/V2), logic (V1/V2), etc. — with lean
    fields including sys_class_name for identification.

    Detail mode (component_sys_id provided): fetches the component's sys_class_name, then
    queries the appropriate child table for full field detail. Supported types are defined
    in _COMPONENT_DETAIL_TABLES; unsupported types return success=False.
    """
    headers = auth_manager.get_headers()

    # --- Detail mode ---
    if params.component_sys_id:
        # Step 1: fetch base component to get sys_class_name
        comp_url = f"{config.instance_url}/api/now/table/sys_hub_flow_component/{params.component_sys_id}"
        try:
            comp_resp = requests.get(
                comp_url,
                headers=headers,
                params={"sysparm_fields": "sys_id,sys_class_name,flow,order,display_text"},
                timeout=config.timeout,
            )
            comp_resp.raise_for_status()
            component = comp_resp.json().get("result", {})
        except requests.RequestException as e:
            _body = _err_body(e)
            logger.error(
                "get_flow_actions | component fetch | sys_id=%s | error=%s%s",
                params.component_sys_id, e, f" | body={_body}" if _body else "",
            )
            return {
                "success": False,
                "message": f"Error fetching component: {e}" + (f" | {_body}" if _body else ""),
            }

        sys_class_name = component.get("sys_class_name", "")
        if sys_class_name not in _COMPONENT_DETAIL_TABLES:
            return {
                "success": False,
                "message": f"Unsupported component type: {sys_class_name}",
            }

        # Step 2: fetch from the child table using routed fields
        detail_url = f"{config.instance_url}/api/now/table/{sys_class_name}/{params.component_sys_id}"
        try:
            detail_resp = requests.get(
                detail_url,
                headers=headers,
                params={
                    "sysparm_display_value": "true",
                    "sysparm_fields": _COMPONENT_DETAIL_TABLES[sys_class_name],
                },
                timeout=config.timeout,
            )
            detail_resp.raise_for_status()
            detail = detail_resp.json().get("result", {})
        except requests.RequestException as e:
            _body = _err_body(e)
            logger.error(
                "get_flow_actions | detail fetch | sys_id=%s | table=%s | error=%s%s",
                params.component_sys_id, sys_class_name, e, f" | body={_body}" if _body else "",
            )
            return {
                "success": False,
                "message": f"Error fetching component detail: {e}" + (f" | {_body}" if _body else ""),
            }

        return {
            "success": True,
            "component_sys_id": params.component_sys_id,
            "sys_class_name": sys_class_name,
            "detail": detail,
        }

    # --- List mode ---
    url = f"{config.instance_url}/api/now/table/sys_hub_flow_component"
    try:
        response = requests.get(
            url,
            headers=headers,
            params={
                "sysparm_query": f"flow={params.flow_sys_id}^ORDERBYorder",
                "sysparm_fields": "sys_id,flow,order,display_text,sys_class_name,ui_id",
                "sysparm_display_value": "true",
                "sysparm_limit": params.limit,
                "sysparm_offset": params.offset,
            },
            timeout=config.timeout,
        )
        response.raise_for_status()
        components = response.json().get("result", [])
        return {
            "success": True,
            "flow_sys_id": params.flow_sys_id,
            "components": components,
            "count": len(components),
        }
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "get_flow_actions | flow_sys_id=%s | error=%s%s",
            params.flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return {
            "success": False,
            "message": f"Error getting flow components: {e}" + (f" | {_body}" if _body else ""),
        }


def get_flow_version(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetFlowVersionParams,
) -> dict:
    """Get the latest (or published) version record for a flow from sys_hub_flow_version.

    Note: sys_hub_flow_version.published is read-only via the Table API.
    Use publish_flow to activate a flow rather than attempting to write this field.
    """
    try:
        url = f"{config.instance_url}/api/now/table/sys_hub_flow_version"
        headers = auth_manager.get_headers()

        query = f"flow={params.flow_sys_id}"
        if params.published_only:
            query += "^published=true"

        response = requests.get(
            url,
            headers=headers,
            params={
                "sysparm_query": query + "^ORDERBYDESCsys_created_on",
                "sysparm_limit": 1,
                "sysparm_display_value": "true",
                "sysparm_fields": "sys_id,flow,annotation,type,favorite,sys_created_on,sys_updated_on,sys_created_by",
            },
            timeout=config.timeout,
        )
        response.raise_for_status()
        records = response.json().get("result", [])
        if not records:
            # Packaged / OOB flows may have no sys_hub_flow_version rows; try read-only snapshot.
            try:
                snap_url = f"{config.instance_url}/api/now/table/sys_hub_flow_snapshot"
                snap_resp = requests.get(
                    snap_url,
                    headers=headers,
                    params={
                        "sysparm_query": f"flow={params.flow_sys_id}^ORDERBYDESCsys_created_on",
                        "sysparm_limit": 1,
                        "sysparm_display_value": "true",
                    },
                    timeout=config.timeout,
                )
                snap_resp.raise_for_status()
                snap_rows = snap_resp.json().get("result", [])
                if snap_rows:
                    return {
                        "success": True,
                        "flow_sys_id": params.flow_sys_id,
                        "version": snap_rows[0],
                        "snapshot_fallback": True,
                    }
            except requests.RequestException as snap_e:
                logger.warning(
                    "get_flow_version | no sys_hub_flow_version row; snapshot fallback failed | flow=%s | %s",
                    params.flow_sys_id,
                    snap_e,
                )
            label = "published" if params.published_only else "latest"
            return {
                "success": False,
                "message": f"No {label} version found for flow {params.flow_sys_id}",
            }
        return {"success": True, "flow_sys_id": params.flow_sys_id, "version": records[0]}
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("get_flow_version | flow_sys_id=%s | error=%s%s", params.flow_sys_id, e, f" | body={_body}" if _body else "")
        return {"success": False, "message": f"Error getting flow version: {e}" + (f" | {_body}" if _body else "")}


def publish_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: PublishFlowParams,
) -> dict:
    """Publish (activate) a Flow Designer flow by setting active=true on sys_hub_flow.

    The sys_hub_flow_version.published field is read-only via the Table API and cannot
    be set directly. Setting active=true on the flow record triggers the platform to
    mark the current version as published.

    Note: For flows that require the FlowDesignerAPI.publishFlow() server-side method
    (e.g. complex flows with ACL constraints), use run_background_script instead with
    the script: FlowDesignerAPI.publishFlow('<flow_sys_id>');
    """
    try:
        url = f"{config.instance_url}/api/now/table/sys_hub_flow/{params.flow_sys_id}"
        headers = auth_manager.get_headers()
        headers["Content-Type"] = "application/json"
        response = requests.patch(
            url,
            json={"active": "true", "status": "published"},
            headers=headers,
            timeout=config.timeout,
        )
        response.raise_for_status()
        record = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Flow {params.flow_sys_id} published (active=true, status=published)",
            "flow": record,
        }
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error("publish_flow | flow_sys_id=%s | error=%s%s", params.flow_sys_id, e, f" | body={_body}" if _body else "")
        return {
            "success": False,
            "message": (
                f"Error publishing flow: {e}"
                + (f" | {_body}" if _body else "")
                + " — If this fails due to ACL constraints, use run_background_script with: "
                f"FlowDesignerAPI.publishFlow('{params.flow_sys_id}');"
            ),
        }


def _build_action_instances(flow_sys_id: str, actions: list[ActionInstanceParam] | None) -> list[dict]:
    """Convert ActionInstanceParam list into the actionInstances array for the PUT body.

    Note on order serialisation: 'order' is cast to str to match the processflow API's
    expected type for this field. uiComponentIndex stays as int — the asymmetry is
    intentional and mirrors the instance-captured payload schema.

    Note on UUID format: both 'id' and 'uiUniqueIdentifier' use uuid4().hex (32 hex
    chars, no dashes) to match the format observed in manually-created flow payloads.
    """
    if not actions:
        return []

    result = []
    for action in actions:
        result.append(
            {
                "id": uuid.uuid4().hex,
                "flowSysId": flow_sys_id,
                "order": str(action.order),          # API expects string; see docstring
                "uiUniqueIdentifier": uuid.uuid4().hex,
                "deleted": False,
                "parent": "",
                "comment": "",
                "generationSource": "",
                "uiComponentIndex": 0,               # API expects int; see docstring
                "actionTypeSysId": action.action_type_sys_id,
                "inputs": [
                    {"id": i.id, "name": i.name, "value": i.value}
                    for i in action.inputs
                ],
                "parentActionTypeId": action.parent_action_type_id or "",
                "compiledSnapshot": "",
                "aliasIds": [],
                "internalName": action.internal_name or "",
                "name": action.name,
                "type": "action",
                "snapshot": False,
            }
        )
    return result


def _build_subflow_instance(
    parent_flow_sys_id: str,
    subflow_sys_id: str,
    name: str,
    order: int,
    inputs: list[ActionInputParam] | None,
) -> dict:
    """Build one subFlowInstances entry for processflow PUT (mirrors action instance shape)."""
    inp_list = [
        {"id": i.id, "name": i.name, "value": i.value}
        for i in (inputs or [])
    ]
    return {
        "id": uuid.uuid4().hex,
        "flowSysId": parent_flow_sys_id,
        "order": str(order),
        "uiUniqueIdentifier": uuid.uuid4().hex,
        "deleted": False,
        "parent": "",
        "comment": "",
        "generationSource": "",
        "uiComponentIndex": 0,
        "subFlowSysId": subflow_sys_id,
        "inputs": inp_list,
        "parentActionTypeId": "",
        "compiledSnapshot": "",
        "aliasIds": [],
        "internalName": "",
        "name": name,
        "type": "subflow",
        "snapshot": False,
    }


_ARTIFACT_TABLE_MAP: dict[str, str] = {
    "flow": "sys_hub_flow",
    "subflow": "sys_hub_flow",
    "action": "sys_hub_action_type_definition",
}


def _delete_artifact(
    config: ServerConfig,
    auth_manager: AuthManager,
    artifact_type: str,
    sys_id: str,
) -> DeleteArtifactResponse:
    """Delete a flow artifact via the Table API DELETE endpoint."""
    table = _ARTIFACT_TABLE_MAP[artifact_type]
    try:
        response = requests.delete(
            f"{config.api_url}/table/{table}/{sys_id}",
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "_delete_artifact | failed | artifact_type=%s | sys_id=%s | error=%s%s",
            artifact_type, sys_id, e, f" | body={_body}" if _body else "",
        )
        return DeleteArtifactResponse(
            success=False,
            message=f"Failed to delete {artifact_type} {sys_id}: {e}" + (f" | body: {_body}" if _body else ""),
            sys_id=sys_id,
        )
    logger.info("_delete_artifact | deleted | artifact_type=%s | sys_id=%s", artifact_type, sys_id)
    return DeleteArtifactResponse(success=True, message=f"Deleted {artifact_type} {sys_id}.", sys_id=sys_id)


def delete_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: DeleteFlowParams,
) -> DeleteArtifactResponse:
    """Delete a flow by sys_id. Irreversible — ensure no dependent subflows or actions reference this flow."""
    return _delete_artifact(config, auth_manager, "flow", params.sys_id)


def delete_subflow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: DeleteSubflowParams,
) -> DeleteArtifactResponse:
    """Delete a subflow by sys_id."""
    return _delete_artifact(config, auth_manager, "subflow", params.sys_id)


def delete_action(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: DeleteActionParams,
) -> DeleteArtifactResponse:
    """Delete a custom action type by sys_id."""
    return _delete_artifact(config, auth_manager, "action", params.sys_id)


def get_flow_execution_history(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetFlowExecutionHistoryParams,
) -> GetFlowExecutionHistoryResult:
    """
    Return recent executions of a flow from sys_hub_flow_context.

    Each execution record includes state, start/end times, and any error
    message. Useful for debugging flows that are failing or running unexpectedly.
    """
    query = f"flow={params.flow_sys_id}^ORDERBYDESCsys_created_on"
    if params.state:
        query += f"^state={params.state}"

    try:
        response = requests.get(
            f"{config.api_url}/table/sys_hub_flow_context",
            params={
                "sysparm_query": query,
                "sysparm_fields": "sys_id,name,state,started,ended,error",
                "sysparm_limit": params.limit,
                "sysparm_display_value": "true",
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "get_flow_execution_history | request failed | flow_sys_id=%s | error=%s%s",
            params.flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return GetFlowExecutionHistoryResult(
            executions=[],
            count=0,
            message=f"Failed to fetch execution history for flow {params.flow_sys_id}: {e}" + (f" | body: {_body}" if _body else ""),
        )

    records = response.json().get("result", [])
    executions = [
        FlowExecution(
            sys_id=r["sys_id"],
            name=r.get("name") or None,
            state=r.get("state") or None,
            started=r.get("started") or None,
            ended=r.get("ended") or None,
            error=r.get("error") or None,
        )
        for r in records
    ]
    logger.info(
        "get_flow_execution_history | flow_sys_id=%s | found %d execution(s)",
        params.flow_sys_id, len(executions),
    )
    return GetFlowExecutionHistoryResult(
        executions=executions,
        count=len(executions),
        message=f"Found {len(executions)} execution(s) for flow {params.flow_sys_id}.",
    )


def remove_steps_from_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: RemoveStepsFromFlowParams,
) -> RemoveStepsFromFlowResponse:
    """
    Remove one or more action or logic steps from an existing flow.

    Uses the GET→mark deleted→PUT→create_version pattern. Steps are marked
    with deleted=True in actionInstances, flowLogicInstances, or subFlowInstances.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: flow_sys_id and list of step id values to remove.

    Returns:
        RemoveStepsFromFlowResponse with success flag, message, and count of
        steps removed.
    """
    if not params.step_ids:
        return RemoveStepsFromFlowResponse(
            success=False,
            message="step_ids must be a non-empty list.",
        )

    processflow_base = f"{config.api_url}/processflow"
    headers = auth_manager.get_headers()

    # Step 1: GET current flow payload
    try:
        get_response = requests.get(
            f"{processflow_base}/flow/{params.flow_sys_id}",
            headers=headers,
            timeout=config.timeout,
        )
        get_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "remove_steps_from_flow | GET failed | flow_sys_id=%s | error=%s%s",
            params.flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return RemoveStepsFromFlowResponse(
            success=False,
            message=f"Failed to fetch flow: {e}" + (f" | response: {_body}" if _body else ""),
        )

    flow_data = get_response.json().get("result", {}).get("data", {})

    if not flow_data:
        return RemoveStepsFromFlowResponse(
            success=False,
            message=f"GET /processflow/flow/{params.flow_sys_id} returned no data.",
            flow_sys_id=params.flow_sys_id,
        )

    # Step 2: Mark specified steps as deleted across instance arrays
    ids_to_remove = set(params.step_ids)
    found_ids: set[str] = set()

    action_instances = flow_data.get("actionInstances", [])
    for step in action_instances:
        if step.get("id") in ids_to_remove:
            step["deleted"] = True
            found_ids.add(step["id"])

    logic_instances = flow_data.get("flowLogicInstances", [])
    for step in logic_instances:
        if step.get("id") in ids_to_remove:
            step["deleted"] = True
            found_ids.add(step["id"])

    subflow_instances = flow_data.get("subFlowInstances", [])
    for step in subflow_instances:
        if step.get("id") in ids_to_remove:
            step["deleted"] = True
            found_ids.add(step["id"])

    not_found = ids_to_remove - found_ids
    if not_found:
        return RemoveStepsFromFlowResponse(
            success=False,
            message=(
                f"Step id(s) not found in flow: {sorted(not_found)}. "
                "Use get_flow_actions, processflow GET, or get_flow_version to list current step ids."
            ),
        )

    # Step 3: PUT modified payload back
    flow_data["actionInstances"] = action_instances
    flow_data["flowLogicInstances"] = logic_instances
    flow_data["subFlowInstances"] = subflow_instances

    try:
        put_response = requests.put(
            f"{processflow_base}/flow",
            params={"sysparm_transaction_scope": "global"},
            json=flow_data,
            headers=headers,
            timeout=config.timeout,
        )
        put_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "remove_steps_from_flow | PUT failed | flow_sys_id=%s | error=%s%s",
            params.flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return RemoveStepsFromFlowResponse(
            success=False,
            flow_sys_id=params.flow_sys_id,
            message=f"Failed to update flow: {e}" + (f" | response: {_body}" if _body else ""),
        )

    # Step 4: Create version to persist the change
    try:
        requests.post(
            f"{processflow_base}/versioning/create_version",
            params={"sysparm_transaction_scope": "global"},
            json={
                "item_sys_id": params.flow_sys_id,
                "type": "Save",
                "annotation": f"Removed {len(found_ids)} step(s) via MCP",
                "favorite": False,
            },
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
    except requests.RequestException as e:
        logger.warning(
            "remove_steps_from_flow | create_version failed | flow_sys_id=%s | error=%s",
            params.flow_sys_id, e,
        )

    logger.info(
        "remove_steps_from_flow | removed %d step(s) | flow_sys_id=%s",
        len(found_ids), params.flow_sys_id,
    )
    return RemoveStepsFromFlowResponse(
        success=True,
        message=f"Successfully removed {len(found_ids)} step(s) from flow.",
        flow_sys_id=params.flow_sys_id,
        steps_removed=len(found_ids),
    )


def add_logic_to_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: AddLogicToFlowParams,
) -> AddLogicToFlowResponse:
    """
    Add a logic step (If, Else, For Each, Do Until, Set Flow Variables) to a flow.

    Uses the GET→append→PUT→create_version pattern. The logic block is added
    to the flow's flowLogicInstances array. Use list_flow_logic_types to
    discover available logic types and their definitionIds.

    For If/Else/End patterns:
      1. add_logic_to_flow with logic_type_sys_id=<If_id>, record uiUniqueIdentifier
         from logic_step_id → uiUniqueIdentifier (the returned logic_step_id IS the
         step's sys_id; the uiUniqueIdentifier is set to a new UUID by this function)
      2. add_logic_to_flow with logic_type_sys_id=<Else_id>, parent_ui_id=<If_uuid>
      3. add_logic_to_flow with logic_type_sys_id=<End_id>, parent_ui_id=<If_uuid>

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Logic step configuration.

    Returns:
        AddLogicToFlowResponse with success flag, message, and logic step id.
    """
    processflow_base = f"{config.api_url}/processflow"
    headers = auth_manager.get_headers()

    # Step 1: GET current flow payload
    try:
        get_response = requests.get(
            f"{processflow_base}/flow/{params.flow_sys_id}",
            headers=headers,
            timeout=config.timeout,
        )
        get_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "add_logic_to_flow | GET failed | flow_sys_id=%s | error=%s%s",
            params.flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return AddLogicToFlowResponse(
            success=False,
            message=f"Failed to fetch flow: {e}" + (f" | response: {_body}" if _body else ""),
        )

    flow_data = get_response.json().get("result", {}).get("data", {})
    if not flow_data:
        return AddLogicToFlowResponse(
            success=False,
            message=f"GET /processflow/flow/{params.flow_sys_id} returned no data.",
            flow_sys_id=params.flow_sys_id,
        )

    # Step 2: Build new flowLogicInstance
    new_step_id = str(uuid.uuid4()).replace("-", "")[:32]
    new_ui_id = str(uuid.uuid4())

    new_logic = {
        "id": new_step_id,
        "flowSysId": params.flow_sys_id,
        "order": str(params.order),
        "displayText": "",
        "uiUniqueIdentifier": new_ui_id,
        "deleted": False,
        "metadata": {},
        "parent": params.parent_ui_id or "",
        "comment": "",
        "generationSource": "",
        "uiComponentIndex": 0,
        "outputsToAssign": [],
        "inputs": [
            {"id": inp.name, "name": inp.name, "value": inp.value, "displayValue": ""}
            for inp in params.inputs
        ],
        "variables": [],
        "errors": [],
        "flowBlockId": "",
        "connectedTo": "",
        "quiescence": "",
        "definitionId": params.logic_type_sys_id,
        "workflowReference": "",
        "workflowInputs": [],
        "workflowInformation": {},
        "decisionTableReference": "",
        "decisionTableInputs": [],
        "dynamicInputs": [],
        "dynamicOutputs": [],
        "decisionTableInformation": {},
        "flowLogicDefinition": {},
        "flowVariables": [],
        "continue": False,
        "afterTopLevelCatch": False,
        "goBackTo": "",
        "appendToFlowVariables": [],
        "break": False,
        "updateFlowTemplate": {},
        "name": params.name,
        "type": "flowlogic",
        "internalName": "",
        "snapshot": {},
    }

    # Step 3: Build PUT body with new logic instance appended (do not mutate flow_data)
    logic_instances = list(flow_data.get("flowLogicInstances", []))
    logic_instances.append(new_logic)
    put_body = {**flow_data, "flowLogicInstances": logic_instances}

    # Step 4: PUT modified payload back
    try:
        put_response = requests.put(
            f"{processflow_base}/flow",
            params={"sysparm_transaction_scope": "global"},
            json=put_body,
            headers=headers,
            timeout=config.timeout,
        )
        put_response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "add_logic_to_flow | PUT failed | flow_sys_id=%s | error=%s%s",
            params.flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return AddLogicToFlowResponse(
            success=False,
            flow_sys_id=params.flow_sys_id,
            message=f"Failed to update flow: {e}" + (f" | response: {_body}" if _body else ""),
        )

    # Step 5: Create version
    try:
        requests.post(
            f"{processflow_base}/versioning/create_version",
            params={"sysparm_transaction_scope": "global"},
            json={
                "item_sys_id": params.flow_sys_id,
                "type": "Save",
                "annotation": f"Added logic step '{params.name}' via MCP",
                "favorite": False,
            },
            headers=headers,
            timeout=config.timeout,
        ).raise_for_status()
    except requests.RequestException as e:
        logger.warning(
            "add_logic_to_flow | create_version failed | flow_sys_id=%s | error=%s",
            params.flow_sys_id, e,
        )

    logger.info(
        "add_logic_to_flow | added logic step | flow_sys_id=%s | step_id=%s | name=%s",
        params.flow_sys_id, new_step_id, params.name,
    )
    return AddLogicToFlowResponse(
        success=True,
        message=f"Successfully added logic step '{params.name}' to flow.",
        flow_sys_id=params.flow_sys_id,
        logic_step_id=new_step_id,
    )


def list_action_type_outputs(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListActionTypeOutputsParams,
) -> ListActionTypeOutputsResult:
    """
    List output variable definitions for an action type.

    Returns the output data pills that an action type produces. These element
    names and sys_ids are needed to wire action outputs into subsequent step
    inputs using data pill references.

    Queries sys_hub_action_output filtered by model={definition_sys_id}.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: action_type_sys_id — the definition sys_id from list_action_types.

    Returns:
        ListActionTypeOutputsResult with list of output variable definitions.
    """
    try:
        response = requests.get(
            f"{config.api_url}/table/sys_hub_action_output",
            params={
                "sysparm_query": f"model={params.action_type_sys_id}",
                "sysparm_fields": "sys_id,element,label,column_label,internal_type,mandatory,default_value,order",
                "sysparm_display_value": "true",
                "sysparm_limit": 100,
                "sysparm_orderby": "order",
            },
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "list_action_type_outputs | request failed | action_type_sys_id=%s | error=%s%s",
            params.action_type_sys_id, e, f" | body={_body}" if _body else "",
        )
        return ListActionTypeOutputsResult(
            action_type_sys_id=params.action_type_sys_id,
            outputs=[],
            message=f"Failed to fetch action outputs: {e}" + (f" | response: {_body}" if _body else ""),
        )

    records = response.json().get("result", [])
    outputs = []
    for r in records:
        def _val(field: Any) -> str:
            """Extract string value from display_value dict or raw string."""
            if isinstance(field, dict):
                return field.get("value") or field.get("display_value") or ""
            return str(field) if field else ""

        outputs.append(ActionTypeOutput(
            sys_id=r.get("sys_id", ""),
            element=_val(r.get("element")) or r.get("element", ""),
            label=_val(r.get("label")) or _val(r.get("column_label")) or "",
            internal_type=_val(r.get("internal_type")) or "",
            mandatory=_val(r.get("mandatory")) == "true",
            default_value=_val(r.get("default_value")) or None,
            order=int(_val(r.get("order")) or 0),
        ))

    logger.info(
        "list_action_type_outputs | found %d output(s) | action_type_sys_id=%s",
        len(outputs), params.action_type_sys_id,
    )
    return ListActionTypeOutputsResult(
        action_type_sys_id=params.action_type_sys_id,
        outputs=outputs,
        message=f"Found {len(outputs)} output variable(s) for action type.",
    )


def list_flow_io(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListFlowIOParams,
) -> ListFlowIOResult:
    """
    List input and output variable definitions for a flow or subflow.

    Queries sys_hub_flow_input and sys_hub_flow_output filtered by the flow
    sys_id. Inputs define what the caller must provide (relevant for subflows).
    Outputs define what data the flow/subflow makes available downstream.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: flow_sys_id.

    Returns:
        ListFlowIOResult with separate inputs and outputs lists.
    """
    headers = auth_manager.get_headers()
    common_query_params = {
        "sysparm_fields": "sys_id,element,label,column_label,internal_type,mandatory,default_value,order",
        "sysparm_display_value": "true",
        "sysparm_limit": 100,
        "sysparm_orderby": "order",
    }

    def _parse_var(r: dict) -> FlowIOVariable:
        def _val(field: Any) -> str:
            if isinstance(field, dict):
                return field.get("value") or field.get("display_value") or ""
            return str(field) if field else ""
        return FlowIOVariable(
            sys_id=r.get("sys_id", ""),
            element=_val(r.get("element")) or r.get("element", ""),
            label=_val(r.get("label")) or _val(r.get("column_label")) or "",
            internal_type=_val(r.get("internal_type")) or "",
            mandatory=_val(r.get("mandatory")) == "true",
            default_value=_val(r.get("default_value")) or None,
            order=int(_val(r.get("order")) or 0),
        )

    def _fetch(table: str) -> list[FlowIOVariable] | str:
        try:
            resp = requests.get(
                f"{config.api_url}/table/{table}",
                params={
                    **common_query_params,
                    "sysparm_query": f"model={params.flow_sys_id}^model_table=sys_hub_flow",
                },
                headers=headers,
                timeout=config.timeout,
            )
            resp.raise_for_status()
            return [_parse_var(r) for r in resp.json().get("result", [])]
        except requests.RequestException as e:
            return str(e)

    inputs = _fetch("sys_hub_flow_input")
    if isinstance(inputs, str):
        logger.error("list_flow_io | inputs fetch failed | flow_sys_id=%s | error=%s", params.flow_sys_id, inputs)
        return ListFlowIOResult(
            flow_sys_id=params.flow_sys_id,
            inputs=[],
            outputs=[],
            message=f"Failed to fetch flow I/O: {inputs}",
        )

    outputs = _fetch("sys_hub_flow_output")
    if isinstance(outputs, str):
        logger.error("list_flow_io | outputs fetch failed | flow_sys_id=%s | error=%s", params.flow_sys_id, outputs)
        return ListFlowIOResult(
            flow_sys_id=params.flow_sys_id,
            inputs=[],
            outputs=[],
            message=f"Failed to fetch flow I/O: {outputs}",
        )

    logger.info(
        "list_flow_io | flow_sys_id=%s | inputs=%d | outputs=%d",
        params.flow_sys_id, len(inputs), len(outputs),
    )
    return ListFlowIOResult(
        flow_sys_id=params.flow_sys_id,
        inputs=inputs,
        outputs=outputs,
        message=f"Found {len(inputs)} input(s) and {len(outputs)} output(s) for flow.",
    )


def _extract_execution_id_from_test_response(data: Any) -> str | None:
    """Parse execution sys_id from POST /processflow/flow/{id}/test JSON (shape varies by release)."""
    if not isinstance(data, dict):
        return None
    cand = data.get("result", data)
    if not isinstance(cand, dict):
        return None
    for key in ("executionId", "execution_id", "sys_id", "contextId", "context_id"):
        v = cand.get(key)
        if v:
            return str(v)
    inner = cand.get("data")
    if isinstance(inner, dict):
        for key in ("executionId", "execution_id", "sys_id"):
            v = inner.get(key)
            if v:
                return str(v)
    return None


def _try_execute_flow_via_rest(
    config: ServerConfig,
    auth_manager: AuthManager,
    flow_sys_id: str,
    inputs_obj: dict[str, str],
) -> tuple[bool, str | None, str | None]:
    """POST /processflow/flow/{id}/test. Returns (ok, execution_id, error_message)."""
    url = f"{config.api_url}/processflow/flow/{flow_sys_id}/test"
    try:
        resp = requests.post(
            url,
            params={"sysparm_transaction_scope": "global"},
            json={"inputs": inputs_obj},
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        if resp.status_code != 200:
            return False, None, f"HTTP {resp.status_code}"
        body = resp.json()
        eid = _extract_execution_id_from_test_response(body)
        if eid:
            return True, eid, None
        return False, None, "test endpoint returned 200 but no execution id in response"
    except requests.RequestException as e:
        _body = _err_body(e)
        return False, None, str(e) + (f" | {_body}" if _body else "")


def execute_flow(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ExecuteFlowParams,
) -> ExecuteFlowResponse:
    """
    Manually execute a flow for testing.

    **Primary:** ``POST /api/now/processflow/flow/{sys_id}/test`` with JSON body
    ``{"inputs": {...}}`` (same ``inputs`` dict as ``list_flow_io`` element names).

    **Fallback:** server-side ``sn_fd.FlowAPI.startFlowAsync`` via the configured
    scripted background-script endpoint (requires ``script_execution_api_resource_path``).

    The flow runs asynchronously; returns an execution context id when the platform
    includes one in the response, correlatable with ``get_flow_execution_history``.
    """
    inputs_obj = dict(params.inputs) if params.inputs else {}

    rest_ok, rest_eid, rest_err = _try_execute_flow_via_rest(
        config, auth_manager, params.flow_sys_id.strip(), inputs_obj
    )
    if rest_ok and rest_eid:
        logger.info(
            "execute_flow | processflow test | flow_sys_id=%s | execution_id=%s",
            params.flow_sys_id, rest_eid,
        )
        return ExecuteFlowResponse(
            success=True,
            message=(
                f"Flow execution started (processflow test). execution_id={rest_eid}. "
                "Use get_flow_execution_history to check status."
            ),
            execution_id=rest_eid,
            execution_source="processflow_test",
        )

    if rest_err:
        logger.info(
            "execute_flow | REST test path did not yield execution id | flow_sys_id=%s | detail=%s",
            params.flow_sys_id, rest_err,
        )

    if not config.script_execution_api_resource_path:
        return ExecuteFlowResponse(
            success=False,
            message=(
                "Could not start execution via processflow test endpoint"
                + (f" ({rest_err})." if rest_err else ".")
                + " Script execution API is not configured (script_execution_api_resource_path), "
                "so GlideFlowAPI fallback is unavailable."
            ),
        )

    headers = auth_manager.get_headers()

    def _cell_str(raw: Any) -> str:
        if isinstance(raw, dict):
            return str(raw.get("value") or raw.get("display_value") or "") or ""
        return str(raw) if raw is not None else ""

    try:
        meta_response = requests.get(
            f"{config.api_url}/table/sys_hub_flow",
            params={
                "sysparm_query": f"sys_id={params.flow_sys_id}",
                "sysparm_fields": "sys_id,internal_name,scope",
                "sysparm_display_value": "all",
                "sysparm_limit": 1,
            },
            headers=headers,
            timeout=config.timeout,
        )
        meta_response.raise_for_status()
        records = meta_response.json().get("result", [])
        if not records:
            return ExecuteFlowResponse(
                success=False,
                message=f"Flow not found: sys_id={params.flow_sys_id}",
            )
        flow_meta = records[0]
        internal_name = _cell_str(flow_meta.get("internal_name")) or str(
            flow_meta.get("internal_name") or ""
        ).strip()
        if not internal_name:
            return ExecuteFlowResponse(
                success=False,
                message=f"Flow has no internal_name (sys_id={params.flow_sys_id}).",
            )
        scope_raw = flow_meta.get("scope")
        scope = _cell_str(scope_raw) if scope_raw is not None else ""
        if not scope:
            scope = "global"
    except requests.RequestException as e:
        _body = _err_body(e)
        logger.error(
            "execute_flow | meta fetch failed | flow_sys_id=%s | error=%s%s",
            params.flow_sys_id, e, f" | body={_body}" if _body else "",
        )
        return ExecuteFlowResponse(
            success=False,
            message=f"Failed to fetch flow metadata: {e}" + (f" | response: {_body}" if _body else ""),
        )

    inputs_js = json.dumps(inputs_obj)
    scoped_name = f"{scope}.{internal_name}" if scope and scope != "global" else internal_name
    flow_name_js = json.dumps(scoped_name)

    script = f"""
var flowName = {flow_name_js};
var inputs = {inputs_js};
try {{
  var execution = sn_fd.FlowAPI.startFlowAsync(flowName, inputs);
  var execId = execution ? execution.toString() : null;
  gs.info("execute_flow | started | flow=" + flowName + " | execution=" + execId);
  gs.print(JSON.stringify({{"executionId": execId, "state": "running", "flow": flowName}}));
}} catch (e) {{
  gs.print(JSON.stringify({{"error": e.message || String(e)}}));
}}
"""

    ok, msg, output_data = _invoke_scripted_js(
        config, auth_manager, script, log_prefix="execute_flow"
    )
    if not ok or output_data is None:
        return ExecuteFlowResponse(success=False, message=msg)

    if "error" in output_data:
        return ExecuteFlowResponse(
            success=False,
            message=f"Flow execution failed: {output_data['error']}",
        )

    execution_id = output_data.get("executionId")
    logger.info(
        "execute_flow | script fallback | flow_sys_id=%s | execution_id=%s",
        params.flow_sys_id, execution_id,
    )
    return ExecuteFlowResponse(
        success=True,
        message=(
            f"Flow execution started (script). execution_id={execution_id}. "
            "Use get_flow_execution_history to check status."
        ),
        execution_id=execution_id if isinstance(execution_id, str) else None,
        execution_source="script",
    )


def _build_get_flow_execution_detail_script(execution_sys_id: str) -> str:
    """Server-side script: load sys_hub_flow_context and sys_hub_flow_stage_context rows."""
    exec_js = json.dumps(execution_sys_id)
    return (
        "function rowToStep(gr) {\n"
        "  var o = { sys_id: gr.getUniqueValue() };\n"
        "  if (gr.isValidField('name')) o.name = String(gr.getDisplayValue('name') || gr.getValue('name') || '');\n"
        "  if (gr.isValidField('state')) o.state = gr.getValue('state') || '';\n"
        "  if (gr.isValidField('started')) o.started = gr.getValue('started') || '';\n"
        "  if (gr.isValidField('ended')) o.ended = gr.getValue('ended') || '';\n"
        "  if (gr.isValidField('output')) o.output = gr.getValue('output');\n"
        "  if (gr.isValidField('error')) o.error = gr.getValue('error');\n"
        "  return o;\n"
        "}\n"
        "function loadSteps(contextSysId) {\n"
        "  var steps = [];\n"
        "  var probe = new GlideRecord('sys_hub_flow_stage_context');\n"
        "  if (!probe.isValid()) return steps;\n"
        "  var qFields = ['flow_context', 'context', 'parent', 'execution_context'];\n"
        "  var seen = {};\n"
        "  for (var i = 0; i < qFields.length; i++) {\n"
        "    var qf = qFields[i];\n"
        "    if (!probe.isValidField(qf)) continue;\n"
        "    var g2 = new GlideRecord('sys_hub_flow_stage_context');\n"
        "    g2.addQuery(qf, contextSysId);\n"
        "    g2.orderBy('sys_created_on');\n"
        "    g2.query();\n"
        "    while (g2.next()) {\n"
        "      var sid = g2.getUniqueValue();\n"
        "      if (seen[sid]) continue;\n"
        "      seen[sid] = true;\n"
        "      steps.push(rowToStep(g2));\n"
        "    }\n"
        "  }\n"
        "  return steps;\n"
        "}\n"
        "var execId = "
        + exec_js
        + ";\n"
        "var grc = new GlideRecord('sys_hub_flow_context');\n"
        "if (!grc.get(execId)) {\n"
        "  gs.print(JSON.stringify({ error: 'not_found', execution_sys_id: execId }));\n"
        "} else {\n"
        "  var ctx = {\n"
        "    sys_id: grc.getUniqueValue(),\n"
        "    name: grc.isValidField('name') ? String(grc.getDisplayValue('name') || grc.getValue('name') || '') : '',\n"
        "    state: grc.getValue('state'),\n"
        "    started: grc.getValue('started'),\n"
        "    ended: grc.getValue('ended'),\n"
        "    error: grc.getValue('error'),\n"
        "    flow: grc.getValue('flow'),\n"
        "  };\n"
        "  gs.print(JSON.stringify({ context: ctx, steps: loadSteps(execId) }));\n"
        "}\n"
    )


def get_flow_execution_detail(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetFlowExecutionDetailParams,
) -> GetFlowExecutionDetailResult:
    """
    Return detail for one Flow Designer execution, including step-level rows when available.

    Uses the scripted background-script endpoint (same as execute_flow) because
    ``sys_hub_flow_context`` may be blocked for REST Table API on some service accounts.

    Step rows are read from ``sys_hub_flow_stage_context`` when that table exists.
    The server script queries candidate reference fields (``flow_context``, ``context``,
    ``parent``, ``execution_context``) and merges results, deduplicating by step ``sys_id``.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: execution_sys_id of ``sys_hub_flow_context``.

    Returns:
        GetFlowExecutionDetailResult with context fields and ``steps``.
    """
    script = _build_get_flow_execution_detail_script(params.execution_sys_id.strip())
    ok, msg, data = _invoke_scripted_js(
        config, auth_manager, script, log_prefix="get_flow_execution_detail"
    )
    if not ok or data is None:
        return GetFlowExecutionDetailResult(success=False, message=msg)

    if data.get("error") == "not_found":
        return GetFlowExecutionDetailResult(
            success=False,
            message=f"Execution not found: sys_id={params.execution_sys_id}",
        )

    ctx = data.get("context")
    steps_raw = data.get("steps")
    if not isinstance(ctx, dict):
        return GetFlowExecutionDetailResult(
            success=False,
            message="Script returned unexpected payload (missing context).",
        )

    steps: list[FlowExecutionStepDetail] = []
    if isinstance(steps_raw, list):
        for s in steps_raw:
            if not isinstance(s, dict) or not s.get("sys_id"):
                continue
            steps.append(
                FlowExecutionStepDetail(
                    sys_id=str(s["sys_id"]),
                    name=s.get("name"),
                    state=s.get("state"),
                    started=s.get("started"),
                    ended=s.get("ended"),
                    output=s.get("output"),
                    error=s.get("error"),
                )
            )

    logger.info(
        "get_flow_execution_detail | execution_sys_id=%s | steps=%d",
        ctx.get("sys_id"), len(steps),
    )
    return GetFlowExecutionDetailResult(
        success=True,
        message=f"Loaded execution detail with {len(steps)} step row(s).",
        execution_sys_id=str(ctx.get("sys_id")) if ctx.get("sys_id") else None,
        name=ctx.get("name") or None,
        state=ctx.get("state") or None,
        started=ctx.get("started") or None,
        ended=ctx.get("ended") or None,
        error=ctx.get("error") or None,
        flow=ctx.get("flow") or None,
        steps=steps,
    )

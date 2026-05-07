from typing import Any, Callable, Dict, Tuple, Type

# Import all necessary tool implementation functions and params models
# (This list needs to be kept complete and up-to-date)
from servicenow_mcp.tools.catalog_optimization import (
    OptimizationRecommendationsParams,
    UpdateCatalogItemParams,
)
from servicenow_mcp.tools.catalog_optimization import (
    get_optimization_recommendations as get_optimization_recommendations_tool,
)
from servicenow_mcp.tools.catalog_optimization import (
    update_catalog_item as update_catalog_item_tool,
)
from servicenow_mcp.tools.catalog_tools import (
    CreateCatalogCategoryParams,
    CreateCatalogItemParams,
    GetCatalogItemParams,
    ListCatalogCategoriesParams,
    ListCatalogItemsParams,
    MoveCatalogItemsParams,
    UpdateCatalogCategoryParams,
)
from servicenow_mcp.tools.catalog_tools import (
    create_catalog_category as create_catalog_category_tool,
)
from servicenow_mcp.tools.catalog_tools import (
    create_catalog_item as create_catalog_item_tool,
)
from servicenow_mcp.tools.catalog_tools import (
    get_catalog_item as get_catalog_item_tool,
)
from servicenow_mcp.tools.catalog_tools import (
    list_catalog_categories as list_catalog_categories_tool,
)
from servicenow_mcp.tools.catalog_tools import (
    list_catalog_items as list_catalog_items_tool,
)
from servicenow_mcp.tools.catalog_tools import (
    move_catalog_items as move_catalog_items_tool,
)
from servicenow_mcp.tools.catalog_tools import (
    update_catalog_category as update_catalog_category_tool,
)
from servicenow_mcp.tools.catalog_variables import (
    CatalogVariableChoiceResponse,
    CreateCatalogItemVariableParams,
    CreateCatalogVariableChoiceParams,
    DeleteCatalogItemVariableParams,
    ListCatalogItemVariablesParams,
    UpdateCatalogItemVariableParams,
)
from servicenow_mcp.tools.catalog_variables import (
    create_catalog_item_variable as create_catalog_item_variable_tool,
)
from servicenow_mcp.tools.catalog_variables import (
    create_catalog_variable_choice as create_catalog_variable_choice_tool,
)
from servicenow_mcp.tools.catalog_variables import (
    delete_catalog_item_variable as delete_catalog_item_variable_tool,
)
from servicenow_mcp.tools.catalog_variables import (
    list_catalog_item_variables as list_catalog_item_variables_tool,
)
from servicenow_mcp.tools.catalog_variables import (
    update_catalog_item_variable as update_catalog_item_variable_tool,
)
from servicenow_mcp.tools.change_tools import (
    AddChangeTaskParams,
    ApproveChangeParams,
    CreateChangeRequestParams,
    GetChangeRequestDetailsParams,
    ListChangeRequestsParams,
    RejectChangeParams,
    SubmitChangeForApprovalParams,
    UpdateChangeRequestParams,
)
from servicenow_mcp.tools.change_tools import (
    add_change_task as add_change_task_tool,
)
from servicenow_mcp.tools.change_tools import (
    approve_change as approve_change_tool,
)
from servicenow_mcp.tools.change_tools import (
    create_change_request as create_change_request_tool,
)
from servicenow_mcp.tools.change_tools import (
    get_change_request_details as get_change_request_details_tool,
)
from servicenow_mcp.tools.change_tools import (
    list_change_requests as list_change_requests_tool,
)
from servicenow_mcp.tools.change_tools import (
    reject_change as reject_change_tool,
)
from servicenow_mcp.tools.change_tools import (
    submit_change_for_approval as submit_change_for_approval_tool,
)
from servicenow_mcp.tools.change_tools import (
    update_change_request as update_change_request_tool,
)
from servicenow_mcp.tools.changeset_tools import (
    AddFileToChangesetParams,
    CommitChangesetParams,
    CreateChangesetParams,
    GetChangesetDetailsParams,
    ListChangesetsParams,
    PublishChangesetParams,
    UpdateChangesetParams,
)
from servicenow_mcp.tools.changeset_tools import (
    add_file_to_changeset as add_file_to_changeset_tool,
)
from servicenow_mcp.tools.changeset_tools import (
    commit_changeset as commit_changeset_tool,
)
from servicenow_mcp.tools.changeset_tools import (
    create_changeset as create_changeset_tool,
)
from servicenow_mcp.tools.changeset_tools import (
    get_changeset_details as get_changeset_details_tool,
)
from servicenow_mcp.tools.changeset_tools import (
    list_changesets as list_changesets_tool,
)
from servicenow_mcp.tools.changeset_tools import (
    publish_changeset as publish_changeset_tool,
)
from servicenow_mcp.tools.changeset_tools import (
    update_changeset as update_changeset_tool,
)
from servicenow_mcp.tools.incident_tools import (
    AddCommentParams,
    CreateIncidentParams,
    GetIncidentByNumberParams,
    GetIncidentJournalParams,
    ListIncidentsParams,
    ResolveIncidentParams,
    UpdateIncidentParams,
)
from servicenow_mcp.tools.incident_tools import (
    add_comment as add_comment_tool,
)
from servicenow_mcp.tools.incident_tools import (
    create_incident as create_incident_tool,
)
from servicenow_mcp.tools.incident_tools import (
    list_incidents as list_incidents_tool,
)
from servicenow_mcp.tools.incident_tools import (
    resolve_incident as resolve_incident_tool,
)
from servicenow_mcp.tools.incident_tools import (
    update_incident as update_incident_tool,
)
from servicenow_mcp.tools.incident_tools import (
    get_incident_by_number as get_incident_by_number_tool,
)
from servicenow_mcp.tools.incident_tools import (
    get_incident_journal as get_incident_journal_tool,
)
from servicenow_mcp.tools.knowledge_base import (
    CreateArticleParams,
    CreateKnowledgeBaseParams,
    GetArticleParams,
    ListArticlesParams,
    ListKnowledgeBasesParams,
    PublishArticleParams,
    UpdateArticleParams,
)
from servicenow_mcp.tools.knowledge_base import (
    CreateCategoryParams as CreateKBCategoryParams,  # Aliased
)
from servicenow_mcp.tools.knowledge_base import (
    ListCategoriesParams as ListKBCategoriesParams,  # Aliased
)
from servicenow_mcp.tools.knowledge_base import (
    create_article as create_article_tool,
)
from servicenow_mcp.tools.knowledge_base import (
    # create_category aliased in function call
    create_knowledge_base as create_knowledge_base_tool,
)
from servicenow_mcp.tools.knowledge_base import (
    get_article as get_article_tool,
)
from servicenow_mcp.tools.knowledge_base import (
    list_articles as list_articles_tool,
)
from servicenow_mcp.tools.knowledge_base import (
    # list_categories aliased in function call
    list_knowledge_bases as list_knowledge_bases_tool,
)
from servicenow_mcp.tools.knowledge_base import (
    publish_article as publish_article_tool,
)
from servicenow_mcp.tools.knowledge_base import (
    update_article as update_article_tool,
)
from servicenow_mcp.tools.script_include_tools import (
    CreateScriptIncludeParams,
    DeleteScriptIncludeParams,
    ExecuteScriptIncludeParams,
    GetScriptIncludeParams,
    ListScriptIncludesParams,
    ScriptIncludeResponse,
    UpdateScriptIncludeParams,
)
from servicenow_mcp.tools.script_include_tools import (
    create_script_include as create_script_include_tool,
)
from servicenow_mcp.tools.script_include_tools import (
    delete_script_include as delete_script_include_tool,
)
from servicenow_mcp.tools.script_include_tools import (
    execute_script_include as execute_script_include_tool,
)
from servicenow_mcp.tools.script_include_tools import (
    get_script_include as get_script_include_tool,
)
from servicenow_mcp.tools.script_include_tools import (
    list_script_includes as list_script_includes_tool,
)
from servicenow_mcp.tools.script_include_tools import (
    update_script_include as update_script_include_tool,
)
from servicenow_mcp.tools.nl_tools import (
    NaturalLanguageSearchParams,
    NaturalLanguageUpdateParams,
)
from servicenow_mcp.tools.nl_tools import (
    natural_language_search as natural_language_search_tool,
)
from servicenow_mcp.tools.nl_tools import (
    natural_language_update as natural_language_update_tool,
)
from servicenow_mcp.tools.user_tools import (
    AddGroupMembersParams,
    CreateGroupParams,
    CreateUserParams,
    GetUserParams,
    ListGroupsParams,
    ListUsersParams,
    RemoveGroupMembersParams,
    UpdateGroupParams,
    UpdateUserParams,
)
from servicenow_mcp.tools.user_tools import (
    add_group_members as add_group_members_tool,
)
from servicenow_mcp.tools.user_tools import (
    create_group as create_group_tool,
)
from servicenow_mcp.tools.user_tools import (
    create_user as create_user_tool,
)
from servicenow_mcp.tools.user_tools import (
    get_user as get_user_tool,
)
from servicenow_mcp.tools.user_tools import (
    list_groups as list_groups_tool,
)
from servicenow_mcp.tools.user_tools import (
    list_users as list_users_tool,
)
from servicenow_mcp.tools.user_tools import (
    remove_group_members as remove_group_members_tool,
)
from servicenow_mcp.tools.user_tools import (
    update_group as update_group_tool,
)
from servicenow_mcp.tools.user_tools import (
    update_user as update_user_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    ActivateWorkflowParams,
    AddWorkflowActivityParams,
    CreateWorkflowParams,
    DeactivateWorkflowParams,
    DeleteWorkflowActivityParams,
    GetWorkflowActivitiesParams,
    GetWorkflowDetailsParams,
    ListWorkflowsParams,
    ListWorkflowVersionsParams,
    ReorderWorkflowActivitiesParams,
    UpdateWorkflowActivityParams,
    UpdateWorkflowParams,
)
from servicenow_mcp.tools.workflow_tools import (
    activate_workflow as activate_workflow_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    add_workflow_activity as add_workflow_activity_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    create_workflow as create_workflow_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    deactivate_workflow as deactivate_workflow_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    delete_workflow_activity as delete_workflow_activity_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    get_workflow_activities as get_workflow_activities_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    get_workflow_details as get_workflow_details_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    list_workflow_versions as list_workflow_versions_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    list_workflows as list_workflows_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    reorder_workflow_activities as reorder_workflow_activities_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    update_workflow as update_workflow_tool,
)
from servicenow_mcp.tools.workflow_tools import (
    update_workflow_activity as update_workflow_activity_tool,
)
from servicenow_mcp.tools.story_tools import (
    CreateStoryParams,
    UpdateStoryParams,
    ListStoriesParams,
    ListStoryDependenciesParams,
    CreateStoryDependencyParams,
    DeleteStoryDependencyParams,
)
from servicenow_mcp.tools.story_tools import (
    create_story as create_story_tool,
    update_story as update_story_tool,
    list_stories as list_stories_tool,
    list_story_dependencies as list_story_dependencies_tool,
    create_story_dependency as create_story_dependency_tool,
    delete_story_dependency as delete_story_dependency_tool,
)
from servicenow_mcp.tools.epic_tools import (
    CreateEpicParams,
    UpdateEpicParams,
    ListEpicsParams,
)
from servicenow_mcp.tools.epic_tools import (
    create_epic as create_epic_tool,
    update_epic as update_epic_tool,
    list_epics as list_epics_tool,
)
from servicenow_mcp.tools.scrum_task_tools import (
    CreateScrumTaskParams,
    UpdateScrumTaskParams,
    ListScrumTasksParams,
)
from servicenow_mcp.tools.scrum_task_tools import (
    create_scrum_task as create_scrum_task_tool,
    update_scrum_task as update_scrum_task_tool,
    list_scrum_tasks as list_scrum_tasks_tool,
)
from servicenow_mcp.tools.project_tools import (
    CreateProjectParams,
    UpdateProjectParams,
    ListProjectsParams,
)
from servicenow_mcp.tools.project_tools import (
    create_project as create_project_tool,
    update_project as update_project_tool,
    list_projects as list_projects_tool,
)
from servicenow_mcp.tools.sctask_tools import (
    GetSCTaskParams,
    UpdateSCTaskParams,
    ListSCTasksParams,
)
from servicenow_mcp.tools.sctask_tools import (
    get_sctask as get_sctask_tool,
    list_sctasks as list_sctasks_tool,
    update_sctask as update_sctask_tool,
)
from servicenow_mcp.tools.time_card_tools import (
    ListTimeCardsParams,
    CreateTimeCardParams,
    UpdateTimeCardParams,
)
from servicenow_mcp.tools.time_card_tools import (
    list_time_cards as list_time_cards_tool,
    create_time_card as create_time_card_tool,
    update_time_card as update_time_card_tool,
)
from servicenow_mcp.tools.syslog_tools import (
    ListSyslogEntriesParams,
    GetSyslogEntryParams,
)
from servicenow_mcp.tools.syslog_tools import (
    list_syslog_entries as list_syslog_entries_tool,
    get_syslog_entry as get_syslog_entry_tool,
)
from servicenow_mcp.tools.bulk_tools import BulkOperationsParams
from servicenow_mcp.tools.bulk_tools import (
    execute_bulk_operations as execute_bulk_operations_tool,
)
from servicenow_mcp.tools.ui_policy_tools import (
    CreateUIPolicyParams,
    CreateUIPolicyActionParams,
)
from servicenow_mcp.tools.ui_policy_tools import (
    create_ui_policy as create_ui_policy_tool,
    create_ui_policy_action as create_ui_policy_action_tool,
)
from servicenow_mcp.tools.user_criteria_tools import (
    CreateUserCriteriaParams,
)
from servicenow_mcp.tools.user_criteria_tools import (
    create_user_criteria as create_user_criteria_tool,
)
from servicenow_mcp.tools.cmdb_tools import (
    CreateCIParams,
    GetCIParams,
    ListCIsParams,
    UpdateCIParams,
)
from servicenow_mcp.tools.cmdb_tools import (
    create_ci as create_ci_tool,
    get_ci as get_ci_tool,
    list_cis as list_cis_tool,
    update_ci as update_ci_tool,
)
from servicenow_mcp.tools.widget_tools import (
    CreateWidgetParams,
    GetWidgetParams,
    UpdateWidgetParams,
    WidgetResponse,
)
from servicenow_mcp.tools.widget_tools import (
    create_widget as create_widget_tool,
    get_widget as get_widget_tool,
    update_widget as update_widget_tool,
)
from servicenow_mcp.tools.case_tools import (
    GetCaseByNumberParams,
    ListCasesParams,
    SearchCasesParams,
)
from servicenow_mcp.tools.case_tools import (
    get_case_by_number as get_case_by_number_tool,
    list_cases as list_cases_tool,
    search_cases as search_cases_tool,
)
from servicenow_mcp.tools.scripted_rest_tools import (
    CreateScriptedRestApiParams,
    CreateScriptedRestResourceParams,
    ScriptedRestResponse,
)
from servicenow_mcp.tools.scripted_rest_tools import (
    create_scripted_rest_api as create_scripted_rest_api_tool,
    create_scripted_rest_resource as create_scripted_rest_resource_tool,
)
from servicenow_mcp.tools.import_set_tools import (
    CloneImportConfigurationParams,
    GetTransformMapParams,
    ListDataSourcesParams,
    ListFieldMappingsParams,
    ListImportRunsParams,
    ListImportSetsParams,
    ListScheduledImportsParams,
    ListTransformMapsParams,
    ListTransformScriptsParams,
    TriggerImportParams,
)
from servicenow_mcp.tools.import_set_tools import clone_import_configuration as clone_import_configuration_tool
from servicenow_mcp.tools.import_set_tools import get_transform_map as get_transform_map_tool
from servicenow_mcp.tools.import_set_tools import list_data_sources as list_data_sources_tool
from servicenow_mcp.tools.import_set_tools import list_field_mappings as list_field_mappings_tool
from servicenow_mcp.tools.import_set_tools import list_import_runs as list_import_runs_tool
from servicenow_mcp.tools.import_set_tools import list_import_sets as list_import_sets_tool
from servicenow_mcp.tools.import_set_tools import list_scheduled_imports as list_scheduled_imports_tool
from servicenow_mcp.tools.import_set_tools import list_transform_maps as list_transform_maps_tool
from servicenow_mcp.tools.import_set_tools import list_transform_scripts as list_transform_scripts_tool
from servicenow_mcp.tools.import_set_tools import trigger_import as trigger_import_tool
from servicenow_mcp.tools.acl_tools import (
    ACLResponse,
    CreateACLParams,
    CreateRoleParams,
    CreateSecurityAttributeParams,
    DeleteACLParams,
    GetACLParams,
    GetRoleParams,
    ListACLsParams,
    ListRolesParams,
    ListSecurityAttributesParams,
    UpdateACLParams,
    UpdateRoleParams,
)
from servicenow_mcp.tools.acl_tools import create_acl as create_acl_tool
from servicenow_mcp.tools.acl_tools import create_role as create_role_tool
from servicenow_mcp.tools.acl_tools import create_security_attribute as create_security_attribute_tool
from servicenow_mcp.tools.acl_tools import delete_acl as delete_acl_tool
from servicenow_mcp.tools.acl_tools import get_acl as get_acl_tool
from servicenow_mcp.tools.acl_tools import get_role as get_role_tool
from servicenow_mcp.tools.acl_tools import list_acls as list_acls_tool
from servicenow_mcp.tools.acl_tools import list_roles as list_roles_tool
from servicenow_mcp.tools.acl_tools import list_security_attributes as list_security_attributes_tool
from servicenow_mcp.tools.acl_tools import update_acl as update_acl_tool
from servicenow_mcp.tools.acl_tools import update_role as update_role_tool
from servicenow_mcp.tools.flow_tools import (
    AddLogicToFlowParams,
    AddLogicToFlowResponse,
    AddStepsToFlowParams,
    AddStepsToFlowResponse,
    AddSubflowStepToFlowParams,
    AddSubflowStepToFlowResponse,
    CreateActionParams,
    CreateFlowParams,
    CreateFlowResponse,
    CreateSubflowParams,
    DeleteActionParams,
    DeleteArtifactResponse,
    DeleteFlowParams,
    DeleteSubflowParams,
    ExecuteFlowParams,
    ExecuteFlowResponse,
    GetActionParams,
    GetArtifactResponse,
    GetFlowActionsParams,
    GetFlowExecutionDetailParams,
    GetFlowExecutionDetailResult,
    GetFlowExecutionHistoryParams,
    GetFlowExecutionHistoryResult,
    GetFlowParams,
    GetFlowTriggersParams,
    GetFlowVersionParams,
    GetSubflowParams,
    ListActionTypeInputsParams,
    ListActionTypeInputsResult,
    ListActionTypeOutputsParams,
    ListActionTypeOutputsResult,
    ListActionsParams,
    ListActionTypesParams,
    ListActionTypesResult,
    ListArtifactsResponse,
    ListFlowIOParams,
    ListFlowIOResult,
    ListFlowLogicTypesParams,
    ListFlowLogicTypesResult,
    ListFlowsParams,
    ListSubflowsParams,
    ListTriggerTypesParams,
    ListTriggerTypesResult,
    MutationResponse,
    PublishActionParams,
    PublishFlowParams,
    PublishSubflowParams,
    CloneFlowParams,
    CloneFlowResponse,
    RemoveStepsFromFlowParams,
    RemoveStepsFromFlowResponse,
    UpdateFlowTriggerParams,
    UpdateFlowTriggerResponse,
    UpdateActionParams,
    UpdateFlowParams,
    UpdateSubflowParams,
)
from servicenow_mcp.tools.flow_tools import (
    add_logic_to_flow as add_logic_to_flow_tool,
    add_steps_to_flow as add_steps_to_flow_tool,
    add_subflow_step_to_flow as add_subflow_step_to_flow_tool,
    create_action as create_action_tool,
    create_flow as create_flow_tool,
    clone_flow as clone_flow_tool,
    delete_action as delete_action_tool,
    delete_flow as delete_flow_tool,
    delete_subflow as delete_subflow_tool,
    execute_flow as execute_flow_tool,
    update_flow_trigger as update_flow_trigger_tool,
    create_subflow as create_subflow_tool,
    get_action as get_action_tool,
    get_flow as get_flow_tool,
    get_flow_actions as get_flow_actions_tool,
    get_flow_execution_detail as get_flow_execution_detail_tool,
    get_flow_execution_history as get_flow_execution_history_tool,
    get_flow_triggers as get_flow_triggers_tool,
    get_flow_version as get_flow_version_tool,
    get_subflow as get_subflow_tool,
    list_action_type_inputs as list_action_type_inputs_tool,
    list_action_type_outputs as list_action_type_outputs_tool,
    list_action_types as list_action_types_tool,
    list_actions as list_actions_tool,
    list_flow_io as list_flow_io_tool,
    list_flow_logic_types as list_flow_logic_types_tool,
    list_flows as list_flows_tool,
    list_subflows as list_subflows_tool,
    list_trigger_types as list_trigger_types_tool,
    publish_action as publish_action_tool,
    publish_flow as publish_flow_tool,
    publish_subflow as publish_subflow_tool,
    remove_steps_from_flow as remove_steps_from_flow_tool,
    update_action as update_action_tool,
    update_flow as update_flow_tool,
    update_subflow as update_subflow_tool,
)
from servicenow_mcp.tools.csm_tools import (
    GetCaseHistoryParams,
    GetCasesByAccountParams,
    GetCasesByIntegrationParams,
    GetCasesByLocationParams,
    GetCasesByProductParams,
    ListAccountsParams,
    ListLocationsParams,
    ListProductsParams,
)
from servicenow_mcp.tools.csm_tools import (
    get_case_history as get_case_history_tool,
    get_cases_by_account as get_cases_by_account_tool,
    get_cases_by_integration as get_cases_by_integration_tool,
    get_cases_by_location as get_cases_by_location_tool,
    get_cases_by_product as get_cases_by_product_tool,
    list_accounts as list_accounts_tool,
    list_locations as list_locations_tool,
    list_products as list_products_tool,
)
from servicenow_mcp.tools.table_api_tools import (
    TableGetRecordsParams,
    TableGetRecordParams,
    TableCreateRecordParams,
    TableUpdateRecordParams,
    TableDeleteRecordParams,
)
from servicenow_mcp.tools.table_api_tools import (
    table_get_records as table_get_records_tool,
    table_get_record as table_get_record_tool,
    table_create_record as table_create_record_tool,
    table_update_record as table_update_record_tool,
    table_delete_record as table_delete_record_tool,
)
# --- System Dictionary Tools ---
from servicenow_mcp.tools.sys_dictionary_tools import (
    CreateFieldParams,
    ListFieldsParams,
    UpdateFieldParams,
)
from servicenow_mcp.tools.sys_dictionary_tools import (
    create_field as create_field_tool,
    list_fields as list_fields_tool,
    update_field as update_field_tool,
)
# --- Business Rule Tools ---
from servicenow_mcp.tools.business_rule_tools import (
    CreateBusinessRuleParams,
    ListBusinessRulesParams,
    GetBusinessRuleParams,
    UpdateBusinessRuleParams,
    DeleteBusinessRuleParams,
)
from servicenow_mcp.tools.business_rule_tools import (
    create_business_rule as create_business_rule_tool,
    list_business_rules as list_business_rules_tool,
    get_business_rule as get_business_rule_tool,
    update_business_rule as update_business_rule_tool,
    delete_business_rule as delete_business_rule_tool,
)
# --- Scheduled Job Tools ---
from servicenow_mcp.tools.scheduled_job_tools import (
    CreateScheduledJobParams,
    ListScheduledJobsParams,
    GetScheduledJobParams,
    UpdateScheduledJobParams,
    DeleteScheduledJobParams,
)
from servicenow_mcp.tools.scheduled_job_tools import (
    create_scheduled_job as create_scheduled_job_tool,
    list_scheduled_jobs as list_scheduled_jobs_tool,
    get_scheduled_job as get_scheduled_job_tool,
    update_scheduled_job as update_scheduled_job_tool,
    delete_scheduled_job as delete_scheduled_job_tool,
)
# --- REST Message Tools ---
from servicenow_mcp.tools.rest_message_tools import (
    CreateRestMessageParams,
    ListRestMessagesParams,
    GetRestMessageParams,
    UpdateRestMessageParams,
    DeleteRestMessageParams,
    CreateHttpMethodParams,
    ListHttpMethodsParams,
    UpdateHttpMethodParams,
    DeleteHttpMethodParams,
)
from servicenow_mcp.tools.rest_message_tools import (
    create_rest_message as create_rest_message_tool,
    list_rest_messages as list_rest_messages_tool,
    get_rest_message as get_rest_message_tool,
    update_rest_message as update_rest_message_tool,
    delete_rest_message as delete_rest_message_tool,
    create_http_method as create_http_method_tool,
    list_http_methods as list_http_methods_tool,
    update_http_method as update_http_method_tool,
    delete_http_method as delete_http_method_tool,
)
# --- OAuth Credential Tools ---
from servicenow_mcp.tools.oauth_tools import (
    CreateOAuthEntityParams,
    ListOAuthEntitiesParams,
    GetOAuthEntityParams,
    UpdateOAuthEntityParams,
    DeleteOAuthEntityParams,
    CreateOAuthProfileParams,
    ListOAuthProfilesParams,
    UpdateOAuthProfileParams,
    DeleteOAuthProfileParams,
)
from servicenow_mcp.tools.oauth_tools import (
    create_oauth_entity as create_oauth_entity_tool,
    list_oauth_entities as list_oauth_entities_tool,
    get_oauth_entity as get_oauth_entity_tool,
    update_oauth_entity as update_oauth_entity_tool,
    delete_oauth_entity as delete_oauth_entity_tool,
    create_oauth_profile as create_oauth_profile_tool,
    list_oauth_profiles as list_oauth_profiles_tool,
    update_oauth_profile as update_oauth_profile_tool,
    delete_oauth_profile as delete_oauth_profile_tool,
)
from servicenow_mcp.tools.cmdb_relationship_tools import (
    CreateCIRelationshipParams,
    DeleteCIRelationshipParams,
    GetCIRelationshipParams,
    ListCIRelationshipsParams,
    ListCIRelationshipTypesParams,
)
from servicenow_mcp.tools.cmdb_relationship_tools import (
    create_ci_relationship as create_ci_relationship_tool,
    delete_ci_relationship as delete_ci_relationship_tool,
    get_ci_relationship as get_ci_relationship_tool,
    list_ci_relationships as list_ci_relationships_tool,
    list_ci_relationship_types as list_ci_relationship_types_tool,
)
from servicenow_mcp.tools.asset_tools import (
    CreateAssetParams,
    DeleteAssetParams,
    GetAssetParams,
    ListAssetsParams,
    UpdateAssetParams,
)
from servicenow_mcp.tools.asset_tools import (
    create_asset as create_asset_tool,
    delete_asset as delete_asset_tool,
    get_asset as get_asset_tool,
    list_assets as list_assets_tool,
    update_asset as update_asset_tool,
)
from servicenow_mcp.tools.contract_tools import (
    CreateAssetContractParams,
    GetAssetContractParams,
    ListAssetContractsParams,
    UpdateAssetContractParams,
)
from servicenow_mcp.tools.contract_tools import (
    create_asset_contract as create_asset_contract_tool,
    get_asset_contract as get_asset_contract_tool,
    list_asset_contracts as list_asset_contracts_tool,
    update_asset_contract as update_asset_contract_tool,
)

# Define a type alias for the Pydantic models or dataclasses used for params
ParamsModel = Type[Any]  # Use Type[Any] for broader compatibility initially

# Define the structure of the tool definition tuple
ToolDefinition = Tuple[
    Callable,  # Implementation function
    ParamsModel,  # Pydantic model for parameters
    Type,  # Return type annotation (used for hints, not strictly enforced by low-level server)
    str,  # Description
    str,  # Serialization method ('str', 'json', 'dict', 'model_dump', etc.)
]


def get_tool_definitions(
    create_kb_category_tool_impl: Callable, list_kb_categories_tool_impl: Callable
) -> Dict[str, ToolDefinition]:
    """
    Returns a dictionary containing definitions for all available ServiceNow tools.

    This centralizes the tool definitions for use in the server implementation.
    Pass aliased functions for KB categories directly.

    Returns:
        Dict[str, ToolDefinition]: A dictionary mapping tool names to their definitions.
    """
    tool_definitions: Dict[str, ToolDefinition] = {
        # Incident Tools
        "create_incident": (
            create_incident_tool,
            CreateIncidentParams,
            str,
            "Create a new incident in ServiceNow. Pass assignment_group as a display name string (e.g. 'Network Support') — not a sys_id.",
            "str",
        ),
        "update_incident": (
            update_incident_tool,
            UpdateIncidentParams,
            str,
            "Update fields on an existing incident. incident_id accepts either an INC number (e.g. 'INC0012345') or a 32-char hex sys_id. Only pass fields that need to change.",
            "str",
        ),
        "add_comment": (
            add_comment_tool,
            AddCommentParams,
            str,
            "Add a comment or work note to an incident. Set is_work_note=true for internal work notes visible only to agents; false (default) for customer-visible comments.",
            "str",
        ),
        "resolve_incident": (
            resolve_incident_tool,
            ResolveIncidentParams,
            str,
            "Resolve an incident by setting its state to Resolved. Requires a resolution_code and resolution_notes. incident_id accepts an INC number or sys_id.",
            "str",
        ),
        "list_incidents": (
            list_incidents_tool,
            ListIncidentsParams,
            str,  # Expects JSON string
            "List incidents from ServiceNow",
            "json",  # Tool returns list/dict, needs JSON dump
        ),
        "get_incident_by_number": (
            get_incident_by_number_tool,
            GetIncidentByNumberParams,
            str,
            "Fetch full details of a single incident by its INC number (e.g. 'INC0012345'). Use this when you have the exact number; use list_incidents to search.",
            "json_dict",
        ),
        "get_incident_journal": (
            get_incident_journal_tool,
            GetIncidentJournalParams,
            str,
            (
                "Fetch the work_notes and comments timeline for an incident. "
                "Resolves the incident number to sys_id, then queries "
                "sys_journal_field for chronologically-ordered journal entries. "
                "Useful when the LLM needs the full conversation history on a ticket. "
                "Closes echelon Issue #52."
            ),
            "json_dict",
        ),
        # Catalog Tools
        "list_catalog_items": (
            list_catalog_items_tool,
            ListCatalogItemsParams,
            str,
            "List service catalog items. Use 'query' for free-text name search; use 'category' for exact category filter. Defaults to active items only.",
            "json",
        ),
        "get_catalog_item": (
            get_catalog_item_tool,
            GetCatalogItemParams,
            str,
            "Fetch full details of a single catalog item by its sys_id or catalog item ID. Use list_catalog_items to find the ID first.",
            "json_dict",
        ),
        "list_catalog_categories": (
            list_catalog_categories_tool,
            ListCatalogCategoriesParams,
            str,
            "List service catalog categories. Use 'query' for partial name search. Defaults to active categories only.",
            "json",
        ),
        "create_catalog_category": (
            create_catalog_category_tool,
            CreateCatalogCategoryParams,
            str,
            "Create a new category in the service catalog.",
            "json_dict",
        ),
        "update_catalog_category": (
            update_catalog_category_tool,
            UpdateCatalogCategoryParams,
            str,
            "Update an existing catalog category. Requires the category sys_id; use list_catalog_categories to find it.",
            "json_dict",
        ),
        "move_catalog_items": (
            move_catalog_items_tool,
            MoveCatalogItemsParams,
            str,
            "Move one or more catalog items to a different category. Provide item sys_ids and the target category sys_id.",
            "json_dict",
        ),
        "get_optimization_recommendations": (
            get_optimization_recommendations_tool,
            OptimizationRecommendationsParams,
            str,
            "Analyse the service catalog and return optimization recommendations (unused items, duplicates, missing descriptions, etc.).",
            "json",
        ),
        "update_catalog_item": (
            update_catalog_item_tool,
            UpdateCatalogItemParams,
            str,
            "Update fields on an existing catalog item. Requires the item sys_id; only pass fields that need to change.",
            "json",
        ),
        "create_catalog_item": (
            create_catalog_item_tool,
            CreateCatalogItemParams,
            str,
            "Create a new service catalog item in ServiceNow",
            "json_dict",
        ),
        # Catalog Variables
        "create_catalog_item_variable": (
            create_catalog_item_variable_tool,
            CreateCatalogItemVariableParams,
            Dict[str, Any],
            "Add a new input variable (question) to a catalog item. Requires the catalog item sys_id.",
            "dict",
        ),
        "list_catalog_item_variables": (
            list_catalog_item_variables_tool,
            ListCatalogItemVariablesParams,
            Dict[str, Any],
            "List all input variables defined on a catalog item. Requires the catalog item sys_id.",
            "dict",
        ),
        "update_catalog_item_variable": (
            update_catalog_item_variable_tool,
            UpdateCatalogItemVariableParams,
            Dict[str, Any],
            "Update an existing catalog item variable. Requires both the catalog item sys_id and the variable sys_id.",
            "dict",
        ),
        "delete_catalog_item_variable": (
            delete_catalog_item_variable_tool,
            DeleteCatalogItemVariableParams,
            Dict[str, Any],  # Expects dict
            "Delete a catalog item variable by sys_id",
            "dict",  # Tool returns Pydantic model
        ),
        "create_catalog_variable_choice": (
            create_catalog_variable_choice_tool,
            CreateCatalogVariableChoiceParams,
            CatalogVariableChoiceResponse,
            "Create a choice option for a select-type catalog item variable",
            "dict",
        ),
        # Change Management Tools
        "create_change_request": (
            create_change_request_tool,
            CreateChangeRequestParams,
            str,
            "Create a new change request (normal, standard, or emergency). Pass assignment_group as a display name string.",
            "str",
        ),
        "update_change_request": (
            update_change_request_tool,
            UpdateChangeRequestParams,
            str,
            "Update fields on an existing change request. change_id accepts a CHG number or sys_id. Only pass fields that need to change.",
            "str",
        ),
        "list_change_requests": (
            list_change_requests_tool,
            ListChangeRequestsParams,
            str,
            "List change requests with optional filters. Use 'state', 'type', 'category', 'assignment_group', or 'timeframe' for structured filters. Use 'query' only for raw ServiceNow encoded query strings.",
            "json",
        ),
        "get_change_request_details": (
            get_change_request_details_tool,
            GetChangeRequestDetailsParams,
            str,
            "Fetch full details of a single change request by its CHG number or sys_id.",
            "json",
        ),
        "add_change_task": (
            add_change_task_tool,
            AddChangeTaskParams,
            str,
            "Add a sub-task to an existing change request. change_id accepts a CHG number or sys_id.",
            "json_dict",
        ),
        "submit_change_for_approval": (
            submit_change_for_approval_tool,
            SubmitChangeForApprovalParams,
            str,
            "Move a change request into the approval workflow. change_id accepts a CHG number or sys_id.",
            "str",
        ),
        "approve_change": (
            approve_change_tool,
            ApproveChangeParams,
            str,
            "Record an approval decision on a change request. change_id accepts a CHG number or sys_id.",
            "str",
        ),
        "reject_change": (
            reject_change_tool,
            RejectChangeParams,
            str,
            "Reject a change request and record the reason. change_id accepts a CHG number or sys_id.",
            "str",
        ),
        # Workflow Management Tools
        "list_workflows": (
            list_workflows_tool,
            ListWorkflowsParams,
            str,
            "List ServiceNow workflows. Use 'query' for name search and 'active' to filter by status.",
            "json",
        ),
        "get_workflow_details": (
            get_workflow_details_tool,
            GetWorkflowDetailsParams,
            str,
            "Fetch full details of a single workflow by its sys_id.",
            "json",
        ),
        "list_workflow_versions": (
            list_workflow_versions_tool,
            ListWorkflowVersionsParams,
            str,
            "List all published versions of a workflow. Requires the workflow sys_id.",
            "json",
        ),
        "get_workflow_activities": (
            get_workflow_activities_tool,
            GetWorkflowActivitiesParams,
            str,
            "List all activities (steps) in a specific workflow version. Requires the workflow sys_id.",
            "json",
        ),
        "create_workflow": (
            create_workflow_tool,
            CreateWorkflowParams,
            str,
            "Create a new workflow in ServiceNow.",
            "json_dict",
        ),
        "update_workflow": (
            update_workflow_tool,
            UpdateWorkflowParams,
            str,
            "Update an existing workflow's metadata. Requires the workflow sys_id. To change activities use add/update/delete_workflow_activity.",
            "json_dict",
        ),
        "activate_workflow": (
            activate_workflow_tool,
            ActivateWorkflowParams,
            str,
            "Activate (publish) a workflow so it can be triggered. Requires the workflow sys_id.",
            "str",
        ),
        "deactivate_workflow": (
            deactivate_workflow_tool,
            DeactivateWorkflowParams,
            str,
            "Deactivate a workflow to prevent it from being triggered. Requires the workflow sys_id.",
            "str",
        ),
        "add_workflow_activity": (
            add_workflow_activity_tool,
            AddWorkflowActivityParams,
            str,
            "Add a new activity (step) to a workflow. Requires the workflow sys_id and activity type.",
            "json_dict",
        ),
        "update_workflow_activity": (
            update_workflow_activity_tool,
            UpdateWorkflowActivityParams,
            str,
            "Update an existing workflow activity. Requires both the workflow sys_id and the activity sys_id.",
            "json_dict",
        ),
        "delete_workflow_activity": (
            delete_workflow_activity_tool,
            DeleteWorkflowActivityParams,
            str,
            "Delete an activity from a workflow. Requires both the workflow sys_id and the activity sys_id.",
            "str",
        ),
        "reorder_workflow_activities": (
            reorder_workflow_activities_tool,
            ReorderWorkflowActivitiesParams,
            str,
            "Change the execution order of activities within a workflow. Requires the workflow sys_id and an ordered list of activity sys_ids.",
            "str",
        ),
        # Changeset Management Tools
        "list_changesets": (
            list_changesets_tool,
            ListChangesetsParams,
            str,
            "List developer changesets (source control batches) in ServiceNow. Filter by state or developer.",
            "json",
        ),
        "get_changeset_details": (
            get_changeset_details_tool,
            GetChangesetDetailsParams,
            str,
            "Fetch full details of a single changeset including all files it contains. Requires the changeset sys_id.",
            "json",
        ),
        "create_changeset": (
            create_changeset_tool,
            CreateChangesetParams,
            str,
            "Create a new developer changeset for grouping configuration changes before commit.",
            "json_dict",
        ),
        "update_changeset": (
            update_changeset_tool,
            UpdateChangesetParams,
            str,
            "Update an existing changeset's metadata. Requires the changeset sys_id.",
            "json_dict",
        ),
        "commit_changeset": (
            commit_changeset_tool,
            CommitChangesetParams,
            str,
            "Commit a changeset to the local update set. Requires the changeset sys_id.",
            "str",
        ),
        "publish_changeset": (
            publish_changeset_tool,
            PublishChangesetParams,
            str,
            "Publish a committed changeset to make it available for deployment. Requires the changeset sys_id.",
            "str",
        ),
        "add_file_to_changeset": (
            add_file_to_changeset_tool,
            AddFileToChangesetParams,
            str,
            "Add a configuration file/record to an existing changeset. Requires the changeset sys_id and the file sys_id.",
            "str",
        ),
        # Script Include Tools
        "list_script_includes": (
            list_script_includes_tool,
            ListScriptIncludesParams,
            Dict[str, Any],
            "List server-side Script Include records. Use 'query' to search by name.",
            "raw_dict",
        ),
        "get_script_include": (
            get_script_include_tool,
            GetScriptIncludeParams,
            Dict[str, Any],
            "Fetch the full script body of a specific Script Include by its sys_id or name.",
            "raw_dict",
        ),
        "create_script_include": (
            create_script_include_tool,
            CreateScriptIncludeParams,
            ScriptIncludeResponse,
            "Create a new server-side Script Include record with the provided JavaScript body.",
            "raw_pydantic",
        ),
        "update_script_include": (
            update_script_include_tool,
            UpdateScriptIncludeParams,
            ScriptIncludeResponse,
            "Update the script body or metadata of an existing Script Include. Requires the sys_id.",
            "raw_pydantic",
        ),
        "delete_script_include": (
            delete_script_include_tool,
            DeleteScriptIncludeParams,
            str,
            "Permanently delete a Script Include record. Requires the sys_id. This cannot be undone.",
            "json_dict",
        ),
        # Natural-language tools (gated to nl_power_user package by default)
        "natural_language_search": (
            natural_language_search_tool,
            NaturalLanguageSearchParams,
            str,
            (
                "Search ServiceNow records using a natural-language phrase "
                "like 'find incidents about SAP with high priority'. "
                "Returns up to 10 records."
            ),
            "raw_pydantic",
        ),
        "natural_language_update": (
            natural_language_update_tool,
            NaturalLanguageUpdateParams,
            str,
            (
                "Update a record using a natural-language phrase like "
                "'close incident INC0010003 with resolution: fixed the issue'. "
                "Looks up the record by number and applies the parsed updates."
            ),
            "raw_pydantic",
        ),
        # Registered but NOT in any default package — see SECURITY note in
        # config/tool_packages.yaml. Issue #43 finding #1.
        "execute_script_include": (
            execute_script_include_tool,
            ExecuteScriptIncludeParams,
            Dict[str, Any],
            (
                "Execute a method on a ServiceNow Script Include and return its result. "
                "Resolves the script include by name or sys_id, then calls the specified "
                "method with optional positional arguments via the server-side scripting "
                "eval endpoint."
            ),
            "raw_dict",
        ),
        # Knowledge Base Tools
        "create_knowledge_base": (
            create_knowledge_base_tool,
            CreateKnowledgeBaseParams,
            str,
            "Create a new knowledge base in ServiceNow.",
            "json_dict",
        ),
        "list_knowledge_bases": (
            list_knowledge_bases_tool,
            ListKnowledgeBasesParams,
            Dict[str, Any],
            "List knowledge bases. Use 'query' for name search; use 'active' to filter by status.",
            "raw_dict",
        ),
        "create_category": (
            create_kb_category_tool_impl,
            CreateKBCategoryParams,
            str,
            "Create a new category inside a knowledge base. Requires the knowledge base sys_id.",
            "json_dict",
        ),
        "create_article": (
            create_article_tool,
            CreateArticleParams,
            str,
            "Create a new knowledge article in draft state. Requires the knowledge base sys_id. Use publish_article to make it live.",
            "json_dict",
        ),
        "update_article": (
            update_article_tool,
            UpdateArticleParams,
            str,
            "Update an existing knowledge article's content or metadata. Requires the article sys_id.",
            "json_dict",
        ),
        "publish_article": (
            publish_article_tool,
            PublishArticleParams,
            str,
            "Publish a knowledge article to make it visible to end users. Requires the article sys_id.",
            "json_dict",
        ),
        "list_articles": (
            list_articles_tool,
            ListArticlesParams,
            Dict[str, Any],
            "List knowledge articles. Filter by 'knowledge_base' sys_id, 'category' sys_id, 'workflow_state' (draft/published/retired), or free-text 'query'.",
            "raw_dict",
        ),
        "get_article": (
            get_article_tool,
            GetArticleParams,
            Dict[str, Any],
            "Fetch the full content of a specific knowledge article by its sys_id.",
            "raw_dict",
        ),
        "list_categories": (
            list_kb_categories_tool_impl,
            ListKBCategoriesParams,
            Dict[str, Any],
            "List categories within a knowledge base. Filter by 'knowledge_base' sys_id or 'parent_category' sys_id for sub-categories.",
            "raw_dict",
        ),
        # User Management Tools
        "create_user": (
            create_user_tool,
            CreateUserParams,
            Dict[str, Any],
            "Create a new user record in ServiceNow.",
            "raw_dict",
        ),
        "update_user": (
            update_user_tool,
            UpdateUserParams,
            Dict[str, Any],
            "Update an existing user record. Requires the user sys_id. Only pass fields that need to change.",
            "raw_dict",
        ),
        "get_user": (
            get_user_tool,
            GetUserParams,
            Dict[str, Any],
            "Fetch a specific user by sys_id, username, or email. Provide only one identifier.",
            "raw_dict",
        ),
        "list_users": (
            list_users_tool,
            ListUsersParams,
            Dict[str, Any],
            "List users with optional filters. Use 'query' for partial match on name, username, or email. Use 'department' or 'active' for exact filters.",
            "raw_dict",
        ),
        "create_group": (
            create_group_tool,
            CreateGroupParams,
            Dict[str, Any],
            "Create a new user group in ServiceNow.",
            "raw_dict",
        ),
        "update_group": (
            update_group_tool,
            UpdateGroupParams,
            Dict[str, Any],
            "Update an existing group's metadata. Requires the group sys_id.",
            "raw_dict",
        ),
        "add_group_members": (
            add_group_members_tool,
            AddGroupMembersParams,
            Dict[str, Any],
            "Add one or more users to a group. Requires the group sys_id and a list of user sys_ids.",
            "raw_dict",
        ),
        "remove_group_members": (
            remove_group_members_tool,
            RemoveGroupMembersParams,
            Dict[str, Any],
            "Remove one or more users from a group. Requires the group sys_id and a list of user sys_ids.",
            "raw_dict",
        ),
        "list_groups": (
            list_groups_tool,
            ListGroupsParams,
            Dict[str, Any],
            "List user groups. Use 'query' for partial match on group name or description. Use 'type' or 'active' for exact filters.",
            "raw_dict",
        ),
        # Story Management Tools
        "create_story": (
            create_story_tool,
            CreateStoryParams,
            str,
            "Create a new agile story in ServiceNow. Requires a parent epic sys_id.",
            "str",
        ),
        "update_story": (
            update_story_tool,
            UpdateStoryParams,
            str,
            "Update an existing story's fields. Requires the story sys_id. Only pass fields that need to change.",
            "str",
        ),
        "list_stories": (
            list_stories_tool,
            ListStoriesParams,
            str,
            "List agile stories. Filter by sprint, epic, state, or assigned user sys_id.",
            "json",
        ),
        "list_story_dependencies": (
            list_story_dependencies_tool,
            ListStoryDependenciesParams,
            str,
            "List dependencies (blockers/dependents) for a specific story. Requires the story sys_id.",
            "json",
        ),
        "create_story_dependency": (
            create_story_dependency_tool,
            CreateStoryDependencyParams,
            str,
            "Create a dependency link between two stories. Provide the sys_ids of both the dependent and blocking story.",
            "str",
        ),
        "delete_story_dependency": (
            delete_story_dependency_tool,
            DeleteStoryDependencyParams,
            str,
            "Remove a dependency link between two stories. Requires the dependency record sys_id.",
            "str",
        ),
        # Epic Management Tools
        "create_epic": (
            create_epic_tool,
            CreateEpicParams,
            str,
            "Create a new agile epic in ServiceNow.",
            "str",
        ),
        "update_epic": (
            update_epic_tool,
            UpdateEpicParams,
            str,
            "Update an existing epic's fields. Requires the epic sys_id. Only pass fields that need to change.",
            "str",
        ),
        "list_epics": (
            list_epics_tool,
            ListEpicsParams,
            str,
            "List agile epics. Filter by project, state, or assigned user.",
            "json",
        ),
        # Scrum Task Management Tools
        "create_scrum_task": (
            create_scrum_task_tool,
            CreateScrumTaskParams,
            str,
            "Create a new scrum task linked to a story. Requires the parent story sys_id.",
            "str",
        ),
        "update_scrum_task": (
            update_scrum_task_tool,
            UpdateScrumTaskParams,
            str,
            "Update an existing scrum task. Requires the task sys_id. Only pass fields that need to change.",
            "str",
        ),
        "list_scrum_tasks": (
            list_scrum_tasks_tool,
            ListScrumTasksParams,
            str,
            "List scrum tasks. Filter by parent story, sprint, state, or assigned user.",
            "json",
        ),
        # Project Management Tools
        "create_project": (
            create_project_tool,
            CreateProjectParams,
            str,
            "Create a new project in ServiceNow.",
            "str",
        ),
        "update_project": (
            update_project_tool,
            UpdateProjectParams,
            str,
            "Update an existing project's fields. Requires the project sys_id. Only pass fields that need to change.",
            "str",
        ),
        "list_projects": (
            list_projects_tool,
            ListProjectsParams,
            str,
            "List projects. Filter by state, manager, or use 'query' for name search.",
            "json",
        ),
        # Service Catalog Task (SCTASK) Tools
        "get_sctask": (
            get_sctask_tool,
            GetSCTaskParams,
            str,
            "Get a Service Catalog Task (SCTASK) by number from ServiceNow",
            "json",
        ),
        "list_sctasks": (
            list_sctasks_tool,
            ListSCTasksParams,
            str,
            "List Service Catalog Tasks (SCTASKs) from ServiceNow",
            "json",
        ),
        "update_sctask": (
            update_sctask_tool,
            UpdateSCTaskParams,
            str,
            "Update a Service Catalog Task (SCTASK) in ServiceNow",
            "json",
        ),
        # Time Card Tools
        "list_time_cards": (
            list_time_cards_tool,
            ListTimeCardsParams,
            str,
            "List time cards from ServiceNow, optionally filtered by task or user",
            "json",
        ),
        "create_time_card": (
            create_time_card_tool,
            CreateTimeCardParams,
            str,
            "Create a new time card entry for a task in ServiceNow",
            "json",
        ),
        "update_time_card": (
            update_time_card_tool,
            UpdateTimeCardParams,
            str,
            "Update an existing time card entry in ServiceNow",
            "json",
        ),
        # Syslog Tools
        "list_syslog_entries": (
            list_syslog_entries_tool,
            ListSyslogEntriesParams,
            str,
            "List syslog entries from ServiceNow, with optional filters for level, source, and date range",
            "json",
        ),
        "get_syslog_entry": (
            get_syslog_entry_tool,
            GetSyslogEntryParams,
            str,
            "Retrieve a single syslog entry by its sys_id",
            "json",
        ),
        # Bulk Operations
        "execute_bulk_operations": (
            execute_bulk_operations_tool,
            BulkOperationsParams,
            Dict[str, Any],
            (
                "Execute up to 100 ServiceNow API calls in a single HTTP round-trip "
                "using the ServiceNow Batch API. Each request specifies a method, "
                "relative URL path, and optional body. Results are returned in the "
                "same order with per-request status codes and parsed response bodies."
            ),
            "raw_dict",
        ),
        # UI Policy Tools
        "create_ui_policy": (
            create_ui_policy_tool,
            CreateUIPolicyParams,
            Dict[str, Any],
            "Create a UI policy that controls field behaviour (mandatory/visible/read-only) on a ServiceNow form",
            "dict",
        ),
        "create_ui_policy_action": (
            create_ui_policy_action_tool,
            CreateUIPolicyActionParams,
            Dict[str, Any],
            "Create a UI policy action that sets the mandatory/visible/read-only state of a form field when a UI policy condition fires",
            "dict",
        ),
        # User Criteria Tools
        "create_user_criteria": (
            create_user_criteria_tool,
            CreateUserCriteriaParams,
            Dict[str, Any],
            "Create a User Criteria record that controls who can see or request Service Catalog items based on role, group, department, company, location, or a custom script",
            "dict",
        ),
        # CMDB Tools
        "list_cis": (
            list_cis_tool,
            ListCIsParams,
            Dict[str, Any],
            (
                "List CMDB configuration items (CIs) from ServiceNow with optional "
                "filters for CI class, name, operational status, and environment. "
                "Supports pagination."
            ),
            "raw_dict",
        ),
        "get_ci": (
            get_ci_tool,
            GetCIParams,
            Dict[str, Any],
            "Retrieve a single CMDB configuration item by its sys_id",
            "raw_dict",
        ),
        "create_ci": (
            create_ci_tool,
            CreateCIParams,
            Dict[str, Any],
            (
                "Create a new CMDB configuration item. Specify ci_class to create "
                "in a specific class table (e.g. cmdb_ci_server). Defaults to the "
                "base cmdb_ci table."
            ),
            "raw_dict",
        ),
        "update_ci": (
            update_ci_tool,
            UpdateCIParams,
            Dict[str, Any],
            "Update an existing CMDB configuration item by its sys_id",
            "raw_dict",
        ),
        # Service Portal Widget Tools (sp_widget)
        "create_widget": (
            create_widget_tool,
            CreateWidgetParams,
            WidgetResponse,
            "Create a new Service Portal widget in ServiceNow",
            "raw_pydantic",
        ),
        "update_widget": (
            update_widget_tool,
            UpdateWidgetParams,
            WidgetResponse,
            "Update an existing Service Portal widget in ServiceNow",
            "raw_pydantic",
        ),
        "get_widget": (
            get_widget_tool,
            GetWidgetParams,
            Dict[str, Any],
            "Get Service Portal widget(s) by sys_id (exact) or by name (contains)",
            "raw_dict",
        ),
        # Scripted REST API Tools
        "create_scripted_rest_api": (
            create_scripted_rest_api_tool,
            CreateScriptedRestApiParams,
            ScriptedRestResponse,
            (
                "Create a Scripted REST API service definition (sys_ws_definition). "
                "Returns the namespace + service id; pair with create_scripted_rest_resource "
                "to add operations (HTTP method + relative path + script body)."
            ),
            "raw_pydantic",
        ),
        "create_scripted_rest_resource": (
            create_scripted_rest_resource_tool,
            CreateScriptedRestResourceParams,
            ScriptedRestResponse,
            (
                "Create an operation on an existing Scripted REST API service "
                "(sys_ws_operation). Defines an HTTP method, relative URL path, "
                "and the server-side script body that handles requests."
            ),
            "raw_pydantic",
        ),
        # --- Data Integration Tools (klapom 8c4b817) ---
        "list_import_sets": (
            list_import_sets_tool,
            ListImportSetsParams,
            str,
            "List Import Set table definitions from ServiceNow (sys_import_set_table)",
            "json",
        ),
        "list_data_sources": (
            list_data_sources_tool,
            ListDataSourcesParams,
            str,
            "List configured Data Sources from ServiceNow (sys_data_source)",
            "json",
        ),
        "list_import_runs": (
            list_import_runs_tool,
            ListImportRunsParams,
            str,
            "List Import Set run history with status from ServiceNow (sys_import_set_run)",
            "json",
        ),
        "trigger_import": (
            trigger_import_tool,
            TriggerImportParams,
            str,
            "Trigger an import run for a configured Data Source in ServiceNow",
            "json",
        ),
        "list_transform_maps": (
            list_transform_maps_tool,
            ListTransformMapsParams,
            str,
            "List Transform Maps (sys_transform_map) for a Data Source or Import Set table in ServiceNow",
            "json",
        ),
        "get_transform_map": (
            get_transform_map_tool,
            GetTransformMapParams,
            str,
            "Get full details of a Transform Map including field mappings and transform scripts",
            "json",
        ),
        "list_field_mappings": (
            list_field_mappings_tool,
            ListFieldMappingsParams,
            str,
            "List field mappings (sys_transform_entry) for a Transform Map in ServiceNow",
            "json",
        ),
        "list_transform_scripts": (
            list_transform_scripts_tool,
            ListTransformScriptsParams,
            str,
            "List transform scripts (onBefore, onAfter, onComplete etc.) for a Transform Map",
            "json",
        ),
        "list_scheduled_imports": (
            list_scheduled_imports_tool,
            ListScheduledImportsParams,
            str,
            "List scheduled import jobs (sys_trigger) that trigger Data Sources in ServiceNow",
            "json",
        ),
        "clone_import_configuration": (
            clone_import_configuration_tool,
            CloneImportConfigurationParams,
            str,
            "Clone a complete import configuration: Data Source, Transform Maps, Field Mappings, Scripts, and optionally Scheduler",
            "json",
        ),
        # --- ACL / Role / Security Attribute Tools (PR #56 port) ---
        # Privileged sysadmin tools — added to system_administrator package
        # only. Tools that mutate ACLs/roles can grant/revoke access at the
        # platform level; do not include in service-desk or developer
        # packages without an explicit approval gate.
        "list_acls": (
            list_acls_tool,
            ListACLsParams,
            Dict[str, Any],
            "List Access Control rules (sys_security_acl) with optional filters",
            "raw_dict",
        ),
        "get_acl": (
            get_acl_tool,
            GetACLParams,
            Dict[str, Any],
            "Get a single ACL by sys_id, including assigned roles",
            "raw_dict",
        ),
        "create_acl": (
            create_acl_tool,
            CreateACLParams,
            ACLResponse,
            "Create an Access Control rule. PRIVILEGED: changes the platform's authorization model.",
            "raw_pydantic",
        ),
        "update_acl": (
            update_acl_tool,
            UpdateACLParams,
            ACLResponse,
            "Update an existing ACL. PRIVILEGED: changes the platform's authorization model.",
            "raw_pydantic",
        ),
        "delete_acl": (
            delete_acl_tool,
            DeleteACLParams,
            ACLResponse,
            "Delete an ACL. PRIVILEGED: removing an ACL may permit previously-denied access.",
            "raw_pydantic",
        ),
        "list_roles": (
            list_roles_tool,
            ListRolesParams,
            Dict[str, Any],
            "List ServiceNow roles (sys_user_role) with optional filters",
            "raw_dict",
        ),
        "get_role": (
            get_role_tool,
            GetRoleParams,
            Dict[str, Any],
            "Get a single role by sys_id or name",
            "raw_dict",
        ),
        "create_role": (
            create_role_tool,
            CreateRoleParams,
            ACLResponse,
            "Create a new role. PRIVILEGED.",
            "raw_pydantic",
        ),
        "update_role": (
            update_role_tool,
            UpdateRoleParams,
            ACLResponse,
            "Update an existing role's metadata. PRIVILEGED.",
            "raw_pydantic",
        ),
        "list_security_attributes": (
            list_security_attributes_tool,
            ListSecurityAttributesParams,
            Dict[str, Any],
            "List Security Attributes (sys_security_attribute) used in fine-grained ACL conditions",
            "raw_dict",
        ),
        "create_security_attribute": (
            create_security_attribute_tool,
            CreateSecurityAttributeParams,
            ACLResponse,
            "Create a Security Attribute. PRIVILEGED.",
            "raw_pydantic",
        ),
        # --- Flow Designer Tools (Flowbie port) ---
        "list_trigger_types": (
            list_trigger_types_tool,
            ListTriggerTypesParams,
            ListTriggerTypesResult,
            (
                "List all available Flow Designer trigger types from sys_hub_trigger_type. "
                "Returns the sys_id and name for each trigger type on this instance. "
                "Call this before create_flow to discover valid trigger_definition_id values, "
                "or let create_flow resolve the sys_id automatically from the type string."
            ),
            "json",
        ),
        "create_flow": (
            create_flow_tool,
            CreateFlowParams,
            CreateFlowResponse,
            (
                "Create a new Flow Designer flow in ServiceNow using the internal "
                "/api/now/processflow/ API. Supports flows with a trigger (record-based "
                "or recurrence) and one or more action steps. The flow is created in "
                "draft state and must be activated manually in Flow Designer. "
                "Action inputs require exact parameter definition sys_ids — see the "
                "flow-designer-api.md memory file for known IDs for Look Up Record and "
                "Create Record."
            ),
            "json",
        ),
        "list_flows": (
            list_flows_tool,
            ListFlowsParams,
            dict,
            "List Flow Designer flows from sys_hub_flow with optional filters for type, status, scope, and name",
            "json",
        ),
        "get_flow": (
            get_flow_tool,
            GetFlowParams,
            dict,
            "Get the detail view of a single Flow Designer flow by sys_id",
            "json",
        ),
        "clone_flow": (
            clone_flow_tool,
            CloneFlowParams,
            CloneFlowResponse,
            (
                "Duplicate an existing Flow Designer flow to a new draft flow (new sys_id). "
                "Fetches the source via GET /processflow/flow/{id}, creates a new shell, "
                "copies trigger/action/logic/subflow instances with regenerated ids, then Save. "
                "Use after list_flows/get_flow when reusing an existing design."
            ),
            "json",
        ),
        "update_flow_trigger": (
            update_flow_trigger_tool,
            UpdateFlowTriggerParams,
            UpdateFlowTriggerResponse,
            (
                "Replace the trigger on an existing flow (processflow GET, replace triggerInstances, PUT, Save). "
                "Uses the same TriggerInstanceParam shape as create_flow. "
                "Does not add action or subflow steps."
            ),
            "json",
        ),
        "get_flow_triggers": (
            get_flow_triggers_tool,
            GetFlowTriggersParams,
            dict,
            "Get trigger instances for a flow from sys_hub_trigger_instance (V1) and sys_hub_trigger_instance_v2 (V2), merged. Supports limit/offset pagination.",
            "json",
        ),
        "get_flow_actions": (
            get_flow_actions_tool,
            GetFlowActionsParams,
            dict,
            "Get flow components in list mode (all step types ordered by execution from sys_hub_flow_component) or detail mode (full fields for one component via sys_class_name routing). Provide component_sys_id for detail mode.",
            "json",
        ),
        "get_flow_version": (
            get_flow_version_tool,
            GetFlowVersionParams,
            dict,
            "Get the latest or published version record for a flow from sys_hub_flow_version",
            "json",
        ),
        "update_flow": (
            update_flow_tool,
            UpdateFlowParams,
            MutationResponse,
            "Update a Flow Designer flow.",
            "json",
        ),
        "publish_flow": (
            publish_flow_tool,
            PublishFlowParams,
            dict,
            "Publish (activate) a Flow Designer flow by setting active=true on sys_hub_flow",
            "json",
        ),
        "create_subflow": (
            create_subflow_tool,
            CreateSubflowParams,
            MutationResponse,
            "Create a Flow Designer subflow.",
            "json",
        ),
        "list_subflows": (
            list_subflows_tool,
            ListSubflowsParams,
            ListArtifactsResponse,
            "List Flow Designer subflows.",
            "json",
        ),
        "get_subflow": (
            get_subflow_tool,
            GetSubflowParams,
            GetArtifactResponse,
            "Get a Flow Designer subflow by sys_id.",
            "json",
        ),
        "update_subflow": (
            update_subflow_tool,
            UpdateSubflowParams,
            MutationResponse,
            "Update a Flow Designer subflow.",
            "json",
        ),
        "publish_subflow": (
            publish_subflow_tool,
            PublishSubflowParams,
            MutationResponse,
            "Publish a Flow Designer subflow.",
            "json",
        ),
        "create_action": (
            create_action_tool,
            CreateActionParams,
            MutationResponse,
            "Create a Flow Designer custom action.",
            "json",
        ),
        "list_actions": (
            list_actions_tool,
            ListActionsParams,
            ListArtifactsResponse,
            "List Flow Designer custom actions.",
            "json",
        ),
        "get_action": (
            get_action_tool,
            GetActionParams,
            GetArtifactResponse,
            "Get a Flow Designer custom action by sys_id.",
            "json",
        ),
        "update_action": (
            update_action_tool,
            UpdateActionParams,
            MutationResponse,
            "Update a Flow Designer custom action.",
            "json",
        ),
        "publish_action": (
            publish_action_tool,
            PublishActionParams,
            MutationResponse,
            "Publish a Flow Designer custom action.",
            "json",
        ),
        "list_action_types": (
            list_action_types_tool,
            ListActionTypesParams,
            ListActionTypesResult,
            (
                "Search the action type catalog by name. Returns both definition_sys_id (for list_action_type_inputs) "
                "and base_sys_id (for ActionInstanceParam.action_type_sys_id in add_steps_to_flow/create_flow). "
                "These are different sys_ids — both are required for the full flow authoring workflow."
            ),
            "json",
        ),
        "list_action_type_inputs": (
            list_action_type_inputs_tool,
            ListActionTypeInputsParams,
            ListActionTypeInputsResult,
            (
                "Return all input parameter definitions (sys_ids, types, mandatory flags) for a given action type. "
                "Use this to discover the exact ActionInputParam.id values needed by create_flow and add_steps_to_flow "
                "without hardcoding instance-specific sys_ids."
            ),
            "json",
        ),
        "list_action_type_outputs": (
            list_action_type_outputs_tool,
            ListActionTypeOutputsParams,
            ListActionTypeOutputsResult,
            (
                "List output variable definitions (data pills) for an action type from sys_hub_action_output. "
                "Use definition_sys_id from list_action_types (same as list_action_type_inputs). "
                "Needed to wire action outputs into later step inputs."
            ),
            "json",
        ),
        "delete_flow": (
            delete_flow_tool,
            DeleteFlowParams,
            DeleteArtifactResponse,
            (
                "Delete a Flow Designer flow by sys_id. Irreversible — ensure no dependent "
                "subflows or actions reference this flow before deletion."
            ),
            "json",
        ),
        "delete_subflow": (
            delete_subflow_tool,
            DeleteSubflowParams,
            DeleteArtifactResponse,
            "Delete a Flow Designer subflow by sys_id. Irreversible.",
            "json",
        ),
        "delete_action": (
            delete_action_tool,
            DeleteActionParams,
            DeleteArtifactResponse,
            "Delete a Flow Designer custom action type by sys_id. Irreversible.",
            "json",
        ),
        "execute_flow": (
            execute_flow_tool,
            ExecuteFlowParams,
            ExecuteFlowResponse,
            (
                "Manually execute a flow for testing. Tries POST /processflow/flow/{sys_id}/test "
                "first; falls back to sn_fd.FlowAPI.startFlowAsync via the configured "
                "scripted background-script endpoint when the REST path does not yield "
                "an execution id. Returns an execution context id correlatable with "
                "get_flow_execution_history."
            ),
            "json",
        ),
        "get_flow_execution_history": (
            get_flow_execution_history_tool,
            GetFlowExecutionHistoryParams,
            GetFlowExecutionHistoryResult,
            (
                "Return recent executions of a flow from sys_hub_flow_context with state, "
                "start/end times, and any error message. Useful for debugging flows that "
                "are failing or running unexpectedly."
            ),
            "json",
        ),
        "get_flow_execution_detail": (
            get_flow_execution_detail_tool,
            GetFlowExecutionDetailParams,
            GetFlowExecutionDetailResult,
            (
                "Return detail for a single flow execution including step-level rows from "
                "sys_hub_flow_stage_context when available. Uses the scripted background-script "
                "endpoint because sys_hub_flow_context may be blocked for REST Table API on "
                "some service accounts."
            ),
            "json",
        ),
        "add_steps_to_flow": (
            add_steps_to_flow_tool,
            AddStepsToFlowParams,
            AddStepsToFlowResponse,
            (
                "Append action steps to an existing flow using the GET→mutate→PUT→create_version "
                "pattern. Order values must not clash with existing steps — use get_flow_actions "
                "first to see current orders."
            ),
            "json",
        ),
        "add_subflow_step_to_flow": (
            add_subflow_step_to_flow_tool,
            AddSubflowStepToFlowParams,
            AddSubflowStepToFlowResponse,
            (
                "Add a subflow invocation step to a parent flow. Inputs use "
                "sys_hub_flow_input.sys_id as id (see list_flow_io on the subflow). "
                "Validates that flow_sys_id is type=flow and subflow_sys_id is "
                "type=subflow before mutating."
            ),
            "json",
        ),
        "remove_steps_from_flow": (
            remove_steps_from_flow_tool,
            RemoveStepsFromFlowParams,
            RemoveStepsFromFlowResponse,
            (
                "Remove one or more action, logic, or subflow steps from a flow. Marks steps "
                "with deleted=True across actionInstances/flowLogicInstances/subFlowInstances "
                "then PUTs and creates a version. Use get_flow_actions or processflow GET to "
                "discover current step ids."
            ),
            "json",
        ),
        "add_logic_to_flow": (
            add_logic_to_flow_tool,
            AddLogicToFlowParams,
            AddLogicToFlowResponse,
            (
                "Add a logic step (If, Else, For Each, Do Until, Set Flow Variables) to a flow's "
                "flowLogicInstances array. Use list_flow_logic_types to discover available logic "
                "types. For If/Else/End patterns: add If first, then Else and End with "
                "parent_ui_id=<If_uuid>."
            ),
            "json",
        ),
        "list_flow_logic_types": (
            list_flow_logic_types_tool,
            ListFlowLogicTypesParams,
            ListFlowLogicTypesResult,
            (
                "List all available Flow Designer logic step types (If, Switch, For Each, etc.) "
                "via GET /processflow/flow_logic/types. The sys_id values are the identifiers "
                "needed by add_logic_to_flow."
            ),
            "json",
        ),
        "list_flow_io": (
            list_flow_io_tool,
            ListFlowIOParams,
            ListFlowIOResult,
            (
                "List input and output variable definitions for a flow or subflow from "
                "sys_hub_flow_input and sys_hub_flow_output. Inputs are what the caller must "
                "provide (relevant for subflows); outputs are data the flow makes available "
                "downstream."
            ),
            "json",
        ),
        # Customer Service Case Tools (CSM)
        "list_cases": (
            list_cases_tool,
            ListCasesParams,
            str,
            "List customer service cases from ServiceNow with optional filters",
            "json",
        ),
        "get_case_by_number": (
            get_case_by_number_tool,
            GetCaseByNumberParams,
            str,
            "Get a customer service case by its CS number",
            "json_dict",
        ),
        "search_cases": (
            search_cases_tool,
            SearchCasesParams,
            str,
            "Search customer service cases by text in description fields",
            "json",
        ),
        # CSM Reference Data
        "list_accounts": (
            list_accounts_tool,
            ListAccountsParams,
            str,
            "List customer accounts from ServiceNow (customer_account table)",
            "json",
        ),
        "list_locations": (
            list_locations_tool,
            ListLocationsParams,
            str,
            "List locations from ServiceNow (cmn_location table)",
            "json",
        ),
        "list_products": (
            list_products_tool,
            ListProductsParams,
            str,
            "List sold products from ServiceNow (sn_install_base_sold_product table)",
            "json",
        ),
        # CSM Case Correlation
        "get_cases_by_account": (
            get_cases_by_account_tool,
            GetCasesByAccountParams,
            str,
            "Get customer service cases for a specific account/customer",
            "json",
        ),
        "get_cases_by_location": (
            get_cases_by_location_tool,
            GetCasesByLocationParams,
            str,
            "Get customer service cases for a specific location/venue",
            "json",
        ),
        "get_cases_by_product": (
            get_cases_by_product_tool,
            GetCasesByProductParams,
            str,
            "Get customer service cases filtered by product type",
            "json",
        ),
        "get_cases_by_integration": (
            get_cases_by_integration_tool,
            GetCasesByIntegrationParams,
            str,
            "Get customer service cases involving a specific integration/vendor",
            "json",
        ),
        "get_case_history": (
            get_case_history_tool,
            GetCaseHistoryParams,
            str,
            "Get full comment and work note timeline for a customer service case",
            "json_dict",
        ),
        # --- Generic Table API Tools ---
        "table_get_records": (
            table_get_records_tool,
            TableGetRecordsParams,
            Dict[str, Any],
            "Retrieve multiple records from any ServiceNow table. Supports filtering, pagination, and field selection.",
            "raw_dict",
        ),
        "table_get_record": (
            table_get_record_tool,
            TableGetRecordParams,
            Dict[str, Any],
            "Retrieve a single record by sys_id from any ServiceNow table.",
            "raw_dict",
        ),
        "table_create_record": (
            table_create_record_tool,
            TableCreateRecordParams,
            Dict[str, Any],
            "Create a new record on any ServiceNow table with arbitrary field data.",
            "raw_dict",
        ),
        "table_update_record": (
            table_update_record_tool,
            TableUpdateRecordParams,
            Dict[str, Any],
            "Update an existing record on any ServiceNow table (PATCH with delta payload).",
            "raw_dict",
        ),
        "table_delete_record": (
            table_delete_record_tool,
            TableDeleteRecordParams,
            Dict[str, Any],
            "Delete a record from any ServiceNow table by sys_id.",
            "raw_dict",
        ),
        # --- System Dictionary Tools (Custom Fields) ---
        "create_field": (
            create_field_tool,
            CreateFieldParams,
            Dict[str, Any],
            "Create a new custom field (column) on a ServiceNow table via sys_dictionary.",
            "raw_dict",
        ),
        "list_fields": (
            list_fields_tool,
            ListFieldsParams,
            Dict[str, Any],
            "List field definitions on a ServiceNow table. Filter by name or custom-only.",
            "raw_dict",
        ),
        "update_field": (
            update_field_tool,
            UpdateFieldParams,
            Dict[str, Any],
            "Update an existing field definition (label, mandatory, read_only, etc.) in sys_dictionary.",
            "raw_dict",
        ),
        # --- Business Rule Tools ---
        "create_business_rule": (
            create_business_rule_tool,
            CreateBusinessRuleParams,
            Dict[str, Any],
            "Create a new Business Rule (server-side script) on a ServiceNow table.",
            "raw_dict",
        ),
        "list_business_rules": (
            list_business_rules_tool,
            ListBusinessRulesParams,
            Dict[str, Any],
            "List Business Rules from ServiceNow. Filter by table, name, or active status.",
            "raw_dict",
        ),
        "get_business_rule": (
            get_business_rule_tool,
            GetBusinessRuleParams,
            Dict[str, Any],
            "Get a single Business Rule with full details including script code.",
            "raw_dict",
        ),
        "update_business_rule": (
            update_business_rule_tool,
            UpdateBusinessRuleParams,
            Dict[str, Any],
            "Update an existing Business Rule (script, timing, filters, active flag).",
            "raw_dict",
        ),
        "delete_business_rule": (
            delete_business_rule_tool,
            DeleteBusinessRuleParams,
            Dict[str, Any],
            "Delete a Business Rule from ServiceNow.",
            "raw_dict",
        ),
        # --- Scheduled Job Tools ---
        "create_scheduled_job": (
            create_scheduled_job_tool,
            CreateScheduledJobParams,
            Dict[str, Any],
            "Create a new Scheduled Script Execution (sysauto_script) in ServiceNow.",
            "raw_dict",
        ),
        "list_scheduled_jobs": (
            list_scheduled_jobs_tool,
            ListScheduledJobsParams,
            Dict[str, Any],
            "List Scheduled Script Executions from ServiceNow.",
            "raw_dict",
        ),
        "get_scheduled_job": (
            get_scheduled_job_tool,
            GetScheduledJobParams,
            Dict[str, Any],
            "Get a single Scheduled Job with full details including script code.",
            "raw_dict",
        ),
        "update_scheduled_job": (
            update_scheduled_job_tool,
            UpdateScheduledJobParams,
            Dict[str, Any],
            "Update an existing Scheduled Job (script, schedule, active flag).",
            "raw_dict",
        ),
        "delete_scheduled_job": (
            delete_scheduled_job_tool,
            DeleteScheduledJobParams,
            Dict[str, Any],
            "Delete a Scheduled Job from ServiceNow.",
            "raw_dict",
        ),
        # --- REST Message Tools ---
        "create_rest_message": (
            create_rest_message_tool,
            CreateRestMessageParams,
            Dict[str, Any],
            "Create a new outbound REST Message (sys_rest_message) in ServiceNow.",
            "raw_dict",
        ),
        "list_rest_messages": (
            list_rest_messages_tool,
            ListRestMessagesParams,
            Dict[str, Any],
            "List outbound REST Messages from ServiceNow.",
            "raw_dict",
        ),
        "get_rest_message": (
            get_rest_message_tool,
            GetRestMessageParams,
            Dict[str, Any],
            "Get a single REST Message with full details.",
            "raw_dict",
        ),
        "update_rest_message": (
            update_rest_message_tool,
            UpdateRestMessageParams,
            Dict[str, Any],
            "Update an existing REST Message (endpoint, auth, description).",
            "raw_dict",
        ),
        "delete_rest_message": (
            delete_rest_message_tool,
            DeleteRestMessageParams,
            Dict[str, Any],
            "Delete a REST Message from ServiceNow.",
            "raw_dict",
        ),
        "create_http_method": (
            create_http_method_tool,
            CreateHttpMethodParams,
            Dict[str, Any],
            "Create an HTTP Method (GET/POST/PATCH/etc.) on a REST Message.",
            "raw_dict",
        ),
        "list_http_methods": (
            list_http_methods_tool,
            ListHttpMethodsParams,
            Dict[str, Any],
            "List HTTP Methods defined on a REST Message.",
            "raw_dict",
        ),
        "update_http_method": (
            update_http_method_tool,
            UpdateHttpMethodParams,
            Dict[str, Any],
            "Update an existing HTTP Method on a REST Message.",
            "raw_dict",
        ),
        "delete_http_method": (
            delete_http_method_tool,
            DeleteHttpMethodParams,
            Dict[str, Any],
            "Delete an HTTP Method from a REST Message.",
            "raw_dict",
        ),
        # --- OAuth Credential Tools ---
        "create_oauth_entity": (
            create_oauth_entity_tool,
            CreateOAuthEntityParams,
            Dict[str, Any],
            "Create a new OAuth Entity (Application Registry) in ServiceNow for outbound OAuth2.",
            "raw_dict",
        ),
        "list_oauth_entities": (
            list_oauth_entities_tool,
            ListOAuthEntitiesParams,
            Dict[str, Any],
            "List OAuth Entities (Application Registry) from ServiceNow.",
            "raw_dict",
        ),
        "get_oauth_entity": (
            get_oauth_entity_tool,
            GetOAuthEntityParams,
            Dict[str, Any],
            "Get a single OAuth Entity with full details.",
            "raw_dict",
        ),
        "update_oauth_entity": (
            update_oauth_entity_tool,
            UpdateOAuthEntityParams,
            Dict[str, Any],
            "Update an existing OAuth Entity (client credentials, token URL, etc.).",
            "raw_dict",
        ),
        "delete_oauth_entity": (
            delete_oauth_entity_tool,
            DeleteOAuthEntityParams,
            Dict[str, Any],
            "Delete an OAuth Entity from ServiceNow.",
            "raw_dict",
        ),
        "create_oauth_profile": (
            create_oauth_profile_tool,
            CreateOAuthProfileParams,
            Dict[str, Any],
            "Create an OAuth Entity Profile (credential set with grant type).",
            "raw_dict",
        ),
        "list_oauth_profiles": (
            list_oauth_profiles_tool,
            ListOAuthProfilesParams,
            Dict[str, Any],
            "List OAuth Entity Profiles from ServiceNow.",
            "raw_dict",
        ),
        "update_oauth_profile": (
            update_oauth_profile_tool,
            UpdateOAuthProfileParams,
            Dict[str, Any],
            "Update an existing OAuth Entity Profile.",
            "raw_dict",
        ),
        "delete_oauth_profile": (
            delete_oauth_profile_tool,
            DeleteOAuthProfileParams,
            Dict[str, Any],
            "Delete an OAuth Entity Profile from ServiceNow.",
            "raw_dict",
        ),
        # CMDB Relationship Tools
        "list_ci_relationships": (
            list_ci_relationships_tool,
            ListCIRelationshipsParams,
            Dict[str, Any],
            (
                "List CI relationships from the cmdb_rel_ci table with optional "
                "filters for parent CI, child CI, and relationship type. Supports pagination."
            ),
            "raw_dict",
        ),
        "get_ci_relationship": (
            get_ci_relationship_tool,
            GetCIRelationshipParams,
            Dict[str, Any],
            "Retrieve a single CI relationship record by its sys_id",
            "raw_dict",
        ),
        "create_ci_relationship": (
            create_ci_relationship_tool,
            CreateCIRelationshipParams,
            Dict[str, Any],
            (
                "Create a directional relationship between two CIs in the CMDB. "
                "Requires the sys_id of the parent CI, child CI, and the desired "
                "cmdb_rel_type (use list_ci_relationship_types to find the type sys_id)."
            ),
            "raw_dict",
        ),
        "delete_ci_relationship": (
            delete_ci_relationship_tool,
            DeleteCIRelationshipParams,
            Dict[str, Any],
            "Delete a CI relationship record from the cmdb_rel_ci table by its sys_id",
            "raw_dict",
        ),
        "list_ci_relationship_types": (
            list_ci_relationship_types_tool,
            ListCIRelationshipTypesParams,
            Dict[str, Any],
            (
                "List available CI relationship types from the cmdb_rel_type table. "
                "Each type has a parent_descriptor (e.g. 'Depends on') and a "
                "child_descriptor (e.g. 'Used by'). Filter by name substring."
            ),
            "raw_dict",
        ),
        # Asset Management Tools
        "create_asset": (
            create_asset_tool,
            CreateAssetParams,
            Dict[str, Any],
            (
                "Create a new asset record in the ServiceNow alm_asset table or a subclass "
                "such as alm_hardware. For hardware assets supply asset_class='alm_hardware' "
                "and optionally include CPU, RAM, disk, OS, and network fields."
            ),
            "raw_dict",
        ),
        "list_assets": (
            list_assets_tool,
            ListAssetsParams,
            Dict[str, Any],
            (
                "List hardware and software assets from the ServiceNow alm_asset table "
                "with optional filters for asset tag, display name, install status, "
                "assigned user, and model category. Supports pagination."
            ),
            "raw_dict",
        ),
        "get_asset": (
            get_asset_tool,
            GetAssetParams,
            Dict[str, Any],
            (
                "Retrieve a single asset record from the alm_asset table. "
                "Lookup by sys_id or by asset tag."
            ),
            "raw_dict",
        ),
        "update_asset": (
            update_asset_tool,
            UpdateAssetParams,
            Dict[str, Any],
            (
                "Update an existing asset record in the alm_asset table. "
                "Supports updating status, cost, dates, assignment, and location fields."
            ),
            "raw_dict",
        ),
        "delete_asset": (
            delete_asset_tool,
            DeleteAssetParams,
            Dict[str, Any],
            (
                "Permanently delete an asset record from the alm_asset table by its sys_id. "
                "This action is irreversible — confirm the sys_id before calling."
            ),
            "raw_dict",
        ),
        # Contract Management Tools
        "list_asset_contracts": (
            list_asset_contracts_tool,
            ListAssetContractsParams,
            Dict[str, Any],
            (
                "List asset contracts from the ServiceNow alm_contract table with optional "
                "filters for vendor, state, contract type, description, and date ranges. "
                "Supports pagination."
            ),
            "raw_dict",
        ),
        "get_asset_contract": (
            get_asset_contract_tool,
            GetAssetContractParams,
            Dict[str, Any],
            (
                "Retrieve a single asset contract from the alm_contract table. "
                "Lookup by sys_id or by contract number (e.g. CON0001234)."
            ),
            "raw_dict",
        ),
        "create_asset_contract": (
            create_asset_contract_tool,
            CreateAssetContractParams,
            Dict[str, Any],
            (
                "Create a new contract record in the alm_contract table. "
                "Requires a short_description; optionally accepts vendor, dates, "
                "value, currency, type, category, state, and assignment fields."
            ),
            "raw_dict",
        ),
        "update_asset_contract": (
            update_asset_contract_tool,
            UpdateAssetContractParams,
            Dict[str, Any],
            (
                "Update an existing contract in the alm_contract table by sys_id. "
                "Supply only the fields that need to change."
            ),
            "raw_dict",
        ),
    }
    return tool_definitions

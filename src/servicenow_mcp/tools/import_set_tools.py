"""
Import Set tools for the ServiceNow MCP server.

Provides tools to inspect, manage and clone ServiceNow Import Sets,
Data Sources, Transform Maps, Field Mappings, Transform Scripts and Schedulers.
"""

import logging
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter models
# ---------------------------------------------------------------------------

class ListImportSetsParams(BaseModel):
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")
    query: Optional[str] = Field(None, description="Encoded query string, e.g. 'nameLIKEemployee'")


class ListDataSourcesParams(BaseModel):
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")
    import_set_table: Optional[str] = Field(None, description="Filter by import set table name")
    name_filter: Optional[str] = Field(None, description="Filter by name (contains)")
    query: Optional[str] = Field(None, description="Additional encoded query string")


class ListImportRunsParams(BaseModel):
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")
    import_set_table: Optional[str] = Field(None, description="Filter by import set table name")
    state: Optional[str] = Field(None, description="Filter by state: 'loaded', 'running', 'complete', 'error'")
    query: Optional[str] = Field(None, description="Additional encoded query string")


class TriggerImportParams(BaseModel):
    data_source_sys_id: str = Field(..., description="sys_id of the Data Source (sys_data_source) to trigger")


class ListTransformMapsParams(BaseModel):
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")
    source_table: Optional[str] = Field(None, description="Filter by source staging table name")
    target_table: Optional[str] = Field(None, description="Filter by target table name")
    name_filter: Optional[str] = Field(None, description="Filter by name (contains)")


class GetTransformMapParams(BaseModel):
    transform_map_sys_id: str = Field(..., description="sys_id of the Transform Map (sys_transform_map)")
    include_field_mappings: bool = Field(True, description="Include all field mappings")
    include_scripts: bool = Field(True, description="Include transform scripts (onBefore, onAfter, etc.)")


class ListFieldMappingsParams(BaseModel):
    transform_map_sys_id: str = Field(..., description="sys_id of the Transform Map")
    limit: int = Field(100, description="Maximum number of field mappings to return")


class ListTransformScriptsParams(BaseModel):
    transform_map_sys_id: str = Field(..., description="sys_id of the Transform Map")


class ListScheduledImportsParams(BaseModel):
    limit: int = Field(20, description="Maximum number of records to return")
    data_source_sys_id: Optional[str] = Field(None, description="Filter by Data Source sys_id")
    name_filter: Optional[str] = Field(None, description="Filter by name (contains)")
    active_only: bool = Field(False, description="Only return active schedulers")


class CloneImportConfigurationParams(BaseModel):
    data_source_sys_id: str = Field(..., description="sys_id of the source Data Source to clone")
    new_name_prefix: str = Field(..., description="Prefix for all cloned records (e.g. 'COPY_')")
    new_import_set_table: Optional[str] = Field(
        None, description="New staging table name. If omitted, appends prefix to original."
    )
    clone_scheduler: bool = Field(False, description="Also clone the associated scheduler entry")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_get(
    config: ServerConfig,
    auth_manager: AuthManager,
    table: str,
    params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    url = f"{config.instance_url}/api/now/table/{table}"
    response = requests.get(url, headers=auth_manager.get_headers(), params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("result", [])


def _table_get_one(
    config: ServerConfig,
    auth_manager: AuthManager,
    table: str,
    sys_id: str,
) -> Dict[str, Any]:
    url = f"{config.instance_url}/api/now/table/{table}/{sys_id}"
    response = requests.get(
        url,
        headers=auth_manager.get_headers(),
        params={"sysparm_display_value": "true"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("result", {})


def _table_post(
    config: ServerConfig,
    auth_manager: AuthManager,
    table: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    url = f"{config.instance_url}/api/now/table/{table}"
    response = requests.post(url, headers=auth_manager.get_headers(), json=data, timeout=30)
    response.raise_for_status()
    return response.json().get("result", {})


def _val(record: Dict, field: str) -> str:
    """Resolve display_value or raw value from a field."""
    v = record.get(field, "")
    if isinstance(v, dict):
        return v.get("display_value") or v.get("value") or ""
    return v or ""


def _val_id(record: Dict, field: str) -> str:
    """Resolve the raw sys_id value (not display value) from a reference field."""
    v = record.get(field, "")
    if isinstance(v, dict):
        return v.get("value") or ""
    return v or ""


def _format_record(record: Dict, fields: List[str]) -> Dict[str, Any]:
    return {f: _val(record, f) for f in fields}


# ---------------------------------------------------------------------------
# Existing tools (read)
# ---------------------------------------------------------------------------

def list_import_sets(
    config: ServerConfig, auth_manager: AuthManager, params: ListImportSetsParams
) -> List[Dict[str, Any]]:
    """List recent Import Set instances (sys_import_set), deduplicated by staging table."""
    query_parts = []
    if params.query:
        query_parts.append(params.query)

    api_params: Dict[str, Any] = {
        "sysparm_limit": params.limit,
        "sysparm_offset": params.offset,
        "sysparm_fields": "sys_id,import_set_table_name,state,data_source,sys_created_on",
        "sysparm_display_value": "true",
        "sysparm_query": "ORDERBYDESCsys_created_on",
    }
    if query_parts:
        api_params["sysparm_query"] = "^".join(query_parts) + "^ORDERBYDESCsys_created_on"

    records = _table_get(config, auth_manager, "sys_import_set", api_params)
    seen: set = set()
    result = []
    for r in records:
        rec = _format_record(r, ["sys_id", "import_set_table_name", "state",
                                  "data_source", "sys_created_on"])
        tname = rec.get("import_set_table_name", "")
        if tname and tname not in seen:
            seen.add(tname)
            result.append(rec)
        elif not tname:
            result.append(rec)
    return result


def list_data_sources(
    config: ServerConfig, auth_manager: AuthManager, params: ListDataSourcesParams
) -> List[Dict[str, Any]]:
    """List configured Data Sources (sys_data_source)."""
    query_parts = []
    if params.import_set_table:
        query_parts.append(f"import_set_table_name={params.import_set_table}")
    if params.name_filter:
        query_parts.append(f"nameLIKE{params.name_filter}")
    if params.query:
        query_parts.append(params.query)

    api_params: Dict[str, Any] = {
        "sysparm_limit": params.limit,
        "sysparm_offset": params.offset,
        "sysparm_fields": "sys_id,name,type,import_set_table_name,file_path,file_name,format,active,sys_updated_on",
        "sysparm_display_value": "true",
    }
    if query_parts:
        api_params["sysparm_query"] = "^".join(query_parts)

    records = _table_get(config, auth_manager, "sys_data_source", api_params)
    return [
        _format_record(r, ["sys_id", "name", "type", "import_set_table_name",
                            "file_path", "file_name", "format", "active", "sys_updated_on"])
        for r in records
    ]


def list_import_runs(
    config: ServerConfig, auth_manager: AuthManager, params: ListImportRunsParams
) -> List[Dict[str, Any]]:
    """List Import Set run history (sys_import_set_run), newest first."""
    query_parts = ["ORDERBYDESCsys_created_on"]
    if params.import_set_table:
        query_parts.insert(0, f"import_set_table_name={params.import_set_table}")
    if params.state:
        query_parts.insert(0, f"state={params.state}")
    if params.query:
        query_parts.insert(0, params.query)

    api_params: Dict[str, Any] = {
        "sysparm_limit": params.limit,
        "sysparm_offset": params.offset,
        "sysparm_fields": "sys_id,set,sys_transform_map,state,inserts,updates,ignored,errors,total,completed,run_time,sys_created_on",
        "sysparm_display_value": "true",
        "sysparm_query": "^".join(query_parts),
    }

    records = _table_get(config, auth_manager, "sys_import_set_run", api_params)
    return [
        _format_record(r, ["sys_id", "set", "sys_transform_map", "state",
                            "inserts", "updates", "ignored", "errors", "total",
                            "completed", "run_time", "sys_created_on"])
        for r in records
    ]


def trigger_import(
    config: ServerConfig, auth_manager: AuthManager, params: TriggerImportParams
) -> Dict[str, Any]:
    """Trigger an import run for a given Data Source."""
    url_ds = f"{config.instance_url}/api/now/table/sys_data_source/{params.data_source_sys_id}"
    headers = auth_manager.get_headers()
    resp = requests.get(url_ds, headers=headers, timeout=30)
    resp.raise_for_status()
    ds = resp.json().get("result", {})
    table_name = _val(ds, "import_set_table_name")
    if not table_name:
        return {"error": "Could not determine import set table from data source."}

    url_import = f"{config.instance_url}/api/now/import/{table_name}"
    resp2 = requests.post(url_import, headers=headers, json={}, timeout=60)
    resp2.raise_for_status()
    return {
        "status": "triggered",
        "import_set_table": table_name,
        "data_source_sys_id": params.data_source_sys_id,
        "response": resp2.json(),
    }


# ---------------------------------------------------------------------------
# New tools — Transform Maps, Field Mappings, Scripts, Scheduler
# ---------------------------------------------------------------------------

def list_transform_maps(
    config: ServerConfig, auth_manager: AuthManager, params: ListTransformMapsParams
) -> List[Dict[str, Any]]:
    """
    List Transform Maps (sys_transform_map).
    Each map connects a staging table to a target table and contains field mappings + scripts.
    """
    query_parts = ["active=true"]
    if params.source_table:
        query_parts.append(f"source_table={params.source_table}")
    if params.target_table:
        query_parts.append(f"target_table={params.target_table}")
    if params.name_filter:
        query_parts.append(f"nameLIKE{params.name_filter}")

    api_params: Dict[str, Any] = {
        "sysparm_limit": params.limit,
        "sysparm_offset": params.offset,
        "sysparm_fields": "sys_id,name,source_table,target_table,active,run_script,order,sys_updated_on",
        "sysparm_display_value": "true",
        "sysparm_query": "^".join(query_parts),
    }
    records = _table_get(config, auth_manager, "sys_transform_map", api_params)
    return [
        _format_record(r, ["sys_id", "name", "source_table", "target_table",
                            "active", "run_script", "order", "sys_updated_on"])
        for r in records
    ]


def get_transform_map(
    config: ServerConfig, auth_manager: AuthManager, params: GetTransformMapParams
) -> Dict[str, Any]:
    """
    Get full details of a Transform Map including field mappings and scripts.
    Returns the map config, all field mappings (source→target, coalesce, scripts),
    and all event scripts (onBefore, onAfter, onComplete, etc.).
    """
    map_rec = _table_get_one(config, auth_manager, "sys_transform_map", params.transform_map_sys_id)
    result: Dict[str, Any] = {
        "transform_map": _format_record(map_rec, [
            "sys_id", "name", "source_table", "target_table", "active",
            "run_script", "script", "copy_empty_fields", "enforce_mandatory_fields",
            "run_business_rules", "order", "sys_updated_on",
        ])
    }

    if params.include_field_mappings:
        fm_params = ListFieldMappingsParams(transform_map_sys_id=params.transform_map_sys_id)
        result["field_mappings"] = list_field_mappings(config, auth_manager, fm_params)

    if params.include_scripts:
        sc_params = ListTransformScriptsParams(transform_map_sys_id=params.transform_map_sys_id)
        result["transform_scripts"] = list_transform_scripts(config, auth_manager, sc_params)

    return result


def list_field_mappings(
    config: ServerConfig, auth_manager: AuthManager, params: ListFieldMappingsParams
) -> List[Dict[str, Any]]:
    """
    List all field mappings (sys_transform_entry) for a Transform Map.
    Shows source field → target field, coalesce flag, and any field-level scripts.
    """
    api_params: Dict[str, Any] = {
        "sysparm_limit": params.limit,
        "sysparm_offset": 0,
        "sysparm_fields": (
            "sys_id,map,source_field,target_field,source_table,target_table,"
            "coalesce,coalesce_case_sensitive,coalesce_empty_fields,"
            "use_source_script,source_script,choice_action,date_format,"
            "reference_value_field"
        ),
        "sysparm_display_value": "true",
        "sysparm_query": f"map={params.transform_map_sys_id}^ORDERBYtarget_field",
    }
    records = _table_get(config, auth_manager, "sys_transform_entry", api_params)
    return [
        _format_record(r, [
            "sys_id", "source_field", "target_field", "coalesce",
            "coalesce_case_sensitive", "coalesce_empty_fields",
            "use_source_script", "source_script", "choice_action",
            "date_format", "reference_value_field",
        ])
        for r in records
    ]


def list_transform_scripts(
    config: ServerConfig, auth_manager: AuthManager, params: ListTransformScriptsParams
) -> List[Dict[str, Any]]:
    """
    List all Transform Scripts (sys_transform_script) for a Transform Map.
    Scripts handle events: onBefore, onAfter, onComplete, onForeignInsert, onStart.
    Returns the event type (when), active status and the full script code.
    """
    api_params: Dict[str, Any] = {
        "sysparm_limit": 50,
        "sysparm_offset": 0,
        "sysparm_fields": "sys_id,map,when,active,script,order,sys_updated_on",
        "sysparm_display_value": "true",
        "sysparm_query": f"map={params.transform_map_sys_id}^ORDERBYorder",
    }
    records = _table_get(config, auth_manager, "sys_transform_script", api_params)
    return [
        _format_record(r, ["sys_id", "when", "active", "script", "order", "sys_updated_on"])
        for r in records
    ]


def list_scheduled_imports(
    config: ServerConfig, auth_manager: AuthManager, params: ListScheduledImportsParams
) -> List[Dict[str, Any]]:
    """
    List scheduled jobs (sys_trigger) that trigger Data Source imports.
    Returns name, schedule (next_action, run_time), state and the trigger script.
    """
    query_parts = ["trigger_type=0"]  # type 0 = scheduled
    if params.data_source_sys_id:
        query_parts.append(f"document_key={params.data_source_sys_id}")
    if params.name_filter:
        query_parts.append(f"nameLIKE{params.name_filter}")
    if params.active_only:
        query_parts.append("state=0")  # 0 = waiting/active

    api_params: Dict[str, Any] = {
        "sysparm_limit": params.limit,
        "sysparm_offset": 0,
        "sysparm_fields": (
            "sys_id,name,state,next_action,run_time,run_dayofweek,run_weekinmonth,"
            "run_month,time_zone,document,document_key,script,sys_updated_on"
        ),
        "sysparm_display_value": "true",
        "sysparm_query": "^".join(query_parts),
    }
    records = _table_get(config, auth_manager, "sys_trigger", api_params)
    return [
        _format_record(r, [
            "sys_id", "name", "state", "next_action", "run_time",
            "run_dayofweek", "run_weekinmonth", "run_month", "time_zone",
            "document", "document_key", "script", "sys_updated_on",
        ])
        for r in records
    ]


def clone_import_configuration(
    config: ServerConfig, auth_manager: AuthManager, params: CloneImportConfigurationParams
) -> Dict[str, Any]:
    """
    Clone a complete Import Set configuration:
    1. Data Source (sys_data_source)
    2. All Transform Maps for the source staging table (sys_transform_map)
    3. All Field Mappings per map (sys_transform_entry)
    4. All Transform Scripts per map (sys_transform_script)
    5. Optionally: Scheduler (sys_trigger)

    Returns sys_ids of all created records.
    """
    headers = auth_manager.get_headers()
    prefix = params.new_name_prefix
    created: Dict[str, Any] = {
        "data_source": None,
        "transform_maps": [],
        "field_mappings_total": 0,
        "transform_scripts_total": 0,
        "scheduler": None,
    }

    # 1. Clone Data Source
    ds_url = f"{config.instance_url}/api/now/table/sys_data_source/{params.data_source_sys_id}"
    ds_resp = requests.get(ds_url, headers=headers, timeout=30)
    ds_resp.raise_for_status()
    ds = ds_resp.json().get("result", {})

    old_table = _val(ds, "import_set_table_name")
    new_table = params.new_import_set_table or f"{prefix}{old_table}".lower()[:40]

    new_ds_data = {
        "name": f"{prefix}{_val(ds, 'name')}"[:80],
        "type": _val_id(ds, "type") or _val(ds, "type"),
        "import_set_table_name": new_table,
        "file_path": _val(ds, "file_path"),
        "file_name": _val(ds, "file_name"),
        "format": _val_id(ds, "format") or _val(ds, "format"),
        "active": "false",  # start inactive for safety
    }
    new_ds = _table_post(config, auth_manager, "sys_data_source", new_ds_data)
    new_ds_id = new_ds.get("sys_id", "")
    created["data_source"] = {"sys_id": new_ds_id, "name": new_ds_data["name"], "table": new_table}

    # 2. Find Transform Maps for the original staging table
    tm_api_params = {
        "sysparm_query": f"source_table={old_table}",
        "sysparm_fields": "sys_id,name,source_table,target_table,active,run_script,script,"
                          "copy_empty_fields,enforce_mandatory_fields,run_business_rules,order",
        "sysparm_display_value": "true",
        "sysparm_limit": 50,
    }
    transform_maps = _table_get(config, auth_manager, "sys_transform_map", tm_api_params)

    for tm in transform_maps:
        old_tm_id = _val_id(tm, "sys_id") or tm.get("sys_id", "")

        new_tm_data = {
            "name": f"{prefix}{_val(tm, 'name')}"[:80],
            "source_table": new_table,
            "target_table": _val(tm, "target_table"),
            "active": "false",
            "run_script": _val(tm, "run_script"),
            "script": _val(tm, "script"),
            "copy_empty_fields": _val(tm, "copy_empty_fields"),
            "enforce_mandatory_fields": _val(tm, "enforce_mandatory_fields"),
            "run_business_rules": _val(tm, "run_business_rules"),
            "order": _val(tm, "order") or "100",
        }
        new_tm = _table_post(config, auth_manager, "sys_transform_map", new_tm_data)
        new_tm_id = new_tm.get("sys_id", "")
        tm_entry: Dict[str, Any] = {
            "sys_id": new_tm_id,
            "name": new_tm_data["name"],
            "field_mappings": [],
            "transform_scripts": [],
        }

        # 3. Clone Field Mappings
        fm_params_api = {
            "sysparm_query": f"map={old_tm_id}",
            "sysparm_fields": (
                "source_field,target_field,source_table,target_table,coalesce,"
                "coalesce_case_sensitive,coalesce_empty_fields,use_source_script,"
                "source_script,choice_action,date_format,reference_value_field"
            ),
            "sysparm_display_value": "true",
            "sysparm_limit": 200,
        }
        field_mappings = _table_get(config, auth_manager, "sys_transform_entry", fm_params_api)
        for fm in field_mappings:
            new_fm_data = {
                "map": new_tm_id,
                "source_field": _val(fm, "source_field"),
                "target_field": _val(fm, "target_field"),
                "source_table": new_table,
                "target_table": _val(tm, "target_table"),
                "coalesce": _val(fm, "coalesce"),
                "coalesce_case_sensitive": _val(fm, "coalesce_case_sensitive"),
                "coalesce_empty_fields": _val(fm, "coalesce_empty_fields"),
                "use_source_script": _val(fm, "use_source_script"),
                "source_script": _val(fm, "source_script"),
                "choice_action": _val(fm, "choice_action"),
                "date_format": _val(fm, "date_format"),
                "reference_value_field": _val(fm, "reference_value_field"),
            }
            new_fm = _table_post(config, auth_manager, "sys_transform_entry", new_fm_data)
            tm_entry["field_mappings"].append(new_fm.get("sys_id", ""))
            created["field_mappings_total"] += 1

        # 4. Clone Transform Scripts (onBefore, onAfter, onComplete, etc.)
        sc_params_api = {
            "sysparm_query": f"map={old_tm_id}",
            "sysparm_fields": "when,active,script,order",
            "sysparm_display_value": "true",
            "sysparm_limit": 50,
        }
        scripts = _table_get(config, auth_manager, "sys_transform_script", sc_params_api)
        for sc in scripts:
            new_sc_data = {
                "map": new_tm_id,
                "when": _val(sc, "when"),
                "active": _val(sc, "active"),
                "script": _val(sc, "script"),
                "order": _val(sc, "order") or "100",
            }
            new_sc = _table_post(config, auth_manager, "sys_transform_script", new_sc_data)
            tm_entry["transform_scripts"].append(new_sc.get("sys_id", ""))
            created["transform_scripts_total"] += 1

        created["transform_maps"].append(tm_entry)

    # 5. Optionally clone Scheduler
    if params.clone_scheduler:
        sched_params_api = {
            "sysparm_query": f"document_key={params.data_source_sys_id}^trigger_type=0",
            "sysparm_fields": "name,state,run_time,run_dayofweek,run_weekinmonth,run_month,time_zone,script",
            "sysparm_display_value": "true",
            "sysparm_limit": 5,
        }
        schedulers = _table_get(config, auth_manager, "sys_trigger", sched_params_api)
        cloned_scheds = []
        for sched in schedulers:
            new_sched_data = {
                "name": f"{prefix}{_val(sched, 'name')}"[:80],
                "document": "sys_data_source",
                "document_key": new_ds_id,
                "trigger_type": "0",
                "state": "2",  # 2 = inactive for safety
                "run_time": _val(sched, "run_time"),
                "run_dayofweek": _val(sched, "run_dayofweek"),
                "run_weekinmonth": _val(sched, "run_weekinmonth"),
                "run_month": _val(sched, "run_month"),
                "time_zone": _val(sched, "time_zone"),
                "script": _val(sched, "script"),
            }
            new_sched = _table_post(config, auth_manager, "sys_trigger", new_sched_data)
            cloned_scheds.append({"sys_id": new_sched.get("sys_id", ""), "name": new_sched_data["name"]})
        created["scheduler"] = cloned_scheds

    created["summary"] = (
        f"Cloned: 1 Data Source → '{new_ds_data['name']}' (table: {new_table}), "
        f"{len(created['transform_maps'])} Transform Map(s), "
        f"{created['field_mappings_total']} Field Mapping(s), "
        f"{created['transform_scripts_total']} Script(s). "
        f"All records created as INACTIVE — activate manually after review."
    )
    return created

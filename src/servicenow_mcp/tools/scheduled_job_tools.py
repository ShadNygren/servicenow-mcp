"""
Scheduled Job tools for the ServiceNow MCP server.

Provides tools to create, list, update, and delete Scheduled Script Executions
(sysauto_script) in ServiceNow. Used for recurring tasks like nightly imports
and daily reconciliation jobs.
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


class CreateScheduledJobParams(BaseModel):
    """Parameters for creating a new Scheduled Script Execution."""

    name: str = Field(..., description="Name of the scheduled job")
    script: str = Field(
        ...,
        description="Server-side JavaScript to execute on schedule",
    )
    run_type: str = Field(
        "daily",
        description="Schedule type: 'daily', 'weekly', 'monthly', 'periodically', 'once', 'on_demand'",
    )
    time_of_day: Optional[str] = Field(
        None,
        description="Time to run in HH:MM:SS format (24h), e.g. '02:00:00'. Used for daily/weekly/monthly.",
    )
    day_of_week: Optional[str] = Field(
        None,
        description="Day of week for weekly jobs: 'monday', 'tuesday', ..., 'sunday'",
    )
    day_of_month: Optional[int] = Field(
        None, description="Day of month for monthly jobs (1-31)"
    )
    run_period: Optional[str] = Field(
        None,
        description="Interval for 'periodically' type, e.g. '00:05:00' for every 5 minutes",
    )
    run_start: Optional[str] = Field(
        None,
        description="Start date/time in 'YYYY-MM-DD HH:MM:SS' format",
    )
    active: bool = Field(True, description="Whether the job is active")
    description: Optional[str] = Field(
        None, description="Description of what the job does"
    )
    conditional: bool = Field(
        False, description="Whether the job has a conditional script"
    )
    condition_script: Optional[str] = Field(
        None,
        description="Condition script — job only runs when this returns true",
    )


class ListScheduledJobsParams(BaseModel):
    """Parameters for listing Scheduled Script Executions."""

    name_filter: Optional[str] = Field(
        None, description="Filter by name (contains)"
    )
    active_only: bool = Field(
        True, description="Only return active jobs (default: true)"
    )
    run_type: Optional[str] = Field(
        None, description="Filter by run type: 'daily', 'weekly', etc."
    )
    query: Optional[str] = Field(
        None, description="Additional encoded query string"
    )
    limit: int = Field(20, description="Maximum number of records to return")
    offset: int = Field(0, description="Offset for pagination")


class GetScheduledJobParams(BaseModel):
    """Parameters for getting a single Scheduled Job."""

    sys_id: str = Field(..., description="sys_id of the scheduled job")


class UpdateScheduledJobParams(BaseModel):
    """Parameters for updating an existing Scheduled Job."""

    sys_id: str = Field(..., description="sys_id of the scheduled job to update")
    name: Optional[str] = Field(None, description="New name")
    script: Optional[str] = Field(None, description="New script")
    run_type: Optional[str] = Field(None, description="New run type")
    time_of_day: Optional[str] = Field(None, description="New time of day (HH:MM:SS)")
    day_of_week: Optional[str] = Field(None, description="New day of week")
    day_of_month: Optional[int] = Field(None, description="New day of month")
    run_period: Optional[str] = Field(None, description="New run period")
    run_start: Optional[str] = Field(None, description="New start date/time")
    active: Optional[bool] = Field(None, description="Set active flag")
    description: Optional[str] = Field(None, description="New description")
    conditional: Optional[bool] = Field(None, description="Set conditional flag")
    condition_script: Optional[str] = Field(None, description="New condition script")


class DeleteScheduledJobParams(BaseModel):
    """Parameters for deleting a Scheduled Job."""

    sys_id: str = Field(..., description="sys_id of the scheduled job to delete")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def create_scheduled_job(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateScheduledJobParams,
) -> Dict[str, Any]:
    """Create a new Scheduled Script Execution in ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sysauto_script"

    data: Dict[str, Any] = {
        "name": params.name,
        "script": params.script,
        "run_type": params.run_type,
        "active": str(params.active).lower(),
    }

    if params.time_of_day:
        data["run_time"] = params.time_of_day
    if params.day_of_week:
        data["run_dayofweek"] = params.day_of_week
    if params.day_of_month is not None:
        data["run_dayofmonth"] = str(params.day_of_month)
    if params.run_period:
        data["run_period"] = params.run_period
    if params.run_start:
        data["run_start"] = params.run_start
    if params.description:
        data["comments"] = params.description
    if params.conditional:
        data["conditional"] = str(params.conditional).lower()
    if params.condition_script:
        data["condition"] = params.condition_script

    try:
        response = requests.post(
            url,
            headers=auth_manager.get_headers(),
            json=data,
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Created scheduled job '{params.name}'",
            "sys_id": result.get("sys_id"),
            "name": params.name,
            "run_type": params.run_type,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to create scheduled job '{params.name}': {e}")
        return {
            "success": False,
            "message": f"Failed to create scheduled job: {str(e)}",
            "sys_id": None,
            "name": params.name,
            "record": {},
        }


def list_scheduled_jobs(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListScheduledJobsParams,
) -> Dict[str, Any]:
    """List Scheduled Script Executions from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sysauto_script"

    query_parts: List[str] = []
    if params.name_filter:
        query_parts.append(f"nameLIKE{params.name_filter}")
    if params.active_only:
        query_parts.append("active=true")
    if params.run_type:
        query_parts.append(f"run_type={params.run_type}")
    if params.query:
        query_parts.append(params.query)

    query_params = {
        "sysparm_query": "^".join(query_parts) if query_parts else "",
        "sysparm_fields": "sys_id,name,run_type,run_time,run_dayofweek,run_dayofmonth,run_period,run_start,active,sys_updated_on",
        "sysparm_limit": str(params.limit),
        "sysparm_offset": str(params.offset),
    }

    try:
        response = requests.get(
            url,
            headers=auth_manager.get_headers(),
            params=query_params,
            timeout=config.timeout,
        )
        response.raise_for_status()
        records = response.json().get("result", [])
        jobs = []
        for r in records:
            jobs.append({
                "sys_id": r.get("sys_id"),
                "name": r.get("name"),
                "run_type": r.get("run_type"),
                "time_of_day": r.get("run_time"),
                "day_of_week": r.get("run_dayofweek"),
                "day_of_month": r.get("run_dayofmonth"),
                "run_period": r.get("run_period"),
                "run_start": r.get("run_start"),
                "active": r.get("active"),
                "updated_on": r.get("sys_updated_on"),
            })
        return {
            "success": True,
            "message": f"Found {len(jobs)} scheduled jobs",
            "count": len(jobs),
            "jobs": jobs,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to list scheduled jobs: {e}")
        return {
            "success": False,
            "message": f"Failed to list scheduled jobs: {str(e)}",
            "count": 0,
            "jobs": [],
        }


def get_scheduled_job(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetScheduledJobParams,
) -> Dict[str, Any]:
    """Get a single Scheduled Job with full details including script."""
    url = f"{config.instance_url}/api/now/table/sysauto_script/{params.sys_id}"

    try:
        response = requests.get(
            url,
            headers=auth_manager.get_headers(),
            params={"sysparm_display_value": "false"},
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Retrieved scheduled job '{result.get('name', params.sys_id)}'",
            "job": {
                "sys_id": result.get("sys_id"),
                "name": result.get("name"),
                "script": result.get("script"),
                "run_type": result.get("run_type"),
                "time_of_day": result.get("run_time"),
                "day_of_week": result.get("run_dayofweek"),
                "day_of_month": result.get("run_dayofmonth"),
                "run_period": result.get("run_period"),
                "run_start": result.get("run_start"),
                "active": result.get("active"),
                "conditional": result.get("conditional"),
                "condition_script": result.get("condition"),
                "description": result.get("comments"),
                "updated_on": result.get("sys_updated_on"),
            },
        }
    except requests.RequestException as e:
        logger.error(f"Failed to get scheduled job {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to get scheduled job: {str(e)}",
            "job": {},
        }


def update_scheduled_job(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateScheduledJobParams,
) -> Dict[str, Any]:
    """Update an existing Scheduled Job."""
    url = f"{config.instance_url}/api/now/table/sysauto_script/{params.sys_id}"

    data: Dict[str, Any] = {}
    if params.name is not None:
        data["name"] = params.name
    if params.script is not None:
        data["script"] = params.script
    if params.run_type is not None:
        data["run_type"] = params.run_type
    if params.time_of_day is not None:
        data["run_time"] = params.time_of_day
    if params.day_of_week is not None:
        data["run_dayofweek"] = params.day_of_week
    if params.day_of_month is not None:
        data["run_dayofmonth"] = str(params.day_of_month)
    if params.run_period is not None:
        data["run_period"] = params.run_period
    if params.run_start is not None:
        data["run_start"] = params.run_start
    if params.active is not None:
        data["active"] = str(params.active).lower()
    if params.description is not None:
        data["comments"] = params.description
    if params.conditional is not None:
        data["conditional"] = str(params.conditional).lower()
    if params.condition_script is not None:
        data["condition"] = params.condition_script

    if not data:
        return {
            "success": False,
            "message": "No fields to update.",
            "sys_id": params.sys_id,
            "record": {},
        }

    try:
        response = requests.patch(
            url,
            headers=auth_manager.get_headers(),
            json=data,
            timeout=config.timeout,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "success": True,
            "message": f"Updated scheduled job {params.sys_id}",
            "sys_id": params.sys_id,
            "record": result,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to update scheduled job {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to update scheduled job: {str(e)}",
            "sys_id": params.sys_id,
            "record": {},
        }


def delete_scheduled_job(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: DeleteScheduledJobParams,
) -> Dict[str, Any]:
    """Delete a Scheduled Job from ServiceNow."""
    url = f"{config.instance_url}/api/now/table/sysauto_script/{params.sys_id}"

    try:
        response = requests.delete(
            url,
            headers=auth_manager.get_headers(),
            timeout=config.timeout,
        )
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Deleted scheduled job {params.sys_id}",
            "sys_id": params.sys_id,
        }
    except requests.RequestException as e:
        logger.error(f"Failed to delete scheduled job {params.sys_id}: {e}")
        return {
            "success": False,
            "message": f"Failed to delete scheduled job: {str(e)}",
            "sys_id": params.sys_id,
        }

"""
Incident tools for the ServiceNow MCP server.

This module provides tools for managing incidents in ServiceNow.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.async_http import get_async_client
from servicenow_mcp.utils.config import ServerConfig
from servicenow_mcp.utils.helpers import (
    _build_sysparm_params,
    _join_query_parts,
    _paginated_list_response,
)

logger = logging.getLogger(__name__)


class CreateIncidentParams(BaseModel):
    """Parameters for creating an incident."""

    short_description: str = Field(..., description="Short description of the incident")
    description: Optional[str] = Field(None, description="Detailed description of the incident")
    caller_id: Optional[str] = Field(None, description="User who reported the incident")
    category: Optional[str] = Field(None, description="Category of the incident")
    subcategory: Optional[str] = Field(None, description="Subcategory of the incident")
    priority: Optional[str] = Field(None, description="Priority of the incident")
    impact: Optional[str] = Field(None, description="Impact of the incident")
    urgency: Optional[str] = Field(None, description="Urgency of the incident")
    assigned_to: Optional[str] = Field(None, description="User assigned to the incident")
    assignment_group: Optional[str] = Field(None, description="Group assigned to the incident")


class UpdateIncidentParams(BaseModel):
    """Parameters for updating an incident."""

    incident_id: str = Field(..., description="Incident ID or sys_id")
    short_description: Optional[str] = Field(None, description="Short description of the incident")
    description: Optional[str] = Field(None, description="Detailed description of the incident")
    state: Optional[str] = Field(None, description="State of the incident")
    category: Optional[str] = Field(None, description="Category of the incident")
    subcategory: Optional[str] = Field(None, description="Subcategory of the incident")
    priority: Optional[str] = Field(None, description="Priority of the incident")
    impact: Optional[str] = Field(None, description="Impact of the incident")
    urgency: Optional[str] = Field(None, description="Urgency of the incident")
    assigned_to: Optional[str] = Field(None, description="User assigned to the incident")
    assignment_group: Optional[str] = Field(None, description="Group assigned to the incident")
    work_notes: Optional[str] = Field(None, description="Work notes to add to the incident")
    close_notes: Optional[str] = Field(None, description="Close notes to add to the incident")
    close_code: Optional[str] = Field(None, description="Close code for the incident")


class AddCommentParams(BaseModel):
    """Parameters for adding a comment to an incident."""

    incident_id: str = Field(..., description="Incident ID or sys_id")
    comment: str = Field(..., description="Comment to add to the incident")
    is_work_note: bool = Field(False, description="Whether the comment is a work note")


class ResolveIncidentParams(BaseModel):
    """Parameters for resolving an incident."""

    incident_id: str = Field(..., description="Incident ID or sys_id")
    resolution_code: str = Field(..., description="Resolution code for the incident")
    resolution_notes: str = Field(..., description="Resolution notes for the incident")


class ListIncidentsParams(BaseModel):
    """Parameters for listing incidents."""

    limit: int = Field(10, description="Maximum number of incidents to return")
    offset: int = Field(0, description="Offset for pagination")
    state: Optional[str] = Field(None, description="Filter by incident state")
    assigned_to: Optional[str] = Field(None, description="Filter by assigned user (sys_id or username)")
    assignment_group: Optional[str] = Field(
        None,
        description="Filter by assignment group name (matches assignment_group.name)",
    )
    category: Optional[str] = Field(None, description="Filter by category")
    query: Optional[str] = Field(None, description="Search query for incidents")
    updated_on_after: Optional[str] = Field(
        None,
        description="Filter by updated-on time: return incidents updated on or after this time (format: YYYY-MM-DD or YYYY-MM-DD HH:mm:ss)",
    )
    updated_on_before: Optional[str] = Field(
        None,
        description="Filter by updated-on time: return incidents updated on or before this time (format: YYYY-MM-DD or YYYY-MM-DD HH:mm:ss)",
    )
    opened_after: Optional[str] = Field(
        None,
        description="Filter by opened-at time: return incidents opened on or after this time (format: YYYY-MM-DD or YYYY-MM-DD HH:mm:ss)",
    )
    opened_before: Optional[str] = Field(
        None,
        description="Filter by opened-at time: return incidents opened on or before this time (format: YYYY-MM-DD or YYYY-MM-DD HH:mm:ss)",
    )


class GetIncidentByNumberParams(BaseModel):
    """Parameters for fetching an incident by its number."""

    incident_number: str = Field(..., description="The number of the incident to fetch")


class GetIncidentJournalParams(BaseModel):
    """Parameters for fetching an incident's journal (work_notes + comments)."""

    incident_number: str = Field(..., description="The incident number, e.g. 'INC0010001'")
    fields: Optional[List[str]] = Field(
        default=None,
        description=(
            "Journal fields to include. Defaults to ['work_notes', 'comments']. "
            "Pass ['work_notes'] for internal-only or ['comments'] for "
            "customer-visible only."
        ),
    )
    limit: int = Field(
        100,
        description="Maximum number of journal entries to return (default 100)",
    )


class IncidentResponse(BaseModel):
    """Response from incident operations."""

    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Message describing the result")
    incident_id: Optional[str] = Field(None, description="ID of the affected incident")
    incident_number: Optional[str] = Field(None, description="Number of the affected incident")


async def create_incident(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: CreateIncidentParams,
) -> IncidentResponse:
    """
    Create a new incident in ServiceNow.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters for creating the incident.

    Returns:
        Response with the created incident details.
    """
    api_url = f"{config.api_url}/table/incident"

    # Build request data
    data: Dict[str, Any] = {
        "short_description": params.short_description,
    }

    if params.description:
        data["description"] = params.description
    if params.caller_id:
        data["caller_id"] = params.caller_id
    if params.category:
        data["category"] = params.category
    if params.subcategory:
        data["subcategory"] = params.subcategory
    if params.priority:
        data["priority"] = params.priority
    if params.impact:
        data["impact"] = params.impact
    if params.urgency:
        data["urgency"] = params.urgency
    if params.assigned_to:
        data["assigned_to"] = params.assigned_to
    if params.assignment_group:
        data["assignment_group"] = params.assignment_group

    # Make request
    try:
        client = await get_async_client()
        response = await client.post(
            api_url,
            json=data,
            headers=await auth_manager.get_headers_async(),
            timeout=config.timeout,
        )
        response.raise_for_status()

        result = response.json().get("result", {})

        return IncidentResponse(
            success=True,
            message="Incident created successfully",
            incident_id=result.get("sys_id"),
            incident_number=result.get("number"),
        )

    except httpx.HTTPError as e:
        logger.error(f"Failed to create incident: {e}")
        return IncidentResponse(
            success=False,
            message=f"Failed to create incident: {str(e)}",
        )


async def update_incident(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: UpdateIncidentParams,
) -> IncidentResponse:
    """
    Update an existing incident in ServiceNow.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters for updating the incident.

    Returns:
        Response with the updated incident details.
    """
    # Determine if incident_id is a number or sys_id
    incident_id = params.incident_id
    if len(incident_id) == 32 and all(c in "0123456789abcdef" for c in incident_id):
        # This is likely a sys_id
        api_url = f"{config.api_url}/table/incident/{incident_id}"
    else:
        # This is likely an incident number
        # First, we need to get the sys_id
        try:
            query_url = f"{config.api_url}/table/incident"
            query_params: Dict[str, Any] = {
                "sysparm_query": f"number={incident_id}",
                "sysparm_limit": 1,
            }

            client = await get_async_client()
            response = await client.get(
                query_url,
                params=query_params,
                headers=await auth_manager.get_headers_async(),
                timeout=config.timeout,
            )
            response.raise_for_status()

            result = response.json().get("result", [])
            if not result:
                return IncidentResponse(
                    success=False,
                    message=f"Incident not found: {incident_id}",
                )

            incident_id = result[0].get("sys_id")
            api_url = f"{config.api_url}/table/incident/{incident_id}"

        except httpx.HTTPError as e:
            logger.error(f"Failed to find incident: {e}")
            return IncidentResponse(
                success=False,
                message=f"Failed to find incident: {str(e)}",
            )

    # Build request data
    data = {}

    if params.short_description:
        data["short_description"] = params.short_description
    if params.description:
        data["description"] = params.description
    if params.state:
        data["state"] = params.state
    if params.category:
        data["category"] = params.category
    if params.subcategory:
        data["subcategory"] = params.subcategory
    if params.priority:
        data["priority"] = params.priority
    if params.impact:
        data["impact"] = params.impact
    if params.urgency:
        data["urgency"] = params.urgency
    if params.assigned_to:
        data["assigned_to"] = params.assigned_to
    if params.assignment_group:
        data["assignment_group"] = params.assignment_group
    if params.work_notes:
        data["work_notes"] = params.work_notes
    if params.close_notes:
        data["close_notes"] = params.close_notes
    if params.close_code:
        data["close_code"] = params.close_code

    # Make request
    try:
        client = await get_async_client()
        response = await client.put(
            api_url,
            json=data,
            headers=await auth_manager.get_headers_async(),
            timeout=config.timeout,
        )
        response.raise_for_status()

        result = response.json().get("result", {})

        return IncidentResponse(
            success=True,
            message="Incident updated successfully",
            incident_id=result.get("sys_id"),
            incident_number=result.get("number"),
        )

    except httpx.HTTPError as e:
        logger.error(f"Failed to update incident: {e}")
        return IncidentResponse(
            success=False,
            message=f"Failed to update incident: {str(e)}",
        )


async def add_comment(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: AddCommentParams,
) -> IncidentResponse:
    """
    Add a comment to an incident in ServiceNow.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters for adding the comment.

    Returns:
        Response with the result of the operation.
    """
    # Determine if incident_id is a number or sys_id
    incident_id = params.incident_id
    if len(incident_id) == 32 and all(c in "0123456789abcdef" for c in incident_id):
        # This is likely a sys_id
        api_url = f"{config.api_url}/table/incident/{incident_id}"
    else:
        # This is likely an incident number
        # First, we need to get the sys_id
        try:
            query_url = f"{config.api_url}/table/incident"
            query_params: Dict[str, Any] = {
                "sysparm_query": f"number={incident_id}",
                "sysparm_limit": 1,
            }

            client = await get_async_client()
            response = await client.get(
                query_url,
                params=query_params,
                headers=await auth_manager.get_headers_async(),
                timeout=config.timeout,
            )
            response.raise_for_status()

            result = response.json().get("result", [])
            if not result:
                return IncidentResponse(
                    success=False,
                    message=f"Incident not found: {incident_id}",
                )

            incident_id = result[0].get("sys_id")
            api_url = f"{config.api_url}/table/incident/{incident_id}"

        except httpx.HTTPError as e:
            logger.error(f"Failed to find incident: {e}")
            return IncidentResponse(
                success=False,
                message=f"Failed to find incident: {str(e)}",
            )

    # Build request data
    data = {}

    if params.is_work_note:
        data["work_notes"] = params.comment
    else:
        data["comments"] = params.comment

    # Make request
    try:
        client = await get_async_client()
        response = await client.put(
            api_url,
            json=data,
            headers=await auth_manager.get_headers_async(),
            timeout=config.timeout,
        )
        response.raise_for_status()

        result = response.json().get("result", {})

        return IncidentResponse(
            success=True,
            message="Comment added successfully",
            incident_id=result.get("sys_id"),
            incident_number=result.get("number"),
        )

    except httpx.HTTPError as e:
        logger.error(f"Failed to add comment: {e}")
        return IncidentResponse(
            success=False,
            message=f"Failed to add comment: {str(e)}",
        )


async def resolve_incident(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ResolveIncidentParams,
) -> IncidentResponse:
    """
    Resolve an incident in ServiceNow.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters for resolving the incident.

    Returns:
        Response with the result of the operation.
    """
    # Determine if incident_id is a number or sys_id
    incident_id = params.incident_id
    if len(incident_id) == 32 and all(c in "0123456789abcdef" for c in incident_id):
        # This is likely a sys_id
        api_url = f"{config.api_url}/table/incident/{incident_id}"
    else:
        # This is likely an incident number
        # First, we need to get the sys_id
        try:
            query_url = f"{config.api_url}/table/incident"
            query_params: Dict[str, Any] = {
                "sysparm_query": f"number={incident_id}",
                "sysparm_limit": 1,
            }

            client = await get_async_client()
            response = await client.get(
                query_url,
                params=query_params,
                headers=await auth_manager.get_headers_async(),
                timeout=config.timeout,
            )
            response.raise_for_status()

            result = response.json().get("result", [])
            if not result:
                return IncidentResponse(
                    success=False,
                    message=f"Incident not found: {incident_id}",
                )

            incident_id = result[0].get("sys_id")
            api_url = f"{config.api_url}/table/incident/{incident_id}"

        except httpx.HTTPError as e:
            logger.error(f"Failed to find incident: {e}")
            return IncidentResponse(
                success=False,
                message=f"Failed to find incident: {str(e)}",
            )

    # Build request data
    data: Dict[str, Any] = {
        "state": "6",  # Resolved
        "close_code": params.resolution_code,
        "close_notes": params.resolution_notes,
        "resolved_at": "now",
    }

    # Make request
    try:
        client = await get_async_client()
        response = await client.put(
            api_url,
            json=data,
            headers=await auth_manager.get_headers_async(),
            timeout=config.timeout,
        )
        response.raise_for_status()

        result = response.json().get("result", {})

        return IncidentResponse(
            success=True,
            message="Incident resolved successfully",
            incident_id=result.get("sys_id"),
            incident_number=result.get("number"),
        )

    except httpx.HTTPError as e:
        logger.error(f"Failed to resolve incident: {e}")
        return IncidentResponse(
            success=False,
            message=f"Failed to resolve incident: {str(e)}",
        )


async def list_incidents(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: ListIncidentsParams,
) -> dict:
    """
    List incidents from ServiceNow.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters for listing incidents.

    Returns:
        Dictionary with list of incidents.
    """
    api_url = f"{config.api_url}/table/incident"

    filters = []
    if params.state:
        filters.append(f"state={params.state}")
    if params.assigned_to:
        filters.append(f"assigned_to={params.assigned_to}")
    if params.assignment_group:
        filters.append(f"assignment_group.name={params.assignment_group}")
    if params.category:
        filters.append(f"category={params.category}")
    if params.updated_on_after:
        filters.append(f"sys_updated_on>={params.updated_on_after}")
    if params.updated_on_before:
        filters.append(f"sys_updated_on<={params.updated_on_before}")
    if params.opened_after:
        filters.append(f"opened_at>={params.opened_after}")
    if params.opened_before:
        filters.append(f"opened_at<={params.opened_before}")
    if params.query:
        filters.append(f"short_descriptionLIKE{params.query}^ORdescriptionLIKE{params.query}")

    query_params = _build_sysparm_params(
        params.limit,
        params.offset,
        query=_join_query_parts(filters),
        exclude_reference_link=True,
    )

    try:
        client = await get_async_client()
        response = await client.get(
            api_url,
            params=query_params,
            headers=await auth_manager.get_headers_async(),
            timeout=config.timeout,
        )
        response.raise_for_status()

        incidents = []
        for incident_data in response.json().get("result", []):
            assigned_to = incident_data.get("assigned_to")
            if isinstance(assigned_to, dict):
                assigned_to = assigned_to.get("display_value")
            assignment_group = incident_data.get("assignment_group")
            if isinstance(assignment_group, dict):
                assignment_group = assignment_group.get("display_value")
            incidents.append({
                "sys_id": incident_data.get("sys_id"),
                "number": incident_data.get("number"),
                "short_description": incident_data.get("short_description"),
                "description": incident_data.get("description"),
                "state": incident_data.get("state"),
                "priority": incident_data.get("priority"),
                "assigned_to": assigned_to,
                "assignment_group": assignment_group,
                "category": incident_data.get("category"),
                "subcategory": incident_data.get("subcategory"),
                "opened_at": incident_data.get("opened_at"),
                "created_on": incident_data.get("sys_created_on"),
                "updated_on": incident_data.get("sys_updated_on"),
            })

        return _paginated_list_response(
            incidents,
            params.limit,
            params.offset,
            "incidents",
            extra={"message": f"Found {len(incidents)} incidents"},
        )

    except httpx.HTTPError as e:
        logger.error(f"Failed to list incidents: {e}")
        return {
            "success": False,
            "message": f"Failed to list incidents: {str(e)}",
            "incidents": [],
        }


async def get_incident_by_number(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetIncidentByNumberParams,
) -> dict:
    """
    Fetch a single incident from ServiceNow by its number.

    Args:
        config: Server configuration.
        auth_manager: Authentication manager.
        params: Parameters for fetching the incident.

    Returns:
        Dictionary with the incident details.
    """
    api_url = f"{config.api_url}/table/incident"

    # Build query parameters
    query_params: Dict[str, Any] = {
        "sysparm_query": f"number={params.incident_number}",
        "sysparm_limit": 1,
        "sysparm_display_value": "true",
        "sysparm_exclude_reference_link": "true",
    }

    # Make request
    try:
        client = await get_async_client()
        response = await client.get(
            api_url,
            params=query_params,
            headers=await auth_manager.get_headers_async(),
            timeout=config.timeout,
        )
        response.raise_for_status()

        data = response.json()
        result = data.get("result", [])

        if not result:
            return {
                "success": False,
                "message": f"Incident not found: {params.incident_number}",
            }

        incident_data = result[0]
        assigned_to = incident_data.get("assigned_to")
        if isinstance(assigned_to, dict):
            assigned_to = assigned_to.get("display_value")

        incident = {
            "sys_id": incident_data.get("sys_id"),
            "number": incident_data.get("number"),
            "short_description": incident_data.get("short_description"),
            "description": incident_data.get("description"),
            "state": incident_data.get("state"),
            "priority": incident_data.get("priority"),
            "assigned_to": assigned_to,
            "category": incident_data.get("category"),
            "subcategory": incident_data.get("subcategory"),
            "created_on": incident_data.get("sys_created_on"),
            "updated_on": incident_data.get("sys_updated_on"),
        }

        return {
            "success": True,
            "message": f"Incident {params.incident_number} found",
            "incident": incident,
        }

    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch incident: {e}")
        return {
            "success": False,
            "message": f"Failed to fetch incident: {str(e)}",
        }


async def get_incident_journal(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: GetIncidentJournalParams,
) -> dict:
    """Fetch the work_notes and comments timeline for an incident.

    ServiceNow stores work_notes and comments as journal fields in
    the ``sys_journal_field`` table, not as columns on the incident
    record itself. The Table API doesn't surface them by default;
    callers have historically had to either query journal fields
    explicitly or include ``sysparm_display_value=all`` and parse
    the journal stream from the response.

    This tool wraps the explicit query path: look up the incident's
    sys_id by number, then query ``sys_journal_field`` for that
    record_id with the requested journal fields.

    Closes Issue #52
    (https://github.com/echelon-ai-labs/servicenow-mcp/issues/52).
    """
    fields = params.fields or ["work_notes", "comments"]

    # Step 1: resolve incident number to sys_id.
    incident_url = f"{config.api_url}/table/incident"
    try:
        client = await get_async_client()
        lookup = await client.get(
            incident_url,
            headers=await auth_manager.get_headers_async(),
            params={
                "sysparm_query": f"number={params.incident_number}",
                "sysparm_limit": "1",
                "sysparm_fields": "sys_id,number",
            },
            timeout=config.timeout,
        )
    except httpx.HTTPError as e:
        logger.error(f"Failed to look up incident: {e}")
        return {
            "success": False,
            "message": f"Failed to look up incident: {e}",
        }

    if lookup.status_code != 200:
        return {
            "success": False,
            "message": f"Incident lookup returned {lookup.status_code}",
        }

    matches = lookup.json().get("result", [])
    if not matches:
        return {
            "success": False,
            "message": f"Incident not found: {params.incident_number}",
        }
    sys_id = matches[0].get("sys_id")
    if not sys_id:
        return {
            "success": False,
            "message": f"Incident {params.incident_number} returned no sys_id",
        }

    # Step 2: query journal entries for that sys_id, ordered chronologically.
    fields_filter = "^OR".join(f"element={f}" for f in fields)
    journal_query = f"name=incident^element_id={sys_id}^({fields_filter})"
    try:
        client = await get_async_client()
        journal_response = await client.get(
            f"{config.api_url}/table/sys_journal_field",
            headers=await auth_manager.get_headers_async(),
            params={
                "sysparm_query": f"{journal_query}^ORDERBYsys_created_on",
                "sysparm_limit": str(params.limit),
                "sysparm_fields": (
                    "sys_id,sys_created_on,sys_created_by,element,value"
                ),
            },
            timeout=config.timeout,
        )
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch journal: {e}")
        return {
            "success": False,
            "message": f"Failed to fetch journal: {e}",
        }

    if journal_response.status_code != 200:
        return {
            "success": False,
            "message": f"Journal query returned {journal_response.status_code}",
        }

    raw_entries = journal_response.json().get("result", [])
    entries = [
        {
            "sys_id": e.get("sys_id"),
            "field": e.get("element"),
            "created_on": e.get("sys_created_on"),
            "created_by": e.get("sys_created_by"),
            "text": e.get("value"),
        }
        for e in raw_entries
    ]

    return {
        "success": True,
        "incident_number": params.incident_number,
        "incident_sys_id": sys_id,
        "fields_queried": fields,
        "count": len(entries),
        "entries": entries,
    }

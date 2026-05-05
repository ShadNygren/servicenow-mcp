"""Natural-language tools for the ServiceNow MCP server.

Wraps :class:`servicenow_mcp.utils.nl.NLPProcessor` in the standard
``(config, auth_manager, params) -> Response`` tool signature so the
parser plugs into echelon's tool registry.

These are gated behind the opt-in ``nl_power_user`` package — they're
useful as a quick natural-language shortcut for power users but
overlap with the more precise structured tools (``list_incidents``,
``update_incident``), so we don't include them in the default
packages.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.async_http import get_async_client
from servicenow_mcp.utils.config import ServerConfig
from servicenow_mcp.utils.nl import NLPProcessor


logger = logging.getLogger(__name__)


class NaturalLanguageSearchParams(BaseModel):
    """Parameters for a natural-language search."""

    query: str = Field(
        ...,
        description=(
            "Natural-language search phrase, e.g. "
            '"find all incidents about SAP with high priority"'
        ),
    )


class NaturalLanguageSearchResponse(BaseModel):
    """Response from a natural-language search."""

    table: str = Field(..., description="ServiceNow table that was queried")
    encoded_query: str = Field(..., description="The sysparm_query that was sent")
    record_count: int = Field(..., description="Number of records returned")
    records: List[Dict[str, Any]] = Field(..., description="Records returned")
    success: bool = Field(..., description="Whether the search succeeded")
    message: str = Field(..., description="Human-readable status")


class NaturalLanguageUpdateParams(BaseModel):
    """Parameters for a natural-language update command."""

    command: str = Field(
        ...,
        description=(
            "Natural-language update phrase referencing a record number, e.g. "
            '"Close incident INC0010003 with resolution: fixed the issue"'
        ),
    )


class NaturalLanguageUpdateResponse(BaseModel):
    """Response from a natural-language update."""

    record_number: str = Field(..., description="The record that was updated")
    sys_id: Optional[str] = Field(None, description="sys_id of the updated record")
    updates: Dict[str, Any] = Field(..., description="Field updates that were applied")
    success: bool = Field(..., description="Whether the update succeeded")
    message: str = Field(..., description="Human-readable status")


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


_PREFIX_TO_TABLE = {
    "INC": "incident",
    "PRB": "problem",
    "CHG": "change_request",
    "TASK": "task",
}


async def natural_language_search(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: NaturalLanguageSearchParams,
) -> NaturalLanguageSearchResponse:
    """Search ServiceNow records using a natural-language phrase."""
    parsed = NLPProcessor.parse_search_query(params.query)
    table = parsed["table"]
    encoded_query = parsed["query"]
    limit = parsed["limit"]

    url = f"{config.instance_url.rstrip('/')}/api/now/table/{table}"
    request_params: Dict[str, str] = {"sysparm_limit": str(limit)}
    if encoded_query:
        request_params["sysparm_query"] = encoded_query

    try:
        client = await get_async_client()
        response = await client.get(
            url,
            headers=await auth_manager.get_headers_async(),
            params=request_params,
            timeout=30,
        )
    except httpx.HTTPError as exc:
        return NaturalLanguageSearchResponse(
            table=table,
            encoded_query=encoded_query,
            record_count=0,
            records=[],
            success=False,
            message=f"Network error: {exc}",
        )

    if response.status_code != 200:
        return NaturalLanguageSearchResponse(
            table=table,
            encoded_query=encoded_query,
            record_count=0,
            records=[],
            success=False,
            message=f"ServiceNow returned {response.status_code}: {response.text[:200]}",
        )

    records = response.json().get("result", [])
    return NaturalLanguageSearchResponse(
        table=table,
        encoded_query=encoded_query,
        record_count=len(records),
        records=records,
        success=True,
        message=f"Found {len(records)} record(s) in {table}.",
    )


async def natural_language_update(
    config: ServerConfig,
    auth_manager: AuthManager,
    params: NaturalLanguageUpdateParams,
) -> NaturalLanguageUpdateResponse:
    """Update a record by parsing a natural-language phrase."""
    try:
        record_number, updates = NLPProcessor.parse_update_command(params.command)
    except ValueError as exc:
        return NaturalLanguageUpdateResponse(
            record_number="",
            sys_id=None,
            updates={},
            success=False,
            message=str(exc),
        )

    if not updates:
        return NaturalLanguageUpdateResponse(
            record_number=record_number,
            sys_id=None,
            updates={},
            success=False,
            message="No actionable updates found in command (no state change, comments, or work notes).",
        )

    # Map record-number prefix to its table.
    prefix = "".join(c for c in record_number if not c.isdigit())[:4].upper()
    table = _PREFIX_TO_TABLE.get(prefix)
    if not table:
        return NaturalLanguageUpdateResponse(
            record_number=record_number,
            sys_id=None,
            updates=updates,
            success=False,
            message=f"Unsupported record-number prefix '{prefix}'.",
        )

    headers = await auth_manager.get_headers_async()
    base_url = f"{config.instance_url.rstrip('/')}/api/now/table/{table}"

    # Look up sys_id by number first — we can't PATCH via the friendly number.
    try:
        client = await get_async_client()
        lookup = await client.get(
            base_url,
            headers=headers,
            params={"sysparm_query": f"number={record_number}", "sysparm_limit": "1"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        return NaturalLanguageUpdateResponse(
            record_number=record_number,
            sys_id=None,
            updates=updates,
            success=False,
            message=f"Network error during sys_id lookup: {exc}",
        )

    if lookup.status_code != 200:
        return NaturalLanguageUpdateResponse(
            record_number=record_number,
            sys_id=None,
            updates=updates,
            success=False,
            message=f"sys_id lookup returned {lookup.status_code}",
        )

    matches = lookup.json().get("result", [])
    if not matches:
        return NaturalLanguageUpdateResponse(
            record_number=record_number,
            sys_id=None,
            updates=updates,
            success=False,
            message=f"Record {record_number} not found in {table}.",
        )

    sys_id = matches[0].get("sys_id")
    if not sys_id:
        return NaturalLanguageUpdateResponse(
            record_number=record_number,
            sys_id=None,
            updates=updates,
            success=False,
            message=f"Record {record_number} returned no sys_id.",
        )

    try:
        patch = await client.patch(
            f"{base_url}/{sys_id}",
            headers=headers,
            json=updates,
            timeout=30,
        )
    except httpx.HTTPError as exc:
        return NaturalLanguageUpdateResponse(
            record_number=record_number,
            sys_id=sys_id,
            updates=updates,
            success=False,
            message=f"Network error during update: {exc}",
        )

    if patch.status_code not in (200, 204):
        return NaturalLanguageUpdateResponse(
            record_number=record_number,
            sys_id=sys_id,
            updates=updates,
            success=False,
            message=f"Update returned {patch.status_code}: {patch.text[:200]}",
        )

    return NaturalLanguageUpdateResponse(
        record_number=record_number,
        sys_id=sys_id,
        updates=updates,
        success=True,
        message=f"Updated {record_number} ({sys_id}) with {list(updates.keys())}.",
    )

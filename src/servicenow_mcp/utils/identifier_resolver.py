import re
from typing import Any, Dict

import requests

SYS_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)

_NUMBER_FIELD: Dict[str, str] = {
    "incident": "number",
    "change_request": "number",
    "problem": "number",
    "sc_request": "number",
    "sc_task": "number",
    "task": "number",
    "kb_knowledge": "number",
    "sn_si_incident": "number",
}


def is_sys_id(value: str) -> bool:
    """Return True if value is a 32-character hex string (ServiceNow sys_id)."""
    if not isinstance(value, str):
        return False
    return bool(SYS_ID_PATTERN.match(value))


def resolve_identifier(config, auth_manager, table: str, identifier: str) -> str:
    """
    Return the sys_id for identifier.

    If identifier is already a sys_id (32 hex chars), return it unchanged with no API call.
    Otherwise, query the table by its number field and return the matching sys_id.

    Raises ValueError with an actionable message if the record is not found.
    """
    if is_sys_id(identifier):
        return identifier

    number_field = _NUMBER_FIELD.get(table, "number")
    url = f"{config.api_url}/table/{table}"
    params: Dict[str, Any] = {
        "sysparm_query": f"{number_field}={identifier.upper()}",
        "sysparm_fields": "sys_id",
        "sysparm_limit": 1,
    }
    headers = auth_manager.get_headers()
    response = requests.get(url, headers=headers, params=params, timeout=config.timeout)
    response.raise_for_status()

    results = response.json().get("result", [])
    if not results:
        raise ValueError(
            f"Record not found: {table}/{identifier}. "
            "Verify the record exists and that you have read access to this table."
        )
    sys_id: str = results[0]["sys_id"]
    return sys_id

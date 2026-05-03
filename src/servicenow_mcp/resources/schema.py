"""Schema-discovery resources for the ServiceNow MCP server.

Exposes three URIs the LLM can read to learn the data model of the
connected ServiceNow instance, eliminating the need to guess field
names and reducing trial-and-error against tools:

- ``servicenow://tables``
    List of tables (name, label, sys_id) from ``sys_db_object``.

- ``servicenow://tables/{table}``
    Sample records (limit 10) from ``{table}``, useful for shape
    discovery.

- ``servicenow://schema/{table}``
    Column metadata (name, label, internal_type, mandatory, max_length)
    for ``{table}`` from ``sys_dictionary``.

Results are cached for 5 minutes — schema lookups are idempotent and
common (the LLM often reads the schema before every tool call), and
sys_dictionary doesn't change often.

Pattern adapted from ``michaelbuckner/servicenow-mcp`` (``server.py``
registrations at lines 327-333) but reimplemented for echelon's
low-level MCP Server. Phase 8 will replace this with FastMCP
``@mcp.resource()`` decorators.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig


logger = logging.getLogger(__name__)


# URI scheme constants. Exposed for server.py to register handlers.
SCHEMA_RESOURCE_URIS = {
    "tables_list": "servicenow://tables",
    "table_records_template": "servicenow://tables/{table}",
    "table_schema_template": "servicenow://schema/{table}",
}


# Cache settings.
_CACHE_TTL_SECONDS = 300  # 5 minutes
_TABLES_LIST_LIMIT = 1000
_TABLE_SAMPLE_LIMIT = 10


class _TTLCache:
    """Tiny, in-process TTL cache. Avoids a cachetools dependency.

    Phase 9 will move to httpx with proper response caching, at which
    point this can go away.
    """

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if not entry:
            return None
        timestamp, value = entry
        if time.monotonic() - timestamp > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._store.clear()


class SchemaResources:
    """Implements the three schema-discovery resource URIs.

    Construct one per ``ServiceNowMCP`` instance; it shares the
    server's ``ServerConfig`` and ``AuthManager`` and maintains its
    own TTL cache.
    """

    def __init__(self, config: ServerConfig, auth_manager: AuthManager) -> None:
        self.config = config
        self.auth_manager = auth_manager
        self._cache = _TTLCache(_CACHE_TTL_SECONDS)

    # -- Public read entry point ------------------------------------------------

    def read(self, uri: str) -> str:
        """Return the JSON body for ``uri``, raising ValueError if unsupported."""
        if uri == SCHEMA_RESOURCE_URIS["tables_list"]:
            return json.dumps(self._list_tables(), indent=2)
        if uri.startswith("servicenow://tables/"):
            table = uri[len("servicenow://tables/"):]
            if not table:
                raise ValueError(f"Missing table name in URI: {uri}")
            return json.dumps(self._sample_records(table), indent=2)
        if uri.startswith("servicenow://schema/"):
            table = uri[len("servicenow://schema/"):]
            if not table:
                raise ValueError(f"Missing table name in URI: {uri}")
            return json.dumps(self._get_table_schema(table), indent=2)
        raise ValueError(f"Unsupported schema resource URI: {uri}")

    # -- Cached fetchers --------------------------------------------------------

    def _list_tables(self) -> List[Dict[str, Any]]:
        cached = self._cache.get("tables_list")
        if cached is not None:
            return cached
        result = self._table_api_get(
            "sys_db_object",
            params={
                "sysparm_fields": "name,label,sys_id",
                "sysparm_limit": str(_TABLES_LIST_LIMIT),
            },
        )
        self._cache.set("tables_list", result)
        return result

    def _sample_records(self, table: str) -> List[Dict[str, Any]]:
        cache_key = f"sample:{table}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result = self._table_api_get(
            table,
            params={"sysparm_limit": str(_TABLE_SAMPLE_LIMIT)},
        )
        self._cache.set(cache_key, result)
        return result

    def _get_table_schema(self, table: str) -> List[Dict[str, Any]]:
        cache_key = f"schema:{table}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        # Filter on element-not-empty so we don't return collection-level rows.
        result = self._table_api_get(
            "sys_dictionary",
            params={
                "sysparm_query": f"name={table}^elementISNOTEMPTY",
                "sysparm_fields": "element,column_label,internal_type,mandatory,max_length",
                "sysparm_limit": "500",
            },
        )
        self._cache.set(cache_key, result)
        return result

    # -- HTTP helper ------------------------------------------------------------

    def _table_api_get(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        if not self.config.instance_url:
            raise ValueError("Instance URL is required to read schema resources")
        url = f"{self.config.instance_url.rstrip('/')}/api/now/table/{table}"
        headers = self.auth_manager.get_headers()
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(
                f"ServiceNow Table API returned {response.status_code} for {table}"
            )
        return response.json().get("result", [])

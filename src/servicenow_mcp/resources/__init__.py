"""MCP resources exposed by the ServiceNow MCP server."""

from servicenow_mcp.resources.schema import (
    SchemaResources,
    SCHEMA_RESOURCE_URIS,
)

__all__ = ["SchemaResources", "SCHEMA_RESOURCE_URIS"]

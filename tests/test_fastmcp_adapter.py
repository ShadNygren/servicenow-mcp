"""Tests for fastmcp_adapter.register_tool sync/async dispatch (Phase 9.1)."""

from typing import Any
from unittest.mock import MagicMock

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from servicenow_mcp.utils.fastmcp_adapter import register_tool


class _SampleParams(BaseModel):
    short_description: str = Field(..., description="Short desc of the thing")
    priority: str = Field("3", description="Priority 1-5")


def _sync_impl(config: Any, auth_manager: Any, params: _SampleParams) -> dict:
    return {
        "kind": "sync",
        "short_description": params.short_description,
        "priority": params.priority,
    }


async def _async_impl(config: Any, auth_manager: Any, params: _SampleParams) -> dict:
    return {
        "kind": "async",
        "short_description": params.short_description,
        "priority": params.priority,
    }


async def test_register_tool_with_sync_impl_produces_callable_tool() -> None:
    mcp = FastMCP("test", stateless_http=True)
    register_tool(
        mcp,
        name="sample_sync",
        description="Sample sync tool",
        impl=_sync_impl,
        params_model=_SampleParams,
        config=MagicMock(),
        auth_manager=MagicMock(),
    )

    tools = await mcp.list_tools()
    names = [t.name for t in tools]
    assert "sample_sync" in names

    result = await mcp.call_tool("sample_sync", {"short_description": "hello"})
    # Sync impl wrapper called the impl function and FastMCP serialised the result.
    text = result[0].text  # TextContent
    assert "hello" in text
    assert "sync" in text


async def test_register_tool_with_async_impl_awaits_correctly() -> None:
    mcp = FastMCP("test", stateless_http=True)
    register_tool(
        mcp,
        name="sample_async",
        description="Sample async tool",
        impl=_async_impl,
        params_model=_SampleParams,
        config=MagicMock(),
        auth_manager=MagicMock(),
    )

    tools = await mcp.list_tools()
    assert "sample_async" in [t.name for t in tools]

    result = await mcp.call_tool("sample_async", {"short_description": "world"})
    text = result[0].text
    assert "world" in text
    assert "async" in text


async def test_async_and_sync_tools_register_side_by_side() -> None:
    """Both kinds can be registered on the same FastMCP instance."""
    mcp = FastMCP("test", stateless_http=True)
    cfg = MagicMock()
    auth = MagicMock()
    register_tool(
        mcp, name="t_sync", description="d", impl=_sync_impl,
        params_model=_SampleParams, config=cfg, auth_manager=auth,
    )
    register_tool(
        mcp, name="t_async", description="d", impl=_async_impl,
        params_model=_SampleParams, config=cfg, auth_manager=auth,
    )
    names = {t.name for t in await mcp.list_tools()}
    assert {"t_sync", "t_async"} <= names


async def test_schema_uses_field_metadata_for_both_dispatch_paths() -> None:
    """Description/default propagation works regardless of sync vs async."""
    mcp = FastMCP("test", stateless_http=True)
    register_tool(
        mcp, name="t", description="d", impl=_async_impl,
        params_model=_SampleParams, config=MagicMock(), auth_manager=MagicMock(),
    )
    tool = next(t for t in await mcp.list_tools() if t.name == "t")
    schema = tool.inputSchema
    assert schema["properties"]["short_description"]["description"] == "Short desc of the thing"
    assert schema["properties"]["priority"]["default"] == "3"
    assert schema["required"] == ["short_description"]


class _DefaultFactoryParams(BaseModel):
    """Regression: a field using ``default_factory`` (not ``default``).

    Before Phase 9.11, ``register_tool`` placed the materialised default value
    on the inspect.Parameter while leaving ``default_factory=list`` on the
    FieldInfo passed via ``Annotated``. FastMCP's create_model then saw both
    ``default`` and ``default_factory`` on the same generated field and raised
    ``TypeError: cannot specify both default and default_factory``.
    """

    name: str = Field(..., description="A required string")
    items: list[str] = Field(default_factory=list, description="Items list")


async def _default_factory_impl(
    config: Any, auth_manager: Any, params: _DefaultFactoryParams
) -> dict:
    return {"name": params.name, "count": len(params.items)}


async def test_default_factory_field_does_not_collide_with_default() -> None:
    """register_tool must accept Pydantic models with default_factory fields.

    This was an inert bug pre-9.11: tools whose params model had any
    ``default_factory`` field silently failed to register. Wiring the
    twelve flow tools surfaced four such tools (create_flow,
    add_steps_to_flow, add_subflow_step_to_flow, add_logic_to_flow).
    """
    mcp = FastMCP("test", stateless_http=True)
    register_tool(
        mcp,
        name="t_factory",
        description="d",
        impl=_default_factory_impl,
        params_model=_DefaultFactoryParams,
        config=MagicMock(),
        auth_manager=MagicMock(),
    )
    tool = next(t for t in await mcp.list_tools() if t.name == "t_factory")
    schema = tool.inputSchema
    assert schema["required"] == ["name"]
    # The materialised default (an empty list) should appear in the schema.
    assert schema["properties"]["items"]["default"] == []

    result = await mcp.call_tool("t_factory", {"name": "x"})
    assert "x" in result[0].text

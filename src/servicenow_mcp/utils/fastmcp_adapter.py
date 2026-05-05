"""Adapter helpers for registering existing ServiceNow tool functions with FastMCP.

The existing tool functions in :mod:`servicenow_mcp.tools.*` have the signature
``(config: ServerConfig, auth_manager: AuthManager, params: BaseModel) -> Any``.
FastMCP's ``add_tool`` introspects the function signature to generate a JSON
Schema for the MCP client.  If we register a tool function as-is, FastMCP would
expose ``config``, ``auth_manager``, and ``params`` as input properties, which is
wrong: those are server-side dependencies, not user-facing arguments.

This module's :func:`register_tool` builds a thin wrapper around the existing
implementation that:

1. Captures ``config`` and ``auth_manager`` in closure (they aren't visible to the
   MCP client).
2. Exposes the *fields of the params model* as the wrapper's keyword arguments,
   each carrying the field's annotation and ``Field(...)`` metadata via
   :class:`typing.Annotated`, so FastMCP's schema generator produces a flat,
   field-level JSON Schema with descriptions, defaults, and required flags
   matching the original Pydantic model.
3. Reconstructs the params model from the kwargs and calls the underlying
   implementation, so the implementation function does not need to change.

The result is FastMCP-everywhere registration without rewriting the 200+ tool
functions.  See Phase 8 in CLAUDE.md.
"""

from __future__ import annotations

import inspect
from typing import Annotated, Any, Callable, Type

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import ServerConfig


def register_tool(
    mcp: FastMCP,
    *,
    name: str,
    description: str,
    impl: Callable[[ServerConfig, AuthManager, BaseModel], Any],
    params_model: Type[BaseModel],
    config: ServerConfig,
    auth_manager: AuthManager,
) -> None:
    """Register a ServiceNow tool function with a FastMCP server.

    Args:
        mcp: The FastMCP instance.
        name: MCP tool name (e.g. ``"create_incident"``).
        description: Human-readable description shown to the LLM.
        impl: Existing tool implementation, signature
            ``(ServerConfig, AuthManager, ParamsModel) -> Any``.
        params_model: Pydantic model class describing the tool's parameters.
        config: ServerConfig instance, captured in the wrapper's closure.
        auth_manager: AuthManager instance, captured in the wrapper's closure.
    """
    fields = params_model.model_fields
    sig_params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}

    for field_name, info in fields.items():
        # Annotated[T, FieldInfo] preserves Field(description=, default=, ...)
        # so FastMCP's schema generator sees the same metadata Pydantic does.
        # Mypy can't follow the dynamic Annotated subscription (info.annotation
        # is Any | None at type-check time), but at runtime it's always a
        # concrete type from the Pydantic model definition.
        annotated_type = Annotated[info.annotation, info]  # type: ignore[name-defined]
        annotations[field_name] = annotated_type

        if info.is_required():
            default: Any = inspect.Parameter.empty
        elif info.default is not PydanticUndefined:
            default = info.default
        else:
            default = None

        sig_params.append(
            inspect.Parameter(
                field_name,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotated_type,
            )
        )

    new_signature = inspect.Signature(sig_params, return_annotation=Any)

    # Phase 9.1: dispatch on whether impl is sync or async.  FastMCP's add_tool
    # accepts both shapes; we just pick the matching wrapper so an awaitable
    # impl is awaited and a sync impl is called.  Sync impls continue to work
    # unchanged (FastMCP runs them in a threadpool).
    if inspect.iscoroutinefunction(impl):

        async def wrapper(**kwargs: Any) -> Any:
            return await impl(config, auth_manager, params_model(**kwargs))

    else:

        def wrapper(**kwargs: Any) -> Any:  # type: ignore[misc]
            return impl(config, auth_manager, params_model(**kwargs))

    wrapper.__name__ = name
    wrapper.__qualname__ = name
    wrapper.__doc__ = description
    wrapper.__signature__ = new_signature  # type: ignore[attr-defined]
    wrapper.__annotations__ = {**annotations, "return": Any}

    mcp.add_tool(wrapper, name=name, description=description)

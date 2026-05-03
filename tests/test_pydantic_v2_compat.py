"""Pydantic v2 compatibility regression tests.

Issue #26 reported that catalog-optimization param classes failed at
``params_model.model_json_schema()`` time:

    AttributeError: type object 'OptimizationRecommendationsParams' has
    no attribute 'model_json_schema'

The root cause was that the original classes used ``@dataclass``
*and* inherited from ``BaseModel`` — a combination that Pydantic v2
doesn't fully support. The MCP server calls ``model_json_schema()``
on every tool's params class during ``list_tools``, so this broke
server startup for anyone using these tools.

Echelon (or torkian's helpers refactor) silently fixed this before
our fork base, but the dead ``from dataclasses import dataclass``
import lingered. We removed the import in Phase 3.2 and add this
test so any future regression that re-introduces the dataclass
decorator (or otherwise breaks ``model_json_schema()``) fails the
build instead of breaking the server at runtime.

We test every params class registered in the tool registry — that's
the same surface the server walks during ``_list_tools_impl``.
"""

import pytest

from servicenow_mcp.tools.knowledge_base import (
    create_category as _kb_create_category,
)
from servicenow_mcp.tools.knowledge_base import (
    list_categories as _kb_list_categories,
)
from servicenow_mcp.utils.tool_utils import get_tool_definitions


def test_every_tool_params_class_supports_model_json_schema():
    """Every params class in the tool registry must support
    ``model_json_schema()`` — that's what the MCP server calls during
    ``list_tools``. If any class fails this, server startup will
    raise AttributeError for that tool."""
    definitions = get_tool_definitions(_kb_create_category, _kb_list_categories)

    failures = []
    for tool_name, definition in definitions.items():
        params_class = definition[1]
        try:
            schema = params_class.model_json_schema()
        except AttributeError as exc:
            failures.append((tool_name, params_class.__name__, str(exc)))
            continue
        # Sanity: schema is a valid Pydantic schema dict
        assert isinstance(schema, dict)
        assert "properties" in schema or "type" in schema, (
            f"{tool_name}: schema missing standard fields"
        )

    if failures:
        msg = "\n  ".join(f"{tool}: {cls} — {err}" for tool, cls, err in failures)
        pytest.fail(
            "Tool params classes do not support model_json_schema():\n  " + msg
            + "\nLikely cause: a class inherits from BaseModel but is also "
              "decorated with @dataclass. Remove the @dataclass decorator."
        )


def test_catalog_optimization_params_schemas_explicitly():
    """Explicit regression test for Issue #26 — the two specific classes
    the original bug report named."""
    from servicenow_mcp.tools.catalog_optimization import (
        OptimizationRecommendationsParams,
        UpdateCatalogItemParams,
    )

    schema_a = OptimizationRecommendationsParams.model_json_schema()
    schema_b = UpdateCatalogItemParams.model_json_schema()

    assert "properties" in schema_a
    assert "properties" in schema_b
    assert "recommendation_types" in schema_a["properties"]
    assert "item_id" in schema_b["properties"]

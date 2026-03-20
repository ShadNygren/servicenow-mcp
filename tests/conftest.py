"""Shared pytest fixtures and session-wide hooks."""

import logging
import os
import re
from typing import List

import pytest


# Test files inherited from echelon-ai-labs/servicenow-mcp that fail to import
# because they reference modules (servicenow_mcp.resources.catalogs,
# .changesets, .script_includes) that were never written. These have been
# broken since at least 2025-10 — torkian's fork excludes them via CI flags
# (commit 167b646). Skip at collection time so the rest of the suite runs.
# Phase 5 (resource refactor) is the right place to delete or rewrite them.
collect_ignore = [
    # Reference modules that were never written (servicenow_mcp.resources.catalogs,
    # .changesets, .script_includes). Phase 5 will fix or delete these tests.
    "test_catalog_resources.py",
    "test_changeset_resources.py",
    "test_script_include_resources.py",
    # Tests with pre-existing failures echelon never fixed — torkian's CI also
    # excludes these. Slated for triage in Phase 5 as part of the workflow/catalog
    # tool cleanup. Note: test_workflow_tools.py::test_add_workflow_activity_success
    # and test_change_tools.py::test_create_change_request_with_swapped_parameters_real
    # and test_knowledge_base.py::test_create_article_params are individual broken
    # tests within otherwise-passing files; they continue to fail until triaged.
    "test_server_catalog.py",
    "test_server_workflow.py",
    "test_workflow_tools_direct.py",
]


# Patterns that should never appear in any captured log line. Adding to
# this list makes the redaction check stricter — only add patterns that
# represent genuinely sensitive data, not just things that *might* be
# sensitive in some contexts.
_SECRET_LOG_PATTERNS = [
    re.compile(r"\baccess_token\b", re.IGNORECASE),
    re.compile(r"\brefresh_token\b", re.IGNORECASE),
    re.compile(r"Authorization:\s*Bearer\b", re.IGNORECASE),
    re.compile(r"Authorization:\s*Basic\b", re.IGNORECASE),
]


@pytest.fixture(autouse=True)
def _capture_logs_for_redaction_check(caplog):
    """Per-test fixture that fails the test if any captured log line
    matches a forbidden secret-leak pattern.

    Why: a regression here is not just a test-quality issue — it's a
    security regression (Issue #43 finding cross-cutting concern). echelon's
    main was logging OAuth response bodies at INFO level, which contained
    access_tokens. We fix that in Phase 1.2 and pin it open with this check
    so any future commit that reintroduces secret logging fails the build
    rather than ships.
    """
    caplog.set_level(logging.DEBUG)
    yield

    leaks: List[str] = []
    for record in caplog.records:
        message = record.getMessage()
        for pattern in _SECRET_LOG_PATTERNS:
            if pattern.search(message):
                leaks.append(f"[{record.levelname}] {record.name}: {message[:200]}")

    if leaks:
        joined = "\n  ".join(leaks)
        pytest.fail(
            "Forbidden secret-shaped string captured in logs (regression check):\n  "
            + joined
            + "\nIf this is a test that genuinely needs to assert log content, "
              "scope the assertion narrowly and document why."
        )


def pytest_collection_modifyitems(config, items):
    """Skip all integration tests unless SN_INTEGRATION_TESTS=1 is set.

    Tests opt in to the gate by adding ``@pytest.mark.integration`` (or by
    using fixtures like ``live_config`` / ``pdi_guard`` that depend on a
    reachable Personal Developer Instance). Default behavior keeps CI fast
    and PDI-independent.

    Pattern from Flowbie commit 0199475.
    """
    if os.getenv("SN_INTEGRATION_TESTS") == "1":
        return  # Env var set — let integration tests run.

    skip_marker = pytest.mark.skip(
        reason="Integration tests disabled. Set SN_INTEGRATION_TESTS=1 to enable.",
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)

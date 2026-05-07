"""Run-ID tagging for E2E test data.

Every record created by an integration test is tagged with a marker
prefix that includes the session-scoped UUID4 ``run_id``. This lets the
session-scoped finalizer in :mod:`tests.integration._cleanup` query each
touched table for records carrying our run-ID and bulk-delete them ---
guaranteeing the PDI is left in the same state regardless of which
tests pass or fail, and giving a forensic trail (the marker) if a
session crashes mid-run and the user needs to clean up manually.

Marker format::

    MCP_E2E_TEST_RUN <run_id> <test_name>

Tag fields preferred (per record type):
- ``description`` for incident, change_request, problem, knowledge, catalog
- ``comments`` for time_card
- ``short_description`` falls back if description is unavailable

Manual cleanup if a session crashes:
    Search the relevant table with sysparm_query=descriptionLIKEMCP_E2E_TEST_RUN
"""

from __future__ import annotations

import uuid

MARKER_PREFIX = "MCP_E2E_TEST_RUN"


def new_run_id() -> str:
    """Return a fresh UUID4 hex string suitable for use as a run-ID."""
    return uuid.uuid4().hex


def tag(run_id: str, test_name: str, suffix: str = "") -> str:
    """Build a marker string for a description/comment field.

    Args:
        run_id: The session-scoped UUID hex.
        test_name: Test identifier (typically the pytest node name).
        suffix: Optional trailing free-text (e.g. "after-update").

    Example:
        >>> tag("abc123", "test_incident_crud")
        'MCP_E2E_TEST_RUN abc123 test_incident_crud'
    """
    parts = [MARKER_PREFIX, run_id, test_name]
    if suffix:
        parts.append(suffix)
    return " ".join(parts)


def is_test_record(field_value: str | None, run_id: str) -> bool:
    """True iff ``field_value`` carries our marker for the given run."""
    if not field_value:
        return False
    return MARKER_PREFIX in field_value and run_id in field_value


def query_for_marker(run_id: str, field: str = "description") -> str:
    """Return a sysparm_query string matching records tagged with this run.

    The PDI's GlideQuery syntax uses ``LIKE`` for substring match. We
    search for the run_id specifically (more selective than
    ``MCP_E2E_TEST_RUN``) so concurrent runs from different sessions
    cannot collide.
    """
    return f"{field}LIKE{run_id}"

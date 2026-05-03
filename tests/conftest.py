"""Shared pytest fixtures and session-wide hooks."""

import logging
import re
from typing import List

import pytest


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

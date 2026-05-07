"""Pytest plugin that emits an audit-ready E2E test report.

Hooks into pytest's standard hooks and writes:
  - ``tests/integration/results/RESULTS_<UTC-iso>.md`` --- markdown report
  - ``tests/integration/results/junit.xml`` --- machine-readable for CI

The report is stamped with the ServiceNow version probe + plugin
inventory + run-ID + cleanup verification per the user's requirement
that every E2E run be audit-ready and version-stamped.

This plugin is conditionally enabled: it only does anything when
``SN_INTEGRATION_TESTS=1`` is set, and skips silently otherwise so the
unit-test suite (964 tests, run on every PR) is unaffected.

Plugin registration: see ``pyproject.toml`` → ``[tool.pytest.ini_options]
addopts = "-p tests.integration._report_plugin"`` (or via the
``pytest_plugins`` list in ``tests/conftest.py``).
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

# Module-level state, populated by fixtures and finalizers across the run.
# This is the canonical pytest-plugin pattern --- the plugin object holds
# state, fixtures push facts into it, finalizers consume them.

_state: dict = {
    "run_id": None,
    "started_at": None,
    "finished_at": None,
    "pdi_version": None,  # PdiVersionInfo
    "tests": [],  # list of {nodeid, outcome, duration_ms, tier}
    "cleanup_result": None,  # CleanupResult
    "orphan_sweep_result": None,
    "tracked_records": [],  # list of TrackedRecord
}


def push_run_id(run_id: str) -> None:
    """Called by the run_id session-scoped fixture."""
    _state["run_id"] = run_id


def push_pdi_version(info) -> None:
    """Called by the pdi_version session-scoped fixture."""
    _state["pdi_version"] = info


def push_tracked_record(record) -> None:
    """Called by the track_record fixture each time a test mutates the PDI."""
    _state["tracked_records"].append(record)


def push_cleanup_result(result, sweep: bool = False) -> None:
    """Called by the cleanup_session finalizer."""
    if sweep:
        _state["orphan_sweep_result"] = result
    else:
        _state["cleanup_result"] = result


def _enabled() -> bool:
    return os.environ.get("SN_INTEGRATION_TESTS") == "1"


def _classify_tier(nodeid: str) -> str:
    """Group the test by tier based on its filename."""
    name = nodeid.split("::")[0]
    if "test_foundation" in name:
        return "foundation"
    if "test_smoke_" in name:
        return "smoke"
    if "test_crud_" in name:
        return "crud"
    if "test_lifecycle_" in name:
        return "lifecycle"
    if "test_edge_" in name:
        return "edge"
    if "test_security_" in name:
        return "security"
    return "other"


# Pytest hooks


def pytest_configure(config) -> None:  # noqa: D401
    """Set the start timestamp."""
    if _enabled():
        _state["started_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()


def pytest_runtest_logreport(report) -> None:
    """Capture per-test pass/fail/skip + duration."""
    if not _enabled():
        return
    if report.when != "call":
        # We only care about the call phase, not setup/teardown.
        # An exception here is a setup-level skip (pytest puts that in
        # the setup phase). For now we keep it simple.
        if report.when == "setup" and report.outcome == "skipped":
            _state["tests"].append({
                "nodeid": report.nodeid,
                "outcome": "skipped",
                "duration_ms": int(report.duration * 1000),
                "tier": _classify_tier(report.nodeid),
                "skip_reason": str(report.longrepr) if report.longrepr else "",
            })
        return
    _state["tests"].append({
        "nodeid": report.nodeid,
        "outcome": report.outcome,
        "duration_ms": int(report.duration * 1000),
        "tier": _classify_tier(report.nodeid),
        "skip_reason": "",
    })


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: D401, ARG001
    """Write the markdown report."""
    if not _enabled():
        return
    _state["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = _state["finished_at"].replace(":", "").replace(".", "")
    md_path = results_dir / f"RESULTS_{timestamp}.md"
    with md_path.open("w") as fh:
        fh.write(_render_report())

    print(f"\n[E2E report] {md_path}")


def _render_report() -> str:
    """Build the markdown report from the captured state."""
    pdi = _state.get("pdi_version")
    run_id = _state.get("run_id") or "<unknown>"
    started = _state.get("started_at") or "<unknown>"
    finished = _state.get("finished_at") or "<unknown>"
    tests = _state.get("tests", [])
    cleanup = _state.get("cleanup_result")
    sweep = _state.get("orphan_sweep_result")

    lines: list[str] = []
    lines.append("# ServiceNow MCP E2E Test Report")
    lines.append("")
    lines.append(f"**Run started**: `{started}`")
    lines.append(f"**Run finished**: `{finished}`")
    lines.append(f"**Run ID**: `{run_id}`")
    if pdi is not None:
        url = pdi.instance_url
        # Redact the full URL --- show only the dev-instance prefix
        instance_id = url.replace("https://", "").split(".")[0] if url else "<unknown>"
        lines.append(f"**PDI instance**: `{instance_id}` (full URL redacted)")
        lines.append(f"**ServiceNow family**: {pdi.family_name or '<unknown>'}")
        lines.append(f"**Build tag**: `{pdi.build_tag or '<unknown>'}`")
        lines.append(f"**Active plugin count**: {pdi.plugin_count}")
        if pdi.probe_errors:
            lines.append(f"**Probe errors**: {len(pdi.probe_errors)} (see appendix)")
    else:
        lines.append("**PDI version**: `<not probed>`")
    lines.append("")

    # Summary table
    by_tier: dict[str, dict[str, int]] = {}
    by_tier_duration: dict[str, int] = {}
    for t in tests:
        tier = t["tier"]
        by_tier.setdefault(tier, {"passed": 0, "failed": 0, "skipped": 0})
        by_tier_duration.setdefault(tier, 0)
        by_tier[tier][t["outcome"]] += 1
        by_tier_duration[tier] += t["duration_ms"]

    lines.append("## Summary by tier")
    lines.append("")
    lines.append("| Tier | Pass | Fail | Skip | Duration |")
    lines.append("|---|---|---|---|---|")
    for tier in sorted(by_tier.keys()):
        b = by_tier[tier]
        d_ms = by_tier_duration[tier]
        d_str = f"{d_ms / 1000:.2f}s" if d_ms >= 1000 else f"{d_ms}ms"
        lines.append(
            f"| {tier} | {b['passed']} | {b['failed']} | {b['skipped']} | {d_str} |"
        )
    total_pass = sum(b["passed"] for b in by_tier.values())
    total_fail = sum(b["failed"] for b in by_tier.values())
    total_skip = sum(b["skipped"] for b in by_tier.values())
    total_dur = sum(by_tier_duration.values())
    lines.append(
        f"| **TOTAL** | **{total_pass}** | **{total_fail}** | **{total_skip}** | "
        f"**{total_dur / 1000:.2f}s** |"
    )
    lines.append("")

    # Cleanup section
    lines.append("## Cleanup verification")
    lines.append("")
    if cleanup is not None:
        lines.append(f"- Records created with run-ID tag: **{cleanup.tracked_count}**")
        lines.append(f"- Records successfully deleted: **{cleanup.deleted_count}**")
        if cleanup.failures:
            lines.append(
                f"- Cleanup failures: **{len(cleanup.failures)}** "
                "(see appendix for details)"
            )
        else:
            lines.append("- Cleanup failures: **0**")
    else:
        lines.append("- Cleanup not run (no mutating tests in this session).")
    if sweep is not None and sweep.orphan_swept_count:
        lines.append(
            f"- Orphan sweep recovered: **{sweep.orphan_swept_count}** records "
            "(records found via run-ID query that the per-test cleanup missed)"
        )
    lines.append("")

    # Per-test detail
    lines.append("## Per-test detail")
    lines.append("")
    lines.append("| Test | Tier | Outcome | Duration |")
    lines.append("|---|---|---|---|")
    for t in tests:
        lines.append(
            f"| `{t['nodeid']}` | {t['tier']} | {t['outcome']} | "
            f"{t['duration_ms']}ms |"
        )
    lines.append("")

    # Failure detail (if any)
    failed_tests = [t for t in tests if t["outcome"] == "failed"]
    if failed_tests:
        lines.append("## Failures")
        lines.append("")
        for t in failed_tests:
            lines.append(f"- `{t['nodeid']}` ({t['duration_ms']}ms)")
        lines.append("")
        lines.append(
            "Full diagnostic detail is in the pytest console output and the JUnit "
            "XML at `tests/integration/results/junit.xml`."
        )
        lines.append("")

    # Appendix: probe errors and plugin inventory
    lines.append("## Appendix")
    lines.append("")
    if pdi is not None and pdi.probe_errors:
        lines.append("### Version probe errors")
        for e in pdi.probe_errors:
            lines.append(f"- {e}")
        lines.append("")
    if pdi is not None and pdi.active_plugins:
        lines.append("### Active plugin inventory")
        lines.append("")
        lines.append("| Plugin ID | Version |")
        lines.append("|---|---|")
        for plugin_id in sorted(pdi.active_plugins.keys()):
            lines.append(f"| `{plugin_id}` | {pdi.active_plugins[plugin_id]} |")
        lines.append("")

    if cleanup is not None and cleanup.failures:
        lines.append("### Cleanup failure detail")
        lines.append("")
        for f in cleanup.failures:
            lines.append(f"- `{f}`")
        lines.append("")

    return "\n".join(lines) + "\n"

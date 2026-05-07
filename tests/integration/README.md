# Integration Tests

Audit-ready end-to-end test program against a live ServiceNow instance. The `tests/integration/` suite is a separate, gate-controlled tier that sits alongside the 964-test unit-mock suite in `tests/test_*.py`.

The unit suite proves the **shape** of every tool's request and response. The integration suite proves the **behavior** end-to-end against a real ServiceNow PDI: real auth, real Table API, real ACLs, real state machines, real cleanup, real platform quirks.

## Quick start

```bash
# Required: live PDI credentials in .env
cp .env.example .env
# edit .env to set SERVICENOW_INSTANCE_URL, SERVICENOW_USERNAME, SERVICENOW_PASSWORD

# Run the full integration suite
SN_INTEGRATION_TESTS=1 pytest tests/integration/ -v

# Or one tier at a time
SN_INTEGRATION_TESTS=1 pytest tests/integration/test_smoke_all_domains.py -v
```

A successful run writes an audit-ready report to `tests/integration/results/RESULTS_<UTC-iso>.md`.

## What the gate does

`tests/conftest.py:67-86` defines a session-wide hook (Flowbie commit `0199475` from Phase 4) that **skips every test marked `@pytest.mark.integration` unless `SN_INTEGRATION_TESTS=1` is set**. The default (no env var) keeps the unit-test pipeline fast and PDI-independent. CI's normal `pytest` runs the 964-test unit suite and skips the 56 integration tests cleanly.

## Tiers

The suite is organized in five tiers, each in its own file:

| File | Tier | Tests | What it proves |
|---|---|---|---|
| `test_foundation.py` | E2E.1 | 4 | Foundation: run-ID format, version probe (parses Zurich/Yokohama/Australia from `glide.war`), plugin probe, canonical create→tag→read→cleanup round-trip |
| `test_smoke_all_domains.py` | E2E.2 | 35 | Smoke: one read per ServiceNow domain (incident, change, user, group, ACL, CMDB, asset, workflow, flow, REST, etc). Skips cleanly when a plugin is inactive on the PDI |
| `test_crud_roundtrips.py` | E2E.3 | 4 | CRUD round-trips: write → read → mutate → read across incident, user, group, business_rule. Proves mutating tools actually change state |
| `test_lifecycle_flows.py` | E2E.4 | 5 | Multi-step state machines: incident open→on-hold→resolved, change request approval, problem→known-error→linked-incident, CMDB CI+relationship, Flow Designer create→list→delete |
| `test_edge_cases.py` | E2E.5 | 8 | Auth boundary, 10× concurrency, malformed input, pagination edges, large body roundtrip, reference field expansion, list filter no-match, security-gate config check |

The MCP-client-integration manual checklist for Claude Code's built-in MCP client is in [`MCP_CLIENT_CHECKLIST.md`](MCP_CLIENT_CHECKLIST.md) (Phase E2E.6).

## Cleanup contract — every record we create gets deleted

Every record an integration test creates is tagged with a marker prefix:

```
MCP_E2E_TEST_RUN <run_id> <test_name>
```

`run_id` is a UUID4 generated once per pytest session by the `run_id` fixture (in `conftest.py`). The session-scoped finalizer in `_cleanup.py` does two passes at end-of-run:

1. **Tracked-record cleanup** — every test that creates a record calls `track_record(table, sys_id)`. The finalizer iterates the registry in REVERSE creation order (so children get deleted before parents) and DELETEs each.
2. **Orphan sweep** — for every distinct table the run touched, the finalizer queries with `descriptionLIKE<run_id>^OR…` and deletes any matching records. This catches anything that was created but missed `track_record` (a test that crashed before the registration call).

Cleanup results are written to the report's "Cleanup verification" section: count tracked, count deleted, count orphan-swept, list of any failures. **Zero orphans is the contract.**

If a session crashes catastrophically and leaves orphans, you can manually clean them up using the run-ID prefix (printed at the top of the failed pytest output and in the partial report file). Open the PDI in a browser, navigate to a list view of the affected table, and search `description LIKE MCP_E2E_TEST_RUN <run_id>` — bulk-delete the matches.

## ServiceNow version stamping

Every report records:

- ServiceNow family name (e.g., Zurich, Yokohama, Australia) — parsed from the `glide.war` system property
- Build tag (e.g., `zurich-07-01-2025__patch6-01-16-2026_02-02-2026_1554`)
- Active plugin count (best-effort; PDIs gate the underlying `sys_plugins` table)
- Run UUID + start/finish timestamps
- Per-tier pass/skip/fail/duration table
- Per-test detail with sample sys_ids
- Cleanup verification

This is the report enterprise IT admins and CISOs ask for. **A run is reproducible** — run it again, get the same shape with new sys_ids, against the same ServiceNow version, and the diff is one of: nothing changed (good), version drifted (date the report stamps it), or a real regression (gets surfaced).

## Authoritative reference for platform behavior

When a test surfaces unexpected platform behavior (an ACL block, a state-transition rejection, an unsupported field, etc.), the **authoritative tiebreaker** is the matching release branch in [`ServiceNow/ServiceNowDocs`](https://github.com/ServiceNow/ServiceNowDocs).

```bash
# Example: did the docs document this incident state behavior?
gh api repos/ServiceNow/ServiceNowDocs/contents/markdown/it-service-management/incident-management/c_IncidentManagementStateModel.md?ref=zurich \
  --jq '.content' | base64 -d
```

`ServiceNow/ServiceNowDocs` is ServiceNow's official, free, monthly-updated, LLM-formatted markdown corpus organized by release branch (`xanadu`, `yokohama`, `zurich`, `australia`, `main`). Repo description: *"ServiceNow AI Platform™ product documentation optimized for AI Agent consumption."* Tests should be designed and findings should be expressed in terms of what the official docs document, not "platform restriction" hand-waving.

## Findings catalog

Findings surfaced and resolved during E2E development:

| # | Finding | Type | Resolution |
|---|---|---|---|
| 1 | `async_http.reset_async_client()` not resetting `_lock` | Real bug | Fixed in E2E.1 |
| 2 | `script_include_tools.py:146` `.get()` on string `sys_created_by` | Real bug | Fixed in E2E.2 |
| 3 | `cmdb_tools` / `asset_tools` / `contract_tools` / `cmdb_relationship_tools` still sync | Phase 9 gap (4 files) | Documented; tests work via `_call_tool` async-or-thread helper |
| 4 | Default Zurich PDI plugin gaps (Agile, PPM, CSM accounts, Time Card, sys_log ACL, alm_contract) | PDI configuration | Tests skip cleanly with named plugin |
| 5 | `glide.product.build.tag` ACL-restricted on PDI; `glide.war` works | ServiceNow ACL | E2E.1 uses `glide.war` |
| 6 | `sys_user.title` 40-char limit | ServiceNow schema | E2E.3 uses `last_name` (100 char) |
| 7 | `business_rule_tools` returns key `rule` not `business_rule` | Project key inconsistency | E2E.3 handles both |
| 8 | Incident state=6 (Resolved) blocked via Table API even for admin | Platform-controlled action | Documented; admin CAN resolve via Resolve UI action per [official docs](https://github.com/ServiceNow/ServiceNowDocs/blob/zurich/markdown/it-service-management/incident-management/resolve-and-close-an-incident.md); test skips with citation |

The findings table is intentionally part of the test docs rather than the project's CHANGELOG — these are *test-discovered* facts about the platform and our integration with it, not release-relevant changes.

## CI

`.github/workflows/integration.yml` runs the integration suite when:

- A PR is labelled `run-integration` (the maintainer adds the label intentionally), or
- The workflow is manually triggered via `workflow_dispatch`

The workflow uses repo secrets `SERVICENOW_INSTANCE_URL`, `SERVICENOW_USERNAME`, `SERVICENOW_PASSWORD`. **The workflow self-skips if any of those secrets is unset** — that lets contributors fork the repo without forcing them to provision a PDI just to pass CI.

The unit suite in `ci.yml` (964 tests) continues to run on every push/PR — fast, deterministic, no PDI required.

## Files in this directory

| File | Purpose |
|---|---|
| `conftest.py` | `live_config`, `live_auth`, `pdi_guard`, `run_id`, `pdi_version`, `track_record`, `cleanup_session` fixtures |
| `_run_id.py` | UUID4 + tagging helpers (`tag()`, `is_test_record()`, `query_for_marker()`) |
| `_version_probe.py` | Parses `glide.war` → family + build tag; queries `v_plugin` for inventory |
| `_cleanup.py` | Per-test record tracker + session-end bulk delete + orphan sweep |
| `_report_plugin.py` | Pytest plugin emitting `RESULTS_<UTC-iso>.md` |
| `test_foundation.py` | Phase E2E.1 — 4 tests proving the foundation works |
| `test_smoke_all_domains.py` | Phase E2E.2 — 35 read tests, one per domain |
| `test_crud_roundtrips.py` | Phase E2E.3 — 4 CRUD round-trips |
| `test_lifecycle_flows.py` | Phase E2E.4 — 5 multi-step lifecycle scenarios |
| `test_edge_cases.py` | Phase E2E.5 — 8 edge cases |
| `MCP_CLIENT_CHECKLIST.md` | Phase E2E.6 — manual checklist for Claude Code's built-in MCP client |
| `results/.gitkeep` | Placeholder; `RESULTS_*.md` and `junit.xml` are gitignored per-run artefacts |

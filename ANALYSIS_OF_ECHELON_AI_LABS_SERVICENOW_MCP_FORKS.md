# Analysis of Echelon-AI-Labs ServiceNow MCP Forks

A survey of 18 active forks of [`echelon-ai-labs/servicenow-mcp`](https://github.com/echelon-ai-labs/servicenow-mcp) (the upstream baseline at `main` @ `0625060`, 2025-10-03), evaluating which commits are **generic and worth cherry-picking** into `ShadNygren/servicenow-mcp` versus which are **environment-specific** to the fork owner's ServiceNow deployment.

## Methodology

Each fork was added as a remote of the local repo and `git log upstream/main..<remote>/main` was used to enumerate unique commits. For each commit of interest, the diff was inspected directly via `git show`. Categorization:

- **GENERIC** — works against any ServiceNow instance with default OOB tables, no hardcoded values. Cherry-pick candidates.
- **SEMI-GENERIC** — useful pattern but has fork-specific assumptions (custom paths, branding, scope IDs) that need adaptation.
- **ENV-SPECIFIC** — references `u_*`/`x_*` custom tables, hardcoded instance URLs, internal scope names, named individuals/teams, or non-OOB schemas. Skip.

Red flags actively scanned for: hardcoded `*.service-now.com` instance hostnames, custom-scope APIs (`/api/x_*`), `u_*` table-prefix references, real personal/team names, internal branding, single-org workflow logic.

## Summary table

| Fork | Ahead | Behind | Verdict | Top take |
|---|---|---|---|---|
| `torkian/servicenow-mcp` | 90 | 42 | **HIGH** — extensive cherry-pick | Helpers refactor, retry/backoff, rate limiting, bulk batch API, CMDB tools, asset tools, SCTASK, time card, OAuth fix, CI/CD scaffolding, 258 tests |
| `Flowbie/servicenow-mcp` | 194 | 0 | **HIGH** — selective port | SnowResponse envelope, identifier resolver, integration-test gate, flow-tools suite, table-tools dual-mode, integration_tools, agile_constants |
| `nathanolds22/servicenow-mcp` | 2 | 0 | **HIGH** — both commits | Comprehensive E2E test suite (111 tests across 6 files) + AI Agent / WFO / A2A tools targeting OOB AI Agent platform |
| `ericstarkey/servicenow-mcp` | 2 | 0 | **HIGH** | ApiKeyMiddleware + Docker Compose + Nginx + 22 tests for production deployment |
| `chan4lk/servicenow-mcp` (`streamable-http` branch) | — | — | **HIGH (future-phase)** | Streamable-HTTP support — directly relevant to our deferred SSE→Streamable-HTTP migration |
| `klapom/servicenow-mcp` | 13 | 0 | **MEDIUM** — split | Platform-admin tools (business_rule_tools, oauth_tools, rest_message_tools, scheduled_job_tools, sys_dictionary_tools), data-integration tools — generic. Neo4j RAG / BGE-M3 — env-specific. |
| `patricebechard/servicenow-mcp` | 4 | 0 | **MEDIUM** — all four | EXTRA_HTTP_HEADERS env-var support, package-data fix for `tool_packages.yaml`, mcp dep upgrade |
| `russ430/servicenow-mcp` | 4 | 0 | **MEDIUM** | Service Portal widget tools (sp_widget) — OOB table |
| `dobromirmontauk/servicenow-mcp` | 4 | 0 | **MEDIUM** — needs rebrand | CSM tools (accounts, locations, products, case correlation) target OOB CSM tables despite "Mashgin" framing |
| `haim-nizri/servicenow-mcp` | 3 | 0 | **MEDIUM (selective)** | Scripted REST API creation tools (sys_ws_definition, sys_ws_operation) — generic. NowLLM chatbot + xti namespace — skip. |
| `clguo-tw/servicenow-mcp` | 2 | 0 | **LOW-MEDIUM** | Small additions to incident filters (assign group, time range) |
| `natedolor/servicenow-mcp` | 1 | 0 | **LOW-MEDIUM** | Expanded list_incidents filter parameters |
| `Kalppatel000/servicenow-mcp` | 3 | 0 | **STUDY** | SessionBridge auth (zero-credential via browser cookies) — interesting pattern, requires their Chrome extension |
| `fromnewcoder/servicenow-mcp` | 1 | 0 | **LOW** | Install-guidance docs |
| `jonathan-f-spencer-usps/servicenow-mcp` | 2 | 8 | **LOW** | Dependabot config; otherwise just upstream-merge churn |
| `Nayef-Abou-Tayoun/servicenow-mcp` | 5 | 0 | **SKIP** | Entirely `u_*` custom fields specific to one org's incident schema |
| `FredM-AI/servicenow-mcp` | 51 | 0 | **SKIP** | 51 commits of Heroku/Procfile deploy churn including a `server_sse.py` → `server_see.py` typo-rename |
| `jschuller/servicenow-mcp` | 1 | 8 | **SKIP** | Single merge commit from `osomai/main`; no original work |

---

## Per-fork analysis

### `torkian/servicenow-mcp` (90 ahead, 42 behind)

**Last commit:** 2026-05-02 — actively maintained.
**Self-description:** "Maintained MCP Server for ServiceNow — SCTASK, time cards, 80+ tools, CI/CD, full wiki".
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...torkian:servicenow-mcp:main

**Summary.** This is the goldmine of the survey. A single highly-active maintainer ("Torkian") with disciplined daily commits, every change accompanied by tests (258 total at 80% coverage), well-written commit messages, and zero observable environment-specific code. The work spans new tools, infrastructure improvements, and project hygiene. Every commit examined was generic and applicable to any ServiceNow instance.

**Worth cherry-picking (GENERIC).** Many of these solve problems explicitly listed in our own playbook's "Cross-cutting issues none of them solve well" section.

- `cb727c0` — **Extract shared helpers into `utils/helpers.py`** (-740 lines duplication across 8 tool files). Removes copy-pasted `_get_instance_url`, `_get_headers`, `_unwrap_and_validate_params`. Foundational refactor that makes all subsequent improvements practical.
- `7c5d87e` — **Retry logic with exponential backoff to all HTTP requests.** Solves a documented gap in our analysis ("None of these implementations back off on 429").
- `fa39ca3` — **Rate-limiting awareness via `RateLimitTracker`** that parses `X-RateLimit-Remaining/Limit/Reset` and proactively sleeps. Module-level singleton, no caller changes. 34 tests. Solves another documented gap.
- `8415b42` — **Pagination helpers** (`_build_sysparm_params`, `_join_query_parts`, `_paginated_list_response` with `has_more`/`next_offset`). Applied to incidents, syslog, knowledge base. 46 new tests. Closes the pagination gap.
- `a091ae0` — **Bulk operations via `/api/now/v1/batch`** — `execute_bulk_operations` posts up to 100 sub-requests in a single HTTP call. 24 tests at 100% coverage.
- `ab3959f` — Input validation for date/datetime/duration fields.
- `2f3f80c` — Improved error messages across all tools (echelon's generic `RuntimeError` wrapping was called out as a weakness in our own analysis).
- `20eebc2` — Request/response logging in debug mode (with credential redaction).
- `ba56b83` — **`fix(auth): stop logging OAuth token response bodies`** — independent implementation of our planned playbook commit 3. **Strong validation that our own fix is the right approach**, and includes regression tests we should also adopt.
- `01bf610` + `7f01fe5` — **CMDB tools**: `list_cis`, `get_ci`, `create_ci`, `update_ci` against `cmdb_ci` (with optional subclass), plus relationship tools. 45 tests at 98% coverage. CMDB is OOB.
- `067a3c5` + `b20ef77` + `8c93107` — **Asset management**: `list_assets`, `get_asset`, `update_asset`, `create_asset`, `delete_asset` against `alm_asset` / `alm_hardware` (OOB). 35 tests at 99% coverage.
- `f7ab804` + `6b3756f` — **Asset contract management**: `list_asset_contracts`, `get_asset_contract`, `create_asset_contract`, `update_asset_contract` against `ast_contract` (OOB).
- `b544f7b` — **SCTASK and time card tools** — `sc_task` and `time_card` are OOB tables.
- `bfec67b` — **Syslog tools**: `list_syslog_entries`, `get_syslog_entry`.
- `6881ddb` — `execute_script_include` tool.
- `5587eae` + `ae3b91b` — `create_user_criteria_condition`, `create_user_criteria` (`sys_user_criteria` is OOB).
- `482eb4c` + `fa7e54d` — `create_ui_policy_action`, `create_ui_policy` (`sys_ui_policy` is OOB).
- `657c4f0` — `create_catalog_variable_choice`.
- `5037840` — `delete_catalog_item_variable` tool.
- `12479b5` — `create_catalog_item` tool.
- `7cfaacd` — **GitHub Actions CI + CodeQL + Dependabot** in one commit. Drop-in replacement for the simple CI we were planning in playbook commit 9.
- `2ab7f6b` + `3416ceb` — Codecov v5 integration with coverage badge.
- `c12aaec` — **PR template, issue templates (bug / feature / new_tool), CONTRIBUTING.md, SECURITY.md**. Project-hygiene baseline.
- `cba8215` — `workflow_dispatch` trigger on CI (allows manual runs from UI).
- `810152c` — Fix 34 unused-import lint errors via ruff auto-fix.
- `dfdcec7` — README badges (CI, CodeQL, Python, license).
- `3cb44bd` — Dockerfile fix to include `config/` directory (otherwise `tool_packages.yaml` is missing in the container).
- `84e10ac` — Comment out 11 unimplemented "ghost" tools in `tool_packages.yaml` that are referenced but don't exist in code.
- `264b048` — Remove tracked `.DS_Store` files and add to `.gitignore`.
- `e16c701` — README "What's New" section template.
- `e073ac4` — Add missing `sse_server_example.py` referenced in README.

**Risks if integrated.** Conflicts with our planned `fix/sse-auth-hardening` merge (their `server_sse.py` and Dockerfile changes overlap — resolve in favor of the hardening branch). Their `_make_request` infrastructure (retry, rate-limit, debug logging) is built on top of `requests`, not `httpx` — fine for our pre-async-refactor phase. Some commits depend on the `helpers.py` refactor (`cb727c0`) being in place first, so cherry-pick order matters.

**Bottom line.** **HIGH value — port aggressively.** This single fork closes most of the gaps our own analysis flagged (retry, rate limiting, pagination, error transparency, the OAuth-body-logging bug, project hygiene, CI/CD). Recommend pulling 30+ of their commits, ordered with the helpers refactor first.

---

### `Flowbie/servicenow-mcp` (194 ahead, 0 behind)

**Last commit:** 2026-04-22.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...Flowbie:servicenow-mcp:main

**Summary.** A heavily-developed fork with ~194 commits, mostly authored by `adolan@hawaii.edu`. The fork has invested in a few generic infrastructure patterns and a *lot* of feature work, some of which is generic (Flow Designer support, integration tools, agile tools) and some of which is product-specific (a "Workbench UI" approval-gate system that integrates with their own product). Worth selective porting.

**Worth cherry-picking (GENERIC).**

- `7aa4181` — **`SnowResponse` structured envelope** for consistent tool output. 83 lines + tests. Solves the "ServiceNow error payload visibility for the LLM" issue we flagged.
- `1ad7272` — **Identifier resolver for ticket-number → sys_id lookup.** Lets tools accept either `INC0010001` or a sys_id. 153 lines + tests.
- `0199475` — **Integration-test gate** — `pytest` skips integration tests unless `SN_INTEGRATION_TESTS=1`. Pattern for safely committing integration tests without breaking CI.
- `8eb4be5` + `c077b08` + many siblings — **Flow Designer tools** (~25 commits): `get_flow`, `get_flow_actions`, `get_flow_triggers`, `get_flow_version`, `add_steps_to_flow`, `delete_flow`, `clone_flow`, `update_flow_trigger`, `add_subflow_step_to_flow`, `add_logic_to_flow`, `remove_steps_from_flow`, `list_action_types`, `list_action_type_inputs`, `list_action_type_outputs`, `list_flow_io`, `list_flow_logic_types`, `list_trigger_types`, `get_flow_execution_history` (`sys_hub_flow_context`). All target OOB Flow Designer tables (`sys_hub_*`).
- `f73e174` — **`integration_tools.py`** with 11 tools (Phase 1 integration platform).
- `73ef158` + `9cf2935` — Transform map tools and `run_import` tool.
- `2060d96` — `update_scheduled_job` and `run_scheduled_job_now`.
- `874da3b` + `b329fae` — UI policy write tools, enable/disable client scripts, enable/disable UI actions.
- `bff6499` + `be3fb17` + `ed86237` — Agile additions: `list_releases`, `get_project`, `list_sprints`. (`rm_release`, `pm_project`, `rm_sprint` are OOB.)
- `a1f3579` — `agile_constants.py` extracting shared StoryIdParams and state constants.
- `3945fdf` — Introspection tools for table metadata and field discovery.
- `f119d9b` + `d709803` — Bug fix: missing `os, asyncio, threading` imports in `script_tools` (with regression tests).
- `cfd485d` + `a91ec7e` + many siblings — Integration test suites for incidents, catalog, stories, change requests, user management, agile, customization, script includes, RITM variables, risk, sprint planning, CMDB CIs, scrum tasks, etc. Even after dropping their integration-test gate (already covered above), the *test patterns themselves* are reusable — they show how to structure read-only integration tests against a live PDI.
- `28b80a1` — **CSRF extraction + `X-UserToken` header + redirect guard** for UI session auth. Bug fix likely applicable.

**Patterns worth porting (SEMI-GENERIC, needs adaptation).**

- `f89d2c1` — **Three-tier script execution (trigger / api / ui)** with `fix_script` generation. Solves real ServiceNow operational problem (running ad-hoc scripts safely). Clean pattern; likely adaptable.
- `85843bf` — **Background script guardrails** — require justification + update-set bypass acknowledgement. Pattern is generic; the specific approval-payload format is Flowbie-specific.
- `cc46287` + `0e96ea6` + `9abb41e` — **Approval gate for write tools.** The *concept* of "writes go through an approval flow" is generic and aligns with our north-bound auth scope-checking idea. Their *implementation* couples to a "workbench" they've built.
- `2dc0a27` — **Default tool package change `'full'` → `'executor'`.** They added an executor package; the default-change is Flowbie-specific. We keep echelon's defaults.
- `146159d` — **Table tools with dual-mode identifier resolution** and structured response envelope. Builds on the `identifier_resolver` and `SnowResponse` patterns above.

**Skip (ENV-SPECIFIC or otherwise unfit).**

- `4c57dc3` + `486cfb0` + `b48...` — **Workbench UI tools / `workbench_tools` module** — Flowbie's own product surface. Skip entirely.
- `6148027` + `5b50028` + `f90f70c` — **`detect_active_modules` with `module_registry.yaml` (31 modules)** — clever pattern but the registry itself encodes Flowbie's module taxonomy. Skip the registry; the *idea* of a module-detection tool is portable.
- The big **CRUD-strip refactor** sequence (~15 commits stripping CRUD from tool files in favor of `table_tools`) is a substantial architectural choice. Their direction (generic table tool replaces per-domain CRUD wrappers) has merit, but this is the kind of "rewrite the tools" decision we've explicitly deferred. Don't take this wholesale; revisit during the planned async refactor.
- `ce57c57` — Migrate `changeset_tools` to standard `(config, auth_manager, params)` signature — useful refactor pattern but only after we're committed to the helpers refactor.

**Risks if integrated.**

- Sheer volume — 194 commits is too many to evaluate exhaustively. Accept that some good commits will be missed in the first pass.
- The CRUD-strip refactor breaks API surface — any tool we port from Flowbie *after* that refactor will look different from one ported before. Pick a "before/after" line.
- Their executor-package default is invasive. Avoid pulling the package-config commits as a unit.
- Workbench/approval-gate code has tight coupling to their own platform; very easy to accidentally pull dependencies.

**Bottom line.** **HIGH value but selective.** The infrastructure pieces (`SnowResponse`, identifier resolver, integration-test gate, flow-tools, integration_tools, agile_constants, script-tools imports fix, CSRF fix) are clean cherry-picks. The CRUD-strip refactor and workbench coupling are scope-creep we should skip.

---

### `nathanolds22/servicenow-mcp` (2 ahead)

**Last commit:** 2026-04-07.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...nathanolds22:servicenow-mcp:main

**Summary.** Two large commits, both generated with Claude assistance, both highly valuable. Despite the dramatic naming ("god mode"), all tools target OOB ServiceNow tables (`sn_aia_agent`, `sn_aia_agent_team`, etc. — these are real tables in the ServiceNow AI Agent platform).

**Worth cherry-picking (GENERIC).**

- `ba1f484` — **Comprehensive E2E test suite (111 tests across 6 files)** — covers server lifecycle, package isolation, tool invocation, error handling, session state, configuration. Total suite goes from 206 → 317 tests. Single highest-leverage testing commit observed across all forks.
- `2fc206b` — **AI Agent + WFO + A2A + Agentic Workflow tool suite** targeting:
  - `sn_aia_agent` (AI Agent), `sn_aia_skill`, `sn_aia_topic`, `sn_aia_agent_config`, `sn_aia_team`, `sn_aia_strategy`, `sn_aia_memory` — all OOB AI Agent tables.
  - WFO (Workforce Optimization) — OOB module.
  - A2A (Agent-to-Agent) execution and callback management.
  - Generic table CRUD operations.
  - HTTP client utility and session-state management.
  - "God Mode" = schema discovery + diagnostics + scope/context-switching helpers — generic operational tooling, not branding.

**Risks if integrated.**

- Large diff (2,000+ lines) into already-substantial code; needs careful conflict resolution against torkian's helpers refactor.
- Includes `servicenow_scripts/` directory with deployment helper scripts — review for any hardcoded values before importing.
- "God mode" terminology may need to be renamed for clarity (e.g., `power_tools` or `admin_tools`) but the underlying functionality is generic.

**Bottom line.** **HIGH value — both commits.** The E2E test suite alone justifies the integration effort.

---

### `ericstarkey/servicenow-mcp` (2 ahead)

**Last commit:** 2026-02-24.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...ericstarkey:servicenow-mcp:main

**Summary.** Two commits implementing a complete production-deployment story: Docker Compose + Nginx with self-signed SSL, plus inbound API key middleware for `server_sse.py`. Directly overlaps with our planned static-bearer-token from echelon's `fix/sse-auth-hardening`, but goes further — adds Compose orchestration and TLS termination.

**Worth cherry-picking (GENERIC).**

- `71e10d2` — Single feature commit containing:
  - **`ApiKeyMiddleware`** for `server_sse.py` (validates `Authorization: Bearer` and `X-API-Key` headers).
  - **`create_config_from_env()`** supporting basic / oauth / api_key auth types — a missing piece in echelon's config.
  - **`docker-compose.yml`** + **Nginx config** for production VPS deployment.
  - **`nginx/generate-certs.sh`** for self-signed SSL.
  - **`DEPLOYMENT.md`** step-by-step guide.
  - **22-test suite** for middleware, config builder, integration.

**Risks if integrated.**

- Their `ApiKeyMiddleware` overlaps with — and may conflict with — echelon's `SecurityMiddleware` from `fix/sse-auth-hardening`. Pick one as the canonical inbound auth, or layer them cleanly. Echelon's hardening branch goes further on DNS-rebinding/CSRF defenses; ericstarkey's adds the API-key envelope. Best outcome: merge hardening branch first, then layer ericstarkey's API-key support on top with their tests.
- Their `server_sse.py` is heavily modified (255 → 510 lines) — substantial conflict surface with the hardening merge.

**Bottom line.** **HIGH value — port after the hardening merge.** Resolve conflicts deliberately; the deployment artifacts (Compose, Nginx, DEPLOYMENT.md) and the `create_config_from_env` helper are clean wins independent of the auth-middleware question.

---

### `chan4lk/servicenow-mcp` — `streamable-http` branch

**Compare:** `chan4lk:servicenow-mcp:streamable-http` vs `echelon-ai-labs:servicenow-mcp:main`

**Summary.** The `main` branch has only three small commits ("add run command" twice, plus an upstream merge), but the `streamable-http` branch contains a feature commit `1d2b689` that adds Streamable-HTTP support to `server_sse.py`'s `/mcp` endpoint, plus an `e8e4e4e` "add oauth" commit. Directly addresses our deferred SSE → Streamable-HTTP migration goal.

**Worth studying for the future-phase migration.**

- `1d2b689` — Streamable-HTTP support added for `/mcp` endpoint. ~70 lines of `server_sse.py` changes plus README.
- `e8e4e4e` — "add oauth" — adds `verify_oauth.py` and modifies `server_sse.py`. Worth examining when we get to the OAuth 2.1 north-bound phase.

**Skip.**

- `copilot_agent_instructions.md`, `copilot_instructions_short.txt`, `copilot_service_desk_instructions.md` — Microsoft Copilot Studio integration docs, env-specific.
- `render.yaml` — Render.com deployment config, env-specific.

**Risks.** The implementation predates the MCP spec's formal Streamable-HTTP definition, so it may need updating against the current spec when we get to that phase.

**Bottom line.** **HIGH value but future-phase.** Tag for the deferred Streamable-HTTP migration; don't merge into main now.

---

### `klapom/servicenow-mcp` (13 ahead)

**Last commit:** 2026-04-23.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...klapom:servicenow-mcp:main

**Summary.** Mixed bag. Two strong generic contributions (platform-admin tools, data-integration tools) and several environment-specific ones (Neo4j graph traversal, BGE-M3 embeddings, FastMCP rewrite).

**Worth cherry-picking (GENERIC).**

- `295e39b` — **Platform-admin tools** — six new tool modules: `business_rule_tools` (CRUD on `sys_script`), `oauth_tools` (`oauth_entity` etc.), `rest_message_tools` (`sys_rest_message`), `scheduled_job_tools` (`sysauto_script`), `sys_dictionary_tools` (schema/dictionary ops), `table_api_tools` (generic Table API). All target OOB tables.
- `8c4b817` — **Data-integration tools** — `list_import_sets`, `list_data_sources`, `list_import_runs`, `trigger_import`, `list_transform_maps`, `get_transform_map`, `list_field_mappings`, `list_transform_scripts`, `list_scheduled_imports`, `clone_import_configuration`. OOB tables.

**Skip (ENV-SPECIFIC).**

- `2391dca` — **B8 FastMCP port + mcp-toolkit-py adoption** — a complete framework rewrite. Out of scope and conflicts with the echelon low-level SDK pattern we're keeping.
- `f6b6980` + `5e0e3bb` + `c376d21` — **ServiceNow Knowledge RAG with 4-signal retrieval / BGE-M3 embeddings / embed-proxy** — requires their RAG infrastructure.
- `7cf34e1` + `51164a3` + `6a8...` + `4ef6aa3` + `9b888c1` — **`graph_traverse` / Neo4j graph extraction / live SN schema pipeline** — requires Neo4j infrastructure.
- `b7d1938` + `7cf34e1` — Customization architecture/best-practices docs may contain klapom-specific FNT references.

**Risks if integrated.** Their `tool_packages.yaml` adds `fnt_integration` package — clearly internal. Check that the platform-admin and data-integration commits don't include `fnt_integration` references.

**Bottom line.** **MEDIUM value — port the two utility commits, skip the RAG/graph/FastMCP work.**

---

### `patricebechard/servicenow-mcp` (4 ahead)

**Last commit:** 2026-02-24.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...patricebechard:servicenow-mcp:main

**Summary.** Four small, focused, all-generic commits from a ServiceNow employee. Every commit looks production-ready.

**Worth cherry-picking (GENERIC).**

- `686cbbe` — Support `EXTRA_HTTP_HEADERS` env var (JSON dict) in `AuthManager.get_headers()` — eliminates the need for monkey-patching to add corporate proxies, traceability headers, etc.
- `a102298` — Prefer `SERVICENOW_EXTRA_HTTP_HEADERS` over `EXTRA_HTTP_HEADERS` (more namespaced), keep the older one as fallback.
- `48b0915` — **Move `tool_packages.yaml` into the Python package** so it's included in `pip install`-built wheels. Important fix — without this, pip-installed servers crash because the tool registry can't find its config.
- `b9c8e77` — Upgrade `mcp` dependency.

**Bottom line.** **MEDIUM-HIGH value — take all four.** The `tool_packages.yaml` package-data fix is a quietly-important correctness fix.

---

### `russ430/servicenow-mcp` (4 ahead)

**Last commit:** 2026-01-20.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...russ430:servicenow-mcp:main

**Summary.** Four commits adding Service Portal widget tools (the `sp_widget` table is OOB Service Portal). Author email is `@servicenow.com`. Looks generic.

**Worth cherry-picking (GENERIC).**

- `273419d` — `create_widget`, `update_widget`, `get_widget` (search by sys_id or name).
- `cd1587e` — Register widget tools in `tool_packages.yaml`.
- `197bc9a` — Update widget parameter for server script.
- `307aa85` — Tests + README for widget utils.

**Bottom line.** **MEDIUM value.** Clean Service Portal widget support; portable as-is.

---

### `dobromirmontauk/servicenow-mcp` (4 ahead)

**Last commit:** 2026-03-04.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...dobromirmontauk:servicenow-mcp:main
**Branches of interest:** `csm-tools-generic` (the branch name itself signals their intent).

**Summary.** Two commits adding CSM (Customer Service Management) tools. Commit message references "Mashgin business entities" but the underlying tables are all OOB ServiceNow CSM tables (`customer_account`, `cmn_location`, `sn_install_base_sold_product`, `sn_customerservice_case`, `task`).

**Worth cherry-picking (GENERIC) with rebrand.**

- `ae45885` — CSM tools: `list_accounts`, `list_locations`, `list_products`, `get_cases_by_account`, `get_cases_by_location`, `get_cases_by_product`, `get_cases_by_integration`, `get_case_history`, plus prerequisite case tools (`list_cases`, `get_case_by_number`, `search_cases`).
- `cdecbe1` — `CLAUDE.md` and CSM docs in README. Their `CLAUDE.md` may have Mashgin-specific content; review before importing.

**Risks if integrated.** Commit message language ("Mashgin business entities", "401 workaround") implies the author was working around access restrictions in their tenant. The text-search workaround code is fine generically (works against any tenant where direct access is restricted), but the comments should be sanitized.

**Bottom line.** **MEDIUM value — take the code, sanitize the framing.** Rename "Mashgin" references in commit messages/comments before integrating.

---

### `haim-nizri/servicenow-mcp` (3 ahead)

**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...haim-nizri:servicenow-mcp:main

**Summary.** Three commits, of mixed value. The Scripted REST API tools are clean and generic; the NowLLM chatbot is large and out-of-scope; the xti namespace fix is environment-specific.

**Worth cherry-picking (GENERIC).**

- `e9c8dd0` — **Scripted REST API tools**: `create_scripted_rest_api` (creates `sys_ws_definition`), `create_scripted_rest_resource` (creates `sys_ws_operation`). Both target OOB tables. Closes the "real ServiceNow installs run `/api/<scope>/...` endpoints alongside OOB" gap from our own analysis.
- `f546c78` — Tests for the Scripted REST tools.

**Skip.**

- `473e573` — "Fix default NowLLM API path to use xti namespace" — `/api/xti/nowllm_chat/generate` is application-scope-specific. The 648-line `chatbot.py` it adds is a separate web chat interface — out of scope for an MCP server.

**Bottom line.** **MEDIUM (selective) value.** Take the two Scripted REST commits; skip the chatbot.

---

### `Kalppatel000/servicenow-mcp` (3 ahead)

**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...Kalppatel000:servicenow-mcp:main

**Summary.** Three commits adding "SessionBridge" — a zero-credential auth mechanism that reads browser session cookies + CSRF tokens written by a SessionBridge Chrome extension. Author email `@servicenow.com`. The pattern is interesting but the dependency on a specific Chrome extension makes it semi-generic.

**Pattern worth studying (SEMI-GENERIC).**

- `2de69cf` — `session_bridge` auth type that reads `~/.sessionbridge/<domain>/session.json`.
- `5e5e2ca` — Auto-discover instance URL from SessionBridge session files.
- `f733d83` — Documentation.

**Risks if integrated.** Tied to a specific external Chrome extension. Adoption requires users to install that extension. Better as a documented pattern than a hard dependency.

**Bottom line.** **STUDY-ONLY.** Note as a future option for "session piggyback auth"; don't port wholesale.

---

### `clguo-tw/servicenow-mcp` (2 ahead)

**Worth cherry-picking (GENERIC).**

- `aad5100` — Add filter by updated time range to `list_incidents`.
- `7f9dc92` — Add filter by assignment group to `list_incidents`.

**Bottom line.** **LOW-MEDIUM value.** Small, surgical incident filter additions. Can probably be subsumed by a more general filter expansion in the same area.

---

### `natedolor/servicenow-mcp` (1 ahead)

**Worth cherry-picking (GENERIC).**

- `cb0db5b` — Expanded list_incidents filters (more parameters).

**Bottom line.** **LOW-MEDIUM.** Same theme as clguo-tw — should be folded together when expanding incident filtering.

---

### `fromnewcoder/servicenow-mcp` (1 ahead)

- `c1eaac2` — `add install guidance` — README docs.

**Bottom line.** **LOW.** Review for any genuinely generic install tips; merge selectively into our own README.

---

### `jonathan-f-spencer-usps/servicenow-mcp` (2 ahead, 8 behind)

- `139806a` — `Create dependabot.yml` (already covered better by torkian's `7cfaacd`).
- `0b10db4` — Merge from `osomai:main` (legacy, predates echelon).

**Bottom line.** **LOW.** Dependabot config superseded by torkian.

---

### `Nayef-Abou-Tayoun/servicenow-mcp` (5 ahead)

**All commits add `u_*` custom fields specific to one IBM-internal incident schema.**

- `654c7f1` — `u_final_severity_score`
- `8560349` — `u_context_environment_impact_score`, `u_context_notes`, `u_context_score`, `u_incident_priority`
- `9b18f2e` — `u_network_quality_score`, `u_network_quality_interpretation`
- `22387cb` — `u_customer_impact_note0`
- `a3a37bc` — `u_area`

**Bottom line.** **SKIP.** The *pattern* of supporting custom fields is generic — but the right answer is a generic "custom fields" extension mechanism (e.g., schema-driven field discovery from `sys_dictionary`), not hardcoded `u_*` constants for one tenant.

---

### `FredM-AI/servicenow-mcp` (51 ahead)

**51 commits of deploy churn.** Includes a `server_sse.py` → `server_see.py` typo-rename (note "see" not "sse") that propagates through 22 subsequent "Update server_see.py" commits. Heroku Procfile, mcp.json deploy variants, repeated start.py/main.py renames.

**Bottom line.** **SKIP entirely.** The typo-rename alone would be a regression. Nothing of substance to port.

---

### `jschuller/servicenow-mcp` (1 ahead, 8 behind)

- `552261d` — Single merge commit from `osomai:main`. No original work.

**Bottom line.** **SKIP.**

---

## Cross-cutting themes

Patterns that appear in multiple forks reveal what's broken or missing in echelon's main and where our own playbook is on the right track.

### 1. Multiple forks independently fixed the OAuth body-logging bug

- `torkian` `ba56b83`
- Our own playbook commit 3

**Implication.** Strong validation that this is a real, widely-noticed security issue worth upstreaming to echelon.

### 2. Multiple forks expanded inbound auth on `server_sse.py`

- `ericstarkey` `71e10d2` (ApiKeyMiddleware)
- echelon's own `fix/sse-auth-hardening` (`c77861e`) — bearer token + Host/Origin allowlist
- `chan4lk/streamable-http` `e8e4e4e` (oauth)
- Our own planned static-token floor (from echelon hardening)

**Implication.** Inbound auth is consistently identified as the highest-priority gap. Multiple convergent solutions exist; the right merge order is hardening branch first, then ApiKeyMiddleware on top.

### 3. Multiple forks added a tool_packages.yaml correctness fix

- `patricebechard` `48b0915` — package-data fix for pip installs
- `torkian` `3cb44bd` — Dockerfile fix to include config directory
- `torkian` `84e10ac` — comment out 11 ghost tools that don't exist in code

**Implication.** echelon's packaging story is broken in multiple ways for both pip and Docker users.

### 4. Multiple forks targeted the same retry/rate-limit/pagination gaps

- `torkian` solves all three in `7c5d87e`, `fa39ca3`, `8415b42`
- Our own analysis flagged all three as gaps

**Implication.** torkian's implementation is the fastest path to closing them; we don't need to write our own.

### 5. Multiple forks expanded incident filter coverage

- `clguo-tw` (assign group, time range)
- `natedolor` (more parameters)
- `Nayef` (custom fields, env-specific)

**Implication.** echelon's `list_incidents` filter set is thin. Worth a deliberate "expand list_X filtering uniformly" pass.

### 6. Multiple forks added new domain tool families that target OOB tables

| Domain | Source | OOB? |
|---|---|---|
| CMDB CIs + relationships | torkian | Yes (`cmdb_ci`) |
| Asset / asset contract | torkian | Yes (`alm_asset`, `ast_contract`) |
| SCTASK + time card | torkian | Yes (`sc_task`, `time_card`) |
| Syslog | torkian | Yes (`syslog`) |
| AI Agent / WFO / A2A | nathanolds22 | Yes (`sn_aia_*`) |
| Flow Designer (deep) | Flowbie | Yes (`sys_hub_*`) |
| Service Portal widgets | russ430 | Yes (`sp_widget`) |
| CSM | dobromirmontauk | Yes (`customer_account`, `sn_customerservice_case`) |
| Scripted REST API | haim-nizri | Yes (`sys_ws_definition`, `sys_ws_operation`) |
| Platform admin (BR / OAuth / REST messages / scheduled jobs / dictionary / table API) | klapom | Yes |
| Data integration (import sets / transform maps) | klapom + Flowbie | Yes |

**Implication.** echelon's ~82-tool surface can plausibly grow to 200+ from these forks alone, all targeting OOB tables — no env-specific hacks needed.

### 7. Multiple forks added test infrastructure

- `nathanolds22 ba1f484` — 111 E2E tests
- `Flowbie 0199475` — integration-test gate
- `torkian` — 258 tests at 80% coverage with Codecov
- `ericstarkey 71e10d2` — 22 middleware/auth tests

**Implication.** Testing is the second-most-converged-on improvement area after auth. Our CI commit (playbook commit 9) should adopt torkian's pattern wholesale rather than rolling our own.

### 8. The `osomai` org appears as a common ancestor

`jschuller`, `jonathan-spencer`, `torkian`, and even echelon's own early history reference `osomai/servicenow-mcp` — apparently the original pre-echelon predecessor. Worth being aware of when reading commit graphs but no direct integration impact.

---

## Recommended cherry-pick order

After completing our own currently-planned playbook commits (the CLAUDE.md-documented work through commit 9), the next-phase integration order should be:

1. **`torkian cb727c0`** — helpers refactor first (foundation for everything else from torkian).
2. **`patricebechard 48b0915`** — `tool_packages.yaml` package-data fix (correctness).
3. **`torkian 84e10ac`** — comment out 11 ghost tools.
4. **`torkian 3cb44bd`** — Dockerfile fix to include config dir.
5. **`torkian 264b048`** — strip tracked `.DS_Store`.
6. **`torkian 8415b42`** — pagination helpers.
7. **`torkian 7c5d87e`** — retry/exponential backoff.
8. **`torkian fa39ca3`** — rate-limit awareness.
9. **`torkian a091ae0`** — bulk batch API.
10. **`torkian ab3959f` + `2f3f80c` + `20eebc2`** — input validation, error messages, debug logging.
11. **`Flowbie 7aa4181`** — SnowResponse envelope.
12. **`Flowbie 1ad7272`** — identifier resolver.
13. **`Flowbie 0199475`** — integration-test gate.
14. **`patricebechard 686cbbe` + `a102298`** — EXTRA_HTTP_HEADERS support.
15. **`torkian` CMDB / asset / SCTASK / time card / syslog / catalog / user-criteria / UI-policy commits** — expand tool surface (cluster these).
16. **`nathanolds22 ba1f484`** — E2E test suite (after the helpers refactor settles).
17. **`nathanolds22 2fc206b`** — AI Agent / WFO / A2A tools.
18. **`klapom 295e39b` + `8c4b817`** — platform-admin and data-integration tools.
19. **`Flowbie` Flow Designer cluster** — large, port as a coordinated unit.
20. **`Flowbie` integration-test corpus** — port test patterns after their gate is in.
21. **`russ430` + `dobromirmontauk` + `haim-nizri (selective)`** — domain tools (widgets, CSM, Scripted REST).
22. **`ericstarkey 71e10d2`** — Docker Compose + ApiKeyMiddleware (after our own hardening merge).
23. **`chan4lk/streamable-http`** — defer to the SSE → Streamable-HTTP migration phase.

Numbers 1–10 are foundational and should land as a coherent set before the domain expansions (11+).

---

## Outreach considerations

Several of these forks contain genuinely upstream-worthy fixes that echelon would likely accept:

- `torkian ba56b83` (OAuth body logging) and our own equivalent.
- `torkian 7cfaacd` (CI/CD setup).
- `torkian 84e10ac` (ghost tool cleanup).
- `patricebechard 48b0915` (pip package-data fix).
- `torkian 3cb44bd` (Dockerfile config-dir fix).

Worth opening upstream PRs to echelon for these regardless of whether we cherry-pick them locally first. They're community-benefiting fixes, and PRs strengthen our position in echelon's fork network.

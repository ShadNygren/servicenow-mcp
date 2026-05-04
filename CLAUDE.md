# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

This repo is a GitHub fork of `echelon-ai-labs/servicenow-mcp` with full upstream history preserved. The `origin` remote is `git@github.com:ShadNygren/servicenow-mcp.git`; the `upstream` remote points to `https://github.com/echelon-ai-labs/servicenow-mcp.git`. The `fix/sse-auth-hardening` branch is also tracked from origin.

In addition to `origin` and `upstream`, the local repo has 18 fork remotes (`torkian`, `Flowbie`, `FredM-AI`, `klapom`, `Nayef`, `nathanolds22`, `patricebechard`, `russ430`, `dobromirmontauk`, `chan4lk`, `Kalppatel`, `haim-nizri`, `ericstarkey`, `clguo-tw`, `jonathan-spencer`, `natedolor`, `fromnewcoder`, `jschuller`) configured for cherry-picking. Run `git fetch --all` to refresh.

## Three planning documents (read these first)

1. **`ANALYSIS_OF_EXISTING_OPEN_SOURCE_SERVICENOW_MCP_SERVERS.md`** — original architectural rationale comparing echelon, michaelbuckner, anilvaranasi, and the proposed best-of-breed unified server. Contains the original 9-commit "phase 1" execution playbook.
2. **`ANALYSIS_OF_ECHELON_AI_LABS_SERVICENOW_MCP_FORKS.md`** — fork survey of 18 active forks with verdicts (cherry-pick / port-pattern / study-only / skip) and a 23-step recommended cherry-pick order.
3. **`ANALYSIS_OF_ECHELON_AI_LABS_PRS_AND_ISSUES.md`** — review of 15 open PRs and 13 open issues at echelon. Identifies which PRs should be merged into our fork, which security findings (Issue #43) require immediate action, and where open PRs validate or supersede our planned commits.

The integrated phased plan below is the current canonical execution order, superseding the original 9-commit playbook (which is now only phase 1).

## Licensing

The project stays under **MIT** (matching both upstream MIT-licensed sources). Both echelon's and michaelbuckner's copyright notices must be preserved in `NOTICE` and the relevant `LICENSE-*` files. **Do not relicense to Apache-2.0 or any other license** without explicit user direction — this decision was discussed and resolved in favor of MIT.

## Integrated phased execution plan

### Phase 1 — Security baseline + auth hygiene (original playbook)

Adapted from the original playbook's 9 commits, with mid-flight refinements from PR/issue analysis.

1. **README rewrite + NOTICE preserving MIT attribution from echelon and michaelbuckner.** Include warnings flagged by Issue #43 (plaintext password risk, password-grant deprecation).
2. **Stop logging OAuth response bodies.** Validates PR #59 (alexzadeh) and torkian `ba56b83`. Open as upstream PR after landing.
3. **Fix hardcoded `.service-now.com` in OAuth token URL.** Adopt PR #31 (jessems) approach — pass `instance_url` to `AuthManager` constructor, not via `oauth_config`. Open as upstream PR.
4. **Merge `origin/fix/sse-auth-hardening`** as a real merge commit (preserves `c77861e` authorship). Resolves Issue #43 finding #4 (0.0.0.0 default binding).
5. **OAuth token refresh-on-expiry with type-safe datetime tracking.** Use michaelbuckner's pattern, fix the datetime-vs-float bug. PR #42 (rangamani54) is an alternative if michaelbuckner's pattern fails.
6. **Schema-discovery resources** (`servicenow://tables`, `servicenow://schema/{table}`). Port from michaelbuckner with 5-minute TTL cache.
7. **Port michaelbuckner NLPProcessor** as `nl_power_user` opt-in package.
8. **GitHub Actions CI matrix** (Python 3.10–3.13) — but adopt torkian's CI/CD setup (`7cfaacd` + Codecov v5 + CodeQL + Dependabot) instead of rolling our own.
9. **Issue #43 finding #1 mitigation — IMMEDIATE.** Remove `execute_script_include`, `create_script_include`, `update_script_include`, `delete_script_include` from default `platform_developer` and `full` packages. Document the security rationale in README.

### Phase 2 — Fork-driven foundations (torkian + supersedes)

Land these together as a coherent set; numbers 1–4 are foundational and gate later domain expansions.

1. **`torkian cb727c0`** — extract shared helpers into `utils/helpers.py` (-740 lines duplication). Foundation for everything.
2. **PR #46 (sam-at-luther)** — uvx-compatible packaging: move `config/` → `src/servicenow_mcp/config/`, fix wheel inclusion, use `importlib.resources`. **Supersedes `patricebechard 48b0915`** (same problem, more thorough).
3. **`torkian 84e10ac`** — comment out 11 ghost tools in `tool_packages.yaml`.
4. **`torkian 264b048`** — strip tracked `.DS_Store`.
5. **`torkian 8415b42`** — pagination helpers (`_build_sysparm_params`, `_join_query_parts`, `_paginated_list_response`).
6. **`torkian 7c5d87e`** — retry logic with exponential backoff.
7. **`torkian fa39ca3`** — rate-limit awareness via `RateLimitTracker` (parses `X-RateLimit-*` headers).
8. **`torkian a091ae0`** — bulk operations via `/api/now/v1/batch`.
9. **`torkian ab3959f`** — input validation for date/datetime/duration fields.
10. **`torkian 2f3f80c`** — improved error messages across all tools.
11. **`torkian 20eebc2`** — request/response logging in debug mode (with redaction).

### Phase 3 — Security + open-PR convergence

1. **PR #51 (dasarunava97)** — client-credentials OAuth as primary, configurable `api_path`. Resolves Issue #43 finding #2 (password-grant insecurity) and Issue #50.
2. **Pydantic v2 fix (Issue #26)** — convert `OptimizationRecommendationsParams` + `UpdateCatalogItemParams` from dataclass to `BaseModel`. Verify torkian/Flowbie didn't already fix it.
3. **`patricebechard 686cbbe` + `a102298`** — `EXTRA_HTTP_HEADERS` env-var support.
4. **README security warnings (Issue #43 finding #3)** — flag plaintext password in `claude_desktop_config.json`, recommend env-var-only config; deprecate `install_claude_desktop.sh` as default install path.
5. **Install-path documentation (Issue #49)** — document venv-aware Claude Desktop config and `uvx` install path.

### Phase 4 — Infrastructure utilities

1. **`Flowbie 7aa4181`** — `SnowResponse` structured envelope for consistent tool output. Solves the LLM-error-transparency issue from our analysis.
2. **`Flowbie 1ad7272`** — identifier resolver (ticket-number → sys_id).
3. **`Flowbie 0199475`** — integration-test gate (`SN_INTEGRATION_TESTS=1`).

### Phase 5 — Domain expansion (large)

Order matters — earlier items are infrastructure for later items.

1. **`torkian` CMDB cluster** (`01bf610` + `7f01fe5`) — `cmdb_ci`, `cmdb_rel_ci`. Closes Issue #45.
2. **`torkian` asset cluster** (`067a3c5` + `b20ef77` + `8c93107`) — `alm_asset` / `alm_hardware`.
3. **`torkian` asset contract cluster** (`f7ab804` + `6b3756f`) — `ast_contract`.
4. **`torkian b544f7b`** — SCTASK + time card tools (`sc_task`, `time_card`).
5. **`torkian bfec67b`** — syslog tools.
6. **`torkian` user-criteria + UI-policy** (`5587eae`, `ae3b91b`, `482eb4c`, `fa7e54d`) — `sys_user_criteria`, `sys_ui_policy`.
7. **`torkian` catalog cluster** (`657c4f0`, `5037840`, `12479b5`) — choices, deletions, create_catalog_item. Closes PR #60.
8. **`torkian 6881ddb`** — `execute_script_include` tool — gated behind explicit security-aware package, NOT in defaults (per Issue #43 finding #1).
9. **PR #37 (debianmaster)** — `get_incident_by_number` registration. Trivial, fold into a cleanup commit.
10. **Issue #52** — new `get_incident_journal` tool querying `sys_journal_field` for work_notes/comments timeline.
11. **`clguo-tw` + `natedolor`** — incident filter expansions (assignment_group, time range, more parameters). Closes Issue #54.
12. **`russ430`** — Service Portal widget tools (`sp_widget`).
13. **`dobromirmontauk`** — CSM tools, sanitize "Mashgin" framing.
14. **`haim-nizri`** Scripted REST API tools (selective — skip chatbot.py and xti namespace fix).
15. **PR #56 (31-rat4)** — ACL tools (`sys_security_acl`, `sys_user_role`, `sys_security_attribute`). Selective — skip test-removal commits.
16. **`klapom 295e39b`** — platform-admin tools (`business_rule_tools`, `oauth_tools`, `rest_message_tools`, `scheduled_job_tools`, `sys_dictionary_tools`, `table_api_tools`).
17. **`klapom 8c4b817`** — data-integration tools (import sets, transform maps, scheduled imports).
18. **`Flowbie` Flow Designer cluster** — coordinated unit (~25 commits).
19. **`Flowbie f73e174`** — integration_tools (Phase 1).
20. **`nathanolds22 ba1f484`** — comprehensive E2E test suite (111 tests).
21. **`nathanolds22 2fc206b`** — AI Agent / WFO / A2A tools (rename "god mode" to `power_tools` or `admin_tools` for clarity).

### Phase 6 — Deployment + production

1. **`ericstarkey 71e10d2`** — Docker Compose + Nginx + ApiKeyMiddleware (resolve conflicts with the hardening branch in favor of layered auth: hardening's bearer-token at the network edge, ericstarkey's API-key for client identity).
2. **PR #36 subset (xiangshen-dk)** — `/health` endpoint for container deployments. Skip the Cloud-Run-specific deploy scripts (move to `docs/deploying-to-gcp.md`).
3. **`torkian 3cb44bd`** — Dockerfile fix (already addressed by ericstarkey; verify).
4. **README rewrite** — comprehensive, with deployment guide, security warnings, install paths, all tool packages documented.
5. **`torkian c12aaec`** — PR / issue templates, CONTRIBUTING.md, SECURITY.md.

### Phase 7 — Streamable HTTP transport migration ✅ DONE

The MCP spec deprecates SSE in favor of Streamable HTTP (single endpoint that supports both request/response and server-pushed streaming over chunked HTTP).

**Shipped on the `phase-7-streamable-http` branch:**

1. ✅ `src/servicenow_mcp/server_http.py` — Streamable HTTP server using `mcp.server.streamable_http_manager.StreamableHTTPSessionManager`. Single `/mcp` endpoint replaces the dual `/sse` + `/messages/` shape.
2. ✅ `src/servicenow_mcp/event_store.py` — In-memory event store for resumability (per spec).
3. ✅ `src/servicenow_mcp/transport_security.py` — Extracted `SecurityMiddleware` + helper functions (`is_loopback_host`, `resolve_auth_token`, `build_allowed_hosts`, `build_allowed_origins`) to a shared module that any HTTP transport can use.
4. ✅ `servicenow-mcp-http` console script (`pyproject.toml`).
5. ✅ Same security posture as the retired SSE transport — bearer token, Host/Origin allowlist, loopback default, `/health` bypass, pure-ASGI streaming-safe middleware.
6. ✅ Comprehensive `tests/test_transport_security.py` (44 tests covering every aspect of `SecurityMiddleware` + helper functions independently of any specific transport).
7. ✅ `tests/test_server_http_integration.py` (8 tests for the HTTP transport's wiring).
8. ✅ SSE entirely removed: `server_sse.py`, `tests/test_server_sse*.py` deleted; `servicenow-mcp-sse` console script removed; nginx config rewritten for `/mcp` only.
9. ✅ README, DEPLOYMENT.md, `.env.example` updated with the migration table.

Reference implementation: `ibeketov/servicenow-mcp:main:server_http.py` (MIT-licensed) — used as the structural reference for the `StreamableHTTPSessionManager` integration. Our version layers our `SecurityMiddleware` on top (ibeketov's was unhardened).

### Phase 8 — Unify on FastMCP, retire `tool_utils.py` registry ✅ DONE

Goal: replace `mcp.server.lowlevel.Server` with `FastMCP` for both stdio (`cli.py`) and Streamable HTTP (`server_http.py`) transports.

**Shipped on the `phase-8-fastmcp` branch:**

1. ✅ `src/servicenow_mcp/server.py` rewritten — `ServiceNowMCP` now wraps a `FastMCP("ServiceNow")` instance. Manual `_list_tools_impl` / `_call_tool_impl` handlers gone (FastMCP provides them). `start()` returns the `FastMCP` instance instead of a low-level `Server`.

2. ✅ `src/servicenow_mcp/utils/fastmcp_adapter.py` — new `register_tool()` helper that builds a thin wrapper per tool: captures `config` + `auth_manager` in closure, dynamically constructs an `inspect.Signature` mirroring the params model's fields with `Annotated[T, FieldInfo]` so FastMCP's schema generator picks up `Field(description=, ...)` metadata. Result: flat field-level JSON Schema per tool, underlying tool functions unchanged. **No 200-tool rewrite required.**

3. ✅ `MCP_TOOL_PACKAGE` filtering preserved — selection happens at *startup* (before `add_tool` runs), same UX, simpler internals. The introspection tool `list_tool_packages` is registered via `@mcp.tool` like everything else.

4. ✅ `cli.py` uses `mcp.run_stdio_async()` — replaces the manual `stdio_server()` + `server.run()` dance.

5. ✅ `server_http.py` mounts FastMCP's `streamable_http_app()` at the root and adds `/health` at the same level. The outer Starlette inherits the inner app's lifespan, so the FastMCP session manager starts/stops with uvicorn. Our hardened `SecurityMiddleware` still wraps everything (bearer + Host + Origin + loopback default + body redaction).

6. ✅ Schema-discovery resources (`servicenow://tables`, `servicenow://tables/{table}`, `servicenow://schema/{table}`) registered with FastMCP's `@resource` decorator pattern. Template URIs flow through `SchemaResources.read`.

7. ✅ `mcp_server` attribute kept as a property aliasing `mcp` for backward compatibility.

8. ✅ Dead test files (`test_server_catalog.py`, `test_server_workflow.py`, `test_workflow_tools_direct.py`) deleted — they tested an even-older shape and had been on `collect_ignore` since the fork started.

9. ✅ Unused `serialize_tool_output` removed from `server.py` (FastMCP handles return-value serialization).

**Test status: 935 passing, ruff clean, mypy clean.** Tool registry (`tool_utils.py`) is still on disk as the canonical list of tools — keeping it as the central definition is the cleaner path; what we eliminated was the *manual server wiring* around it.

**Deferred to Phase 8.5 (optional, not blocking):** decorator-on-each-tool-function pattern (`@mcp.tool()` directly on every tool implementation). The current adapter approach gives us all the FastMCP benefits without touching every tool file; the per-tool decorator migration would be cosmetic and would touch 200+ files. Worth doing only if there's demand for the "drop a file in `tools/<domain>/`, decorate, done" experience.

**Why FastMCP-everywhere is the right end state:**

| Concern | Status |
|---|---|
| CVE / patching cadence | No differential — `lowlevel.Server` and FastMCP ship in the same `mcp` Python SDK and patches cover both. Confirmed during Phase 1 planning. |
| ServiceNow-specific features requiring low-level | None observed. ServiceNow tools are just HTTP requests; both interfaces handle this fine. |
| Custom `tool_utils.py` registry maintenance | Eliminated in Phase 8 — decorators replace it. |
| `MCP_TOOL_PACKAGE` filtering | Reimplementable as decorator metadata; design shape is preserved. |
| Compatibility with cherry-picked fork code | Cherry-picks land in Phases 2-6 against the current low-level shape; Phase 8 migrates all of them at once with a coordinated rewrite. |

### Phase 9 — Async refactor (`requests` → `httpx.AsyncClient`)

FastMCP supports sync tools (runs them in a threadpool), so async refactoring is **not** coupled to Phase 8. After Phase 8 lands, migrate every tool's HTTP client from sync `requests` to `httpx.AsyncClient`, with one shared client per process and connection pooling. Touches every tool file in `tools/`. Meaningful perf win for HTTP transports under concurrent load. Removes the awkward sync-under-async footgun in echelon's current SSE server.

### Phase 10+ — Future / deferred

- **Full MCP-spec OAuth 2.1 north-bound** (Resource Server, JWT validation, JWKS, audience binding per RFC 8707, `/.well-known/oauth-protected-resource` per RFC 9728).
- **RFC 8693 token exchange (OBO)** for end-user attribution to ServiceNow.
- **Pluggable secret stores** (`secrets/vault.py`, `secrets/aws_secrets.py`).
- **OS keyring integration** for credential storage (addresses Issue #43 finding #3 fully).

## Upstream-PR opportunities

After we land each fix, open a PR back to echelon for genuinely community-benefiting items:

- **OAuth body logging fix** (we'd land it; PR #59 already exists — comment in support).
- **Hardcoded `.service-now.com` URL** (PR #31 already exists — comment in support).
- **`tool_packages.yaml` packaging** (PR #46 already exists — comment in support).
- **Issue #43 finding #1 mitigation** — no PR exists; open one. The security finding has been open 8 months without acknowledgment.
- **Pydantic v2 fix (Issue #26)** — community workaround in comments; open a clean PR.
- **`get_incident_by_number` registration** (PR #37 already exists).

Our fork serves as the de-facto reviewed-and-tested version while we advocate upstream.

## Constraints baked into this phase

These are not open questions — explicitly deferred:

- **Do not refactor `requests` → `httpx.AsyncClient`.** Phase 9.
- ~~Do not migrate SSE → Streamable HTTP. Phase 7.~~ **Done (Phase 7 complete on `phase-7-streamable-http` branch).** SSE entirely removed; `/mcp` is the single HTTP endpoint.
- ~~Do not migrate stdio from low-level to FastMCP. Phase 8.~~ **Done (Phase 8 complete on `phase-8-fastmcp` branch).** Both transports now FastMCP-based.
- ~~Do not retire `tool_utils.py` registry. Phase 8.~~ **Partial — server-side wiring around the registry is gone; the registry remains as the canonical tool list. Per-tool decorator migration deferred to optional Phase 8.5.**
- **Do not implement full MCP-spec OAuth 2.1 north-bound.** Phase 10. Static-bearer-token floor (from `fix/sse-auth-hardening`) is the current ceiling.
- **Commit cadence is small and atomic.** Push after each milestone.
- **Stay MIT.** Don't relicense.
- **Stay on the official `mcp` Python SDK** (the package on PyPI named `mcp`). Do not switch to the standalone `fastmcp` 2.x package by jlowin without explicit user direction — committed during Phase 1 planning.
- **End-state architecture is FastMCP-everywhere** (Phase 8). Don't roll our own registry, don't fork the MCP SDK, don't switch frameworks mid-project.
- **anilvaranasi.** Reviewed only — no code copied. Their repo has no LICENSE file.

## Architectural orientation

Two-axis auth separation:

- **North-bound** (MCP client → this server): For HTTP transports, eventually OAuth 2.1 Resource Server per the MCP authorization spec; in this phase, a static bearer token gated by Host/Origin allowlists with loopback default. For stdio, the OS process boundary is the trust boundary.
- **South-bound** (this server → ServiceNow): Basic / API key / ServiceNow OAuth 2.0 (`client_credentials`, `password`, `refresh_token`, `authorization_code`). Eventually RFC 8693 token exchange (OBO) so ServiceNow sees the real end-user when both axes are OAuth-enabled.

Echelon's tool packaging (`MCP_TOOL_PACKAGE` env var + `config/tool_packages.yaml`) is the killer feature being preserved — it lets one server serve many personas without exposing the wrong blast radius to the wrong agent. Per Issue #43 finding #1, **default packages must not include arbitrary-script-execution tools.**

## Bugs from upstream that must not be reintroduced

1. **echelon `auth_manager.py:113,133`** logs OAuth response bodies (containing access tokens) at INFO level. CI log-redaction check fails the build if `access_token` or `Authorization: Bearer` appears in any captured log line.
2. **michaelbuckner `server.py:153` vs `:191`** mixes `datetime` and epoch-seconds for token expiry — comparison raises `TypeError` after the first refresh. Use timezone-aware UTC `datetime` consistently; never `.timestamp()`.
3. **echelon `auth_manager.py:90-94`** hardcodes `.service-now.com` — breaks custom domains. PR #31 has the canonical fix.
4. **`OptimizationRecommendationsParams` + `UpdateCatalogItemParams`** use `@dataclass` but server expects Pydantic `BaseModel`. Issue #26.
5. **`tool_packages.yaml` not bundled in pip wheels.** PR #46 has the canonical fix.
6. **Default Dockerfile binds 0.0.0.0.** Issue #43 finding #4. Fixed by `fix/sse-auth-hardening`.

## Testing against a live ServiceNow instance (PDI)

ServiceNow provides free, fully functional Personal Developer Instances (PDIs) — dedicated sandboxes at URLs like `https://dev12345.service-now.com`. These are the right testing target for integration tests and end-to-end validation.

**Setup.**
1. Sign up at [developer.servicenow.com](https://developer.servicenow.com).
2. Request an instance (the dashboard has a "Request Instance" action). Provisioning takes a few minutes.
3. Note the admin password and instance URL — you'll need them for `SERVICENOW_INSTANCE_URL`, `SERVICENOW_USERNAME`, `SERVICENOW_PASSWORD`.
4. **Keep the instance active** — log in at least once every 10 days, or it will be reclaimed.

**What's installed by default.** PDIs ship with the standard ITSM stack pre-activated (incident, change, problem, knowledge, catalog, CMDB, sys_user, etc.). Some specialized plugins (Agile 2.0, Service Portal extensions, AI Agent platform) need explicit activation via the Plugins UI in the instance.

**Testing flow.**
- **Unit tests** (the default `pytest` run) use mocks via `respx` and never hit a real instance.
- **Integration tests** (Phase 4 — Flowbie `0199475` gate): set `SN_INTEGRATION_TESTS=1` to enable. The gate skips them by default so CI doesn't depend on PDI availability.
- **MCP Inspector** ([github.com/modelcontextprotocol/inspector](https://github.com/modelcontextprotocol/inspector)) — the official debugging UI for MCP servers. Run our server locally, connect Inspector to it, exercise tools manually against the PDI.
- **Claude Desktop** — point `claude_desktop_config.json` at the local server (see install-path notes for Issue #49). Real end-to-end test with the real LLM.
- **REST API Explorer** — built into the PDI itself at `/now/nav/ui/classic/params/target/sys_rest_message.do`. Use it to verify your auth + query syntax before debugging from the MCP layer.

**Auth recommendation for PDI testing.** Use basic auth (admin username/password) for local development — simplest path. OAuth is worth testing later but introduces an extra moving part you don't need while building.

**Future: PDI fixture pattern.** Flowbie's `8eb4be5` commit (in our Phase 4 cherry-pick list) introduces a `live_config` + `pdi_guard` fixture pair that gates integration tests on a configured PDI being reachable. After Phase 4 lands, that's the canonical pattern for new integration tests in this repo.

## Commands

Standard development commands:

```
uv sync --all-extras           # or: pip install -e ".[dev]"
pytest -v                       # full suite
pytest tests/test_<file>.py -v  # single file
pytest -k <pattern> -v          # by name pattern
ruff check .
mypy src/servicenow_mcp         # strict mode is configured in pyproject.toml
```

After Phase 2 lands, `pytest` runs ~258 tests at 80%+ coverage with Codecov uploads.

## Reference clones / remotes

```
upstream  = echelon-ai-labs/servicenow-mcp        # baseline + fix/sse-auth-hardening branch
michaelbuckner/servicenow-mcp                     # cloned locally; NLP, schema, OAuth refresh, CI patterns
anilvaranasi/ServiceNowMCPServer                  # cloned locally; reviewed only — do not copy code
torkian, Flowbie, FredM-AI, klapom, Nayef, nathanolds22, patricebechard,
russ430, dobromirmontauk, chan4lk, Kalppatel, haim-nizri, ericstarkey,
clguo-tw, jonathan-spencer, natedolor, fromnewcoder, jschuller         # remotes for cherry-pick
```

Pinned SHAs:

| Source | Reference | Purpose |
|---|---|---|
| `echelon-ai-labs/servicenow-mcp` | `main` @ `0625060` | Fork base |
| `echelon-ai-labs/servicenow-mcp` | `origin/fix/sse-auth-hardening` @ `c77861e` | SSE hardening — merge as-is |
| `michaelbuckner/servicenow-mcp` | `main` @ `39e0910` | Port: NLP, schema, OAuth refresh patterns |
| `torkian/servicenow-mcp` | `main` (90 ahead, 42 behind, actively maintained) | Phase 2 foundation + Phase 5 domain tools |
| `Flowbie/servicenow-mcp` | `main` (194 ahead) | Phase 4 utilities + Phase 5 flow tools |
| `nathanolds22/servicenow-mcp` | `main` (2 commits) | Phase 5 E2E tests + AI Agent tools |
| `ericstarkey/servicenow-mcp` | `main` (2 commits) | Phase 6 Docker/Nginx/auth |
| `chan4lk/servicenow-mcp` | `streamable-http` branch | Phase 7 future migration |
| `anilvaranasi/ServiceNowMCPServer` | (no LICENSE) | Reviewed only — no code copied |

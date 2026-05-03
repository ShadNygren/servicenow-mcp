# Analysis of Existing Open Source ServiceNow MCP Servers

A comparative review of three open-source ServiceNow MCP server implementations, and a proposal for a unified server that combines the best of each — with **OAuth 2.x support on both axes**: ServiceNow OAuth 2.0 for the server-to-ServiceNow connection, and MCP-spec OAuth 2.1 for the client-to-server connection.

## Repos under review

| Repo | Language | Maturity | Notes |
|---|---|---|---|
| [`echelon-ai-labs/servicenow-mcp`](https://github.com/echelon-ai-labs/servicenow-mcp) | Python (low-level MCP SDK) | Alpha but substantial | Full-featured: 82 tools across 15 domains. Has a `fix/sse-auth-hardening` branch with security fixes worth merging. |
| [`michaelbuckner/servicenow-mcp`](https://github.com/michaelbuckner/servicenow-mcp) | Python (FastMCP + httpx async) | Beta | 10 tools + 7 resources. Differentiator: rule-based natural-language query parsing. |
| [`anilvaranasi/ServiceNowMCPServer`](https://github.com/anilvaranasi/ServiceNowMCPServer) | Python (FastMCP) | Sample / demo | Single-file tutorial. Reviewed for completeness; nothing portable. |

## At a glance

| Dimension | echelon-ai-labs | michaelbuckner | anilvaranasi |
|---|---|---|---|
| Auth to ServiceNow (south-bound) | Basic / OAuth / API Key | Basic / Token / OAuth | Basic (hardcoded in source) |
| Auth from MCP client (north-bound) | Static bearer (in `fix/sse-auth-hardening` branch only) | None | None |
| Credential source | Env / CLI / `.env` | Env / CLI / `.env` | Hardcoded in source |
| Transport | stdio + SSE | stdio | stdio |
| HTTP client | sync `requests` | async `httpx` | async `httpx` |
| Tool count | ~82 | 10 + 7 resources | ~7 (mixed with weather demo) |
| Domain coverage | Incident, change, catalog, knowledge, agile, workflow, scripts, users | Incident, generic table, scripts | Incident sample only |
| Type safety | Pydantic + mypy strict | Pydantic + mypy strict | None |
| Tests | ~20 test files | 1 (NLP only) | None |
| CI | None visible | GitHub Actions (3.8–3.11) | None |
| License | MIT | MIT | None |

---

## Per-repo review

### 1. `echelon-ai-labs/servicenow-mcp`

**What it is.** The most complete implementation by a wide margin. Built on the low-level `mcp` SDK, ~82 tools across 15 domain modules under `src/servicenow_mcp/tools/`, with a dedicated `auth/` package, Pydantic config under `utils/config.py`, and a YAML-driven tool packaging system at `config/tool_packages.yaml`.

**Strengths.**
- **Three south-bound auth strategies** with a clean `AuthConfig` tagged union: Basic, OAuth (client_credentials with password fallback), API Key (`auth/auth_manager.py`).
- **Dual transport.** `cli.py` for stdio, `server_sse.py` for SSE/HTTP via Starlette+Uvicorn — same `ServiceNowMCP` instance underneath. Lets you serve Claude Desktop *and* a remote web client from one codebase.
- **Role-based tool packages.** `MCP_TOOL_PACKAGE` env var (`service_desk`, `catalog_builder`, `change_coordinator`, `platform_developer`, `agile_management`, `full`, `none`, etc.) filters which tools the LLM sees. This is the single best idea in any of these repos — it lets one server serve many personas without exposing the wrong blast radius to the wrong agent.
- **Functional tool signature.** Every tool is `(ServerConfig, AuthManager, ParamsModel) -> Response`. Pure, testable, no shared state.
- **Strict typing.** `mypy --strict`, Pydantic v2 throughout.
- **Real domain coverage.** Incidents, changes, catalog (with variables and optimization), workflows, changesets, script includes, knowledge base, users, and the full agile suite (epics, stories, scrum tasks, projects).
- **Tests for most tool modules** under `tests/`.

**Weaknesses.**
- **Logs OAuth response bodies at INFO level** (`auth_manager.py:113,133`) — that includes the access token. Real security bug.
- **Hardcodes `.service-now.com`** in OAuth token-URL construction (`auth_manager.py:90-94`) — breaks on custom domains.
- **No token expiry handling.** OAuth token is cached forever in `self.token`; only refreshed if you call `refresh_token()` manually. A long-lived server will start 401-ing silently.
- **No retry, no rate limiting, no connection pooling tuned for the workload.**
- **Sync `requests` library** despite MCP being async — the SSE server is going to block its event loop under load.
- **Monolithic 980-line `tool_utils.py` registry** — adding a tool requires editing this file. Doesn't take advantage of Python's import machinery for auto-discovery.
- **No CI** despite having tests, dev-deps, and lint config.
- **Generic `RuntimeError` wrapping** drops the underlying API error context that the LLM could use to recover.
- **No north-bound authentication at all on `main`** — the SSE server binds `0.0.0.0` with no token validation. (Fixed on `fix/sse-auth-hardening`; see below.)

**What to take.** Tool packaging (the killer feature), dual transport, the tagged-union auth config, the functional tool signature, the per-domain module split, mypy strict, the entire `fix/sse-auth-hardening` patch.

#### The `fix/sse-auth-hardening` branch

A single commit (`c77861e`, 2026-04-26, addressing EntruLabs disclosure 2026-04-22) rewrites `server_sse.py` with five defenses that are all **transport-agnostic** and worth keeping even if a future migration moves from SSE to Streamable HTTP:

- **Loopback bind by default** (`127.0.0.1` instead of `0.0.0.0`); non-loopback requires explicit `--allow-remote` *and* `MCP_AUTH_TOKEN`.
- **Bearer-token gate** on every request, validated with `hmac.compare_digest` (constant-time, no timing leak). Auto-generated and printed once to stderr if not configured on loopback.
- **`Host` header allowlist** → `421 Misdirected Request`. This is the **DNS-rebinding defense** — without it, any browser tab can be tricked into resolving a hostile hostname to `127.0.0.1` and issuing commands to a local MCP server.
- **`Origin` header allowlist** → `403 Forbidden`. CSRF defense for browser-originated cross-site requests.
- **Pure ASGI middleware** (not Starlette `BaseHTTPMiddleware`) — the latter buffers responses and silently breaks streaming. Non-obvious gotcha; they got it right.
- **`debug=True` removed** (was leaking Starlette stack traces) and **`mcp[cli]` bumped `1.3.0 → >=1.23.0,<2.0.0`** to pick up CVE-2025-66416. 41 new tests added (24 unit + 17 integration via Starlette `TestClient`).

The threat model these defenses address — DNS rebinding, browser CSRF, network-exposed unauthenticated servers, streaming-buffer regressions — applies to any HTTP-based MCP transport. The MCP authorization spec explicitly requires Origin validation and localhost binding for local servers, so this branch is essentially implementing the floor of those requirements. The static-token mechanism is the only piece superseded by full MCP OAuth 2.1; everything else carries over unchanged.

---

### 2. `michaelbuckner/servicenow-mcp`

**What it is.** A FastMCP server (10 tools, 7 resources) with a natural-language query parsing layer. Two parallel implementations: a 696-line `servicenow-mcp.py` at the root and a packaged `mcp_server_servicenow/` — unclear which is canonical.

**Strengths.**
- **Natural-language tools.** `natural_language_search`, `natural_language_update`, and `update_script` use a regex-based `NLPProcessor` (`mcp_server_servicenow/nlp.py`) to translate phrases like "close incident INC0010003 with resolution: X" into structured Snow operations. Lightweight, no LLM needed at the server layer — just rule-based extraction.
- **Generic table resources.** `servicenow://tables`, `servicenow://tables/{table}`, `servicenow://schema/{table}` give the LLM a way to discover the data model.
- **Async httpx end-to-end.** Single `httpx.AsyncClient` per server instance — the right shape for an async MCP.
- **Three south-bound auth strategies** with a base `Authentication` ABC.
- **OAuth refresh token logic** with expiry tracking (which echelon's lacks).
- **CI exists** — GitHub Actions across Python 3.8–3.11 with flake8.
- **Clean Pydantic models** for all payloads (`IncidentCreate`, `IncidentUpdate`, `QueryOptions`, `ScriptUpdateModel`).

**Weaknesses.**
- **Two parallel codebases** (top-level script vs package). Either deduplicate or delete one.
- **OAuth expiry comparison mixes types** (`server.py:153` vs `:191`) — `datetime` object vs epoch seconds. Token will either never expire or always look expired depending on the path.
- **Test coverage is the NLP module only** — no API-client mocks, no integration tests.
- **Hardcoded table mappings** in the NLP layer (8 tables); no schema-driven discovery despite having `servicenow://schema/{table}` available.
- **`update_script` searches by name** without `sys_id` disambiguation — silent overwrite risk.
- **Narrow tool surface** compared to echelon (10 vs 82).
- **No north-bound authentication.**

**What to take.** Natural-language query parsing as a power-user shortcut, generic table resources for schema discovery, async httpx, the `Authentication` ABC with proper OAuth token-refresh tracking (after fixing the type bug), the CI workflow scaffolding.

---

### 3. `anilvaranasi/ServiceNowMCPServer`

**What it is.** A single 160-line Python file (`mcpnow1.py`) demonstrating MCP tool registration against a personal `dev251734.service-now.com` instance.

**Strengths.**
- **Smallest possible reference.** Useful as a "what does FastMCP look like" example.
- **Async httpx.**
- **Demonstrates calling both custom Scripted REST APIs (`/api/x_146833_awesomevi/test`) and OOB tables (`/api/now/table/incident`).**

**Weaknesses.**
- **Hardcoded credentials.** `auth = ("myadmin", "XXXXX")` (`mcpnow1.py:17`). Even as a demo, this teaches the wrong habit.
- **Hardcoded instance URL** in source.
- **Dead code from a copy-pasted weather tutorial** — `get_alerts`, `get_forecast`, and an orphan `format_alert` docstring without a function. The constant is still named `NWS_API_BASE`.
- **Broken control flow.** `similarincidentsforincident` calls a coroutine without `await` (`mcpnow1.py:154-155`) and discards the result.
- **No type hints, no tests, no error handling, no packaging.**

**What to take.** Honestly very little. The pattern of querying a custom Scripted REST API namespace (`/api/<scope>/...`) alongside OOB tables is a reminder that real ServiceNow installations have both, and a serious server should support both.

---

## Architectural comparison

### Two distinct auth axes

The defining design choice is to cleanly separate the two authentication axes that the existing repos either conflate or only solve halfway:

- **South-bound auth** (MCP server → ServiceNow): Basic, API key, or **ServiceNow OAuth 2.0** (RFC 6749, the grant types ServiceNow's `oauth_token.do` endpoint supports — `client_credentials`, `password`, `refresh_token`, `authorization_code`). Echelon supports Basic / OAuth / API Key; michaelbuckner supports Basic / Token / OAuth; anilvaranasi only Basic (hardcoded).
- **North-bound auth** (MCP client → MCP server): how Claude Desktop or another agent authenticates to *us*. For stdio this is the OS process boundary (no auth needed). For HTTP transports, the **MCP authorization spec mandates OAuth 2.1** with PKCE, audience-bound tokens (RFC 8707), `/.well-known/oauth-protected-resource` metadata (RFC 9728), and ideally Dynamic Client Registration (RFC 7591).

None of the existing repos implement north-bound OAuth 2.1. Echelon's hardening branch implements a **static-bearer-token floor** that satisfies the spec's general "must authenticate" requirement but isn't full OAuth 2.1.

The two axes need separate packages and types — they don't share a credential lifecycle and they answer different questions.

### South-bound credential storage

Two postures across the repos:

1. **Local env / `.env`** (all three repos). Easy to set up, fine for local development, weak for production — credentials sit on every developer's box, no rotation story, no central audit.
2. **No credential storage at all** (anilvaranasi). Hardcoded in source.

A serious unified server needs a pluggable secret-store layer: env vars by default, with Vault and AWS Secrets Manager (and equivalents) as drop-in providers behind a `SecretsProvider` ABC.

### Transport

- All three repos default to stdio (correct for Claude Desktop).
- **Only echelon** supports HTTP (via SSE), and an HTTP transport is essential for cloud / remote-agent / multi-tenant scenarios.
- **SSE is being deprecated by the MCP spec in favor of Streamable HTTP** (single endpoint that supports both request/response and server-pushed streaming over chunked HTTP). The unified server should ship Streamable HTTP, not SSE — but the security defenses from echelon's hardening branch (Host/Origin allowlist, loopback default, pure ASGI middleware, constant-time token comparison, `debug=False`) all carry over because they address transport-agnostic threats (DNS rebinding, browser CSRF, unbounded network exposure).

The unified server should be **dual-transport** (stdio + Streamable HTTP), with the HTTP side genuinely async end-to-end (echelon's isn't — it uses sync `requests` under an async server).

### Tool organization

- **Echelon**: per-domain Python modules + central registry + YAML role packages — best at scale.
- **Michaelbuckner**: monolithic `server.py` with a separate NLP module — clean separation but doesn't scale past ~20 tools.
- **Anilvaranasi**: everything in one file — fine for demos.

The right answer is per-domain modules (echelon-style) with auto-registration via decorators or `pkgutil.iter_modules`, eliminating the 980-line central registry.

### Configuration

- **Echelon**: Pydantic `ServerConfig` with CLI args + env + `.env`. Layered correctly.
- **Michaelbuckner**: similar to echelon but less structured.
- **Anilvaranasi**: env only or hardcoded.

Echelon's `ServerConfig` shape is the right base.

### Domain coverage

Echelon dominates: incidents, changes, catalog (with variables and optimization), workflows, changesets, script includes, knowledge base, users, and full agile (epics, stories, scrum tasks, projects). Michaelbuckner is incident-heavy with a generic-table escape hatch. The unified server should start from echelon's tool set.

### Quality bar

Only echelon and michaelbuckner enforce typing strictly. Only michaelbuckner has CI. Only echelon has serious test coverage. The unified server should adopt: mypy strict + Pydantic v2 + ruff + pytest + GitHub Actions matrix (3.10–3.13) from day one.

---

## Cross-cutting issues none of them solve well

1. **OAuth token lifecycle (south-bound).** Echelon never refreshes; michaelbuckner has a type bug in expiry comparison; nobody handles 401-then-refresh-and-retry.
2. **No north-bound OAuth 2.1.** All three are unauthenticated on the wire; only echelon's hardening branch has even a static-token floor.
3. **Pagination.** ServiceNow returns `X-Total-Count` and `Link` headers for paged responses. Nobody respects them.
4. **Rate limiting.** ServiceNow throttles per-instance. None of these implementations back off on 429.
5. **Caching.** Read-heavy workloads (schema lookups, user info) re-query on every call.
6. **Error transparency to the LLM.** Most wrap errors generically; an LLM agent recovers much better when it sees the actual ServiceNow error payload.
7. **Schema discovery.** Only michaelbuckner exposes table schema as a resource. Without it, the LLM has to guess field names.
8. **Custom Scripted REST APIs.** Real ServiceNow installs run `/api/<scope>/...` endpoints alongside OOB. Only anilvaranasi (accidentally) hits one.
9. **Audit attribution.** None forward an end-user identity to ServiceNow. With north-bound OAuth 2.1, the MCP server knows who the caller is — but no existing implementation propagates that to ServiceNow (via OBO token exchange or even a custom header).

---

## Proposed best-of-breed architecture

A single Python MCP server that stitches together the strongest ideas.

### Layout

```
src/servicenow_mcp/
  cli.py                  # stdio entry point
  server_http.py          # Streamable HTTP entry point (single endpoint, async)
  server.py               # core ServiceNowMCP (shared by both transports)
  northbound/             # MCP client → MCP server auth (north-bound)
    middleware.py         # ASGI: Host/Origin allowlist, loopback default
    oauth_resource.py     # OAuth 2.1 Resource Server: JWT validate, audience check
    metadata.py           # /.well-known/oauth-protected-resource (RFC 9728)
    static_token.py       # opt-in fallback: bearer + hmac.compare_digest
    identity.py           # MCPCallerIdentity model exposed to tools/auth
  southbound/             # MCP server → ServiceNow (south-bound)
    base.py               # Authentication ABC w/ async get_headers() + refresh()
    basic.py
    api_key.py
    oauth.py              # ServiceNow OAuth 2.0: expiry tracking + 401-retry-once
    obo.py                # OAuth on-behalf-of: exchange MCP caller token for SN token
  secrets/
    env.py                # default loader
    vault.py              # HashiCorp Vault (open source)
    aws_secrets.py        # AWS Secrets Manager
  utils/
    config.py             # Pydantic ServerConfig (echelon-style, layered)
    pagination.py         # respects X-Total-Count, Link, sysparm_offset/limit
    retry.py              # exponential backoff on 429/5xx; refresh+retry on 401
    cache.py              # TTL cache for schema lookups + user lookups + JWKS
    nl.py                 # michaelbuckner's NLPProcessor, generalized
    tool_registry.py      # auto-discovery via pkgutil; no 980-line registry
    redaction.py          # log filter to scrub access_token / authorization
  tools/
    incident/             # one folder per ServiceNow table/domain:
      model.py            #   Pydantic models
      mapping.py          #   ServiceNow ↔ MCP field mapping
      validation.py       #   regex / business rules
      tools.py            #   @register_tool functions
    change/
    catalog/
    knowledge/
    user/
    workflow/
    script_include/
    agile/                # epic, story, scrum_task, project
    table/                # generic perform_query (gated)
    nl/                   # natural_language_search / _update (opt-in package)
  resources/
    schema.py             # servicenow://schema/{table}, servicenow://tables
config/
  tool_packages.yaml      # role-based filtering (echelon's killer feature)
```

### Key design decisions

#### Two-layer auth

The defining design choice: cleanly separate **north-bound** (MCP client → us) from **south-bound** (us → ServiceNow). They live in different packages, don't share types, and can be configured independently.

1. **North-bound: OAuth 2.1 Resource Server, per MCP spec.**
   - For Streamable HTTP transport, implement the MCP authorization spec as a proper OAuth 2.1 Resource Server:
     - Validate bearer JWTs from the `Authorization` header (signature via cached JWKS, `iss`, `aud`, `exp`, `nbf`).
     - **Enforce audience binding (RFC 8707)** — reject any token whose `aud` is not this MCP server's resource identifier. This stops a token issued for one MCP from being replayed against another.
     - Publish `/.well-known/oauth-protected-resource` (RFC 9728) pointing at the configured Authorization Server(s); clients use this for discovery.
     - Document support for one or more configured Authorization Servers (Auth0, Okta, Entra, Keycloak, in-house). No embedded AS — be a Resource Server only.
     - Optionally support Dynamic Client Registration (RFC 7591) by proxying to the AS that supports it; otherwise document the manual registration steps.
     - Required response codes: `401 Unauthorized` with `WWW-Authenticate: Bearer resource_metadata="..."` for missing/invalid tokens; `403 Forbidden` for insufficient scope.
     - Token-to-`MCPCallerIdentity` mapping exposes `sub`, `scope`, `client_id`, `aud`, raw claims to downstream code so tools and south-bound auth can attribute calls.
   - **Static-token mode** (port from echelon's `fix/sse-auth-hardening`) remains as an opt-in fallback for development, air-gapped environments, and the inside-perimeter case where an upstream API gateway has already done OAuth. Same `hmac.compare_digest` + Host/Origin allowlist + loopback default.
   - **For stdio transport**, north-bound auth is the OS process boundary — the launching client is trusted. Identity, if needed, comes from MCP `initialize` params, not from a tool argument.

2. **Universal HTTP defenses** (transport-agnostic, port from echelon's hardening branch):
   - Loopback bind by default; non-loopback requires `--allow-remote` opt-in.
   - **`Host` header allowlist → 421** (DNS-rebinding defense).
   - **`Origin` header allowlist → 403** (browser CSRF defense).
   - Pure ASGI middleware (not `BaseHTTPMiddleware`) so streaming responses aren't buffered.
   - `debug=False` always; structured logging with credential redaction.
   - Pin `mcp[cli]` to a version with the CVE-2025-66416 fix; track upstream advisories.

3. **South-bound: ServiceNow OAuth 2.0 done correctly.** ABC with async `get_headers()` and `refresh()`. Implementations:
   - `basic.py` — username/password from secret store.
   - `api_key.py` — header-based.
   - `oauth.py` — ServiceNow OAuth 2.0 with proper expiry tracking + 401-retry-once. Fixes echelon's "log the access token" bug and michaelbuckner's `datetime` vs epoch-seconds confusion. Supports the four ServiceNow OAuth grant types: `client_credentials`, `password`, `refresh_token`, `authorization_code`.
   - `obo.py` — exchange the inbound MCP OAuth token for a ServiceNow OAuth token (RFC 8693 token exchange) so ServiceNow sees the real end-user. The only path that gives true ServiceNow-side audit attribution.

4. **Secret-store as a first-class plugin.** `SecretsProvider` ABC. Default = env vars. Production = HashiCorp Vault or AWS Secrets Manager. Loaded once at startup, refresh hook for long-lived servers and OAuth client-secret rotation.

5. **Tool packaging from echelon, generalized.** YAML-driven role packages, plus a `MCP_TOOL_DENYLIST` for fine-grained removal. **Hook into north-bound scopes**: a tool can declare `required_scope="snow:incident:write"` and the registry filters by both the configured package *and* the caller's actual OAuth scopes. A `service_desk` agent shouldn't see `delete_record`, and even if it did, the missing scope would 403 it.

6. **Auto-registered tools.** `@register_tool(domain="incident", scope="read", required_scope="snow:incident:read")` decorator + `pkgutil.iter_modules` walker. Adding a tool = drop a file in the right folder. Kills echelon's 980-line registry.

7. **Per-domain module structure** with a `model.py` / `mapping.py` / `validation.py` / `tools.py` triplet per domain — keeps schema discipline as the tool count grows.

8. **Async httpx + httpx.AsyncClient with connection pooling.** One client per process, reused across tools. Async all the way down — no `requests` under an async server.

9. **Real production middleware:**
   - Pagination helper that auto-follows `Link` headers (opt-in, capped).
   - Retry: exponential backoff on 429 and 5xx; one-shot refresh-and-retry on 401 for both north-bound (token refresh via AS) and south-bound (ServiceNow OAuth).
   - TTL cache for schema, user lookups, and JWKS (high read repetition).
   - **End-user attribution** propagated to ServiceNow via OBO when both axes are OAuth-enabled; otherwise via a configured `X-User-Id` header derived from `MCPCallerIdentity.sub` so at least an audit log can attribute the call.

10. **NLP layer from michaelbuckner**, driven by schema discovery (not hardcoded table names). Use the schema cache to map "incidents" → `incident`, "stories" → `rm_story`.

11. **Generic table escape hatch** (`perform_query`) gated behind both the `platform_developer` package *and* a `snow:table:raw` scope — too dangerous for service-desk personas, and the scope check is the actual enforcement.

12. **Quality bar from day one:** mypy strict, ruff, pytest with `respx` for HTTP mocking, **CI matrix using echelon hardening branch's test pattern** (Starlette `TestClient` for north-bound integration tests), GitHub Actions on Python 3.10–3.13, and a logging redaction filter that fails the build if `access_token` or `authorization` appears in any captured log line (would have caught echelon's bug).

---

## How to combine the existing repos

**Don't merge them in place — use them as ingredients.**

- `echelon-ai-labs/servicenow-mcp` is the strongest base. ~70% of the unified server's structure can be ported from it directly; the rest (auth ABC, async, secret stores, NL parsing, schema resources, north-bound OAuth, auto-discovery, retry/pagination) is additive.
- `michaelbuckner/servicenow-mcp` contributes the NLP processor, async pattern, schema resources, OAuth refresh-with-expiry tracking, and CI scaffolding.
- `anilvaranasi/ServiceNowMCPServer` has nothing reusable beyond the "Scripted REST API namespace exists" reminder. Don't merge; review only.

The recommended sequence is to fork echelon as `main`, integrate the targeted fixes from its own `fix/sse-auth-hardening` branch and from michaelbuckner in a series of small, atomic commits (the playbook below), and only then take on the larger structural changes (sync→async refactor, SSE→Streamable HTTP migration, full MCP OAuth 2.1 north-bound).

---

## Execution playbook

> Self-contained step-by-step plan. Assumes a fresh Claude Code session with no prior conversation context. Read this whole section first, then execute.

### What this playbook produces

Take an unzipped copy of the `main` branch of `echelon-ai-labs/servicenow-mcp` in a local working directory, turn it into a git repo, and make a series of small focused commits that integrate selected fixes from the two other public OSS repos. Push each milestone to a (presumed empty) GitHub repo of the user's choosing.

### Prerequisites

- A working directory containing the unzipped contents of echelon's `main` branch (no `.git/` directory yet).
- An empty target GitHub repo URL, owned by whoever is doing this work.
- `git` is configured globally; verify before starting:
  - `git config --global user.name` should return the author name to use.
  - `git config --global user.email` — confirm with the user which email to use (likely `<github-username>@users.noreply.github.com` for a public personal repo) and set it repo-locally.
- SSH to GitHub works as the repo owner: `ssh -T git@github.com` should print `Hi <username>!`. If this fails, stop and ask the user.
- `gh` CLI is **not** required. Use plain `git` for everything.

### Reference repos

Clone these alongside the working directory if they aren't already present:

```
git clone https://github.com/echelon-ai-labs/servicenow-mcp echelon-ai-labs/servicenow-mcp
git clone https://github.com/michaelbuckner/servicenow-mcp michaelbuckner/servicenow-mcp
git clone https://github.com/anilvaranasi/ServiceNowMCPServer anilvaranasi/ServiceNowMCPServer
```

Pinned commits referenced below:

| Source | Branch / SHA | Purpose |
|---|---|---|
| `echelon-ai-labs/servicenow-mcp` | `main` @ `0625060` (2025-10-03) | Baseline |
| `echelon-ai-labs/servicenow-mcp` | `origin/fix/sse-auth-hardening` @ `c77861e` (2026-04-26) | SSE hardening patch — single biggest source for this phase |
| `michaelbuckner/servicenow-mcp` | `master` @ `39e0910` | NLP, schema resources, OAuth refresh, CI workflow |
| `anilvaranasi/ServiceNowMCPServer` | `bcbbf2e` | Reviewed only; nothing reusable |

### Decisions baked into this playbook

These are constraints, not open questions:

1. **Scope: incremental, not big-bang.** Defer the `requests` → `httpx.AsyncClient` refactor to a separate later phase. Async refactor touches every file in `src/servicenow_mcp/tools/` and is out of scope here.
2. **Transport: port hardening to existing `server_sse.py`.** Streamable HTTP migration is out of scope here.
3. **Full MCP OAuth 2.1 north-bound is out of scope for this phase.** This phase ships the static-token floor from the hardening branch. OAuth 2.1 Resource Server is its own follow-up phase (see proposed architecture above for shape).
4. **Commit cadence: small, atomic, push after each milestone.** The repo is brand new and empty, so push to `main` is safe.
5. **anilvaranasi: no code ported.** Add a single note to the README's fork-attribution block crediting it as reviewed.

### Commit-by-commit plan

Make these as separate commits in this order. Push after each one (or batch the first two if the user prefers fewer pushes).

#### Commit 1 — Initial import (verbatim baseline)

```
cd <working-dir>
git init -b main
git config user.email '<email-the-user-told-you>'
# .gitignore already exists in the unzipped tree; .DS_Store may be present and should be removed before first commit:
find . -name .DS_Store -delete
git add -A
git commit -m "Initial import: echelon-ai-labs/servicenow-mcp main @ 0625060"
git remote add origin git@github.com:<owner>/<repo>.git
git push -u origin main
```

The commit message should reference echelon's exact baseline commit SHA so the import is auditable. This commit must contain **no modifications** beyond stripping `.DS_Store` files — it is a verbatim snapshot.

If the push fails with auth errors, do not attempt destructive recovery. Stop and ask the user.

#### Commit 2 — Fork attribution in README

A small, visible second commit that documents what this fork is and what it integrates. Add a section near the top of `README.md` (after the title, before the existing badges/intro) with content along these lines:

```markdown
> **Fork notice.** This repository is a fork of [echelon-ai-labs/servicenow-mcp](https://github.com/echelon-ai-labs/servicenow-mcp) (`main` @ `0625060`, 2025-10-03). It integrates selected fixes from:
> - `echelon-ai-labs/servicenow-mcp` `fix/sse-auth-hardening` branch (`c77861e`, 2026-04-26) — SSE transport hardening
> - [michaelbuckner/servicenow-mcp](https://github.com/michaelbuckner/servicenow-mcp) (`master` @ `39e0910`) — natural-language query parsing, schema-discovery resources, OAuth refresh-with-expiry tracking, CI workflow
>
> [anilvaranasi/ServiceNowMCPServer](https://github.com/anilvaranasi/ServiceNowMCPServer) was also reviewed but contained no patterns suitable for porting.
```

```
git commit -am "docs: add fork attribution and integration roadmap to README"
git push
```

#### Commit 3 — Bug fix: stop logging OAuth response bodies

In `src/servicenow_mcp/auth/auth_manager.py`:
- Lines around `:112-113` and `:132-133` log `response.text` at INFO level after a token request. These response bodies contain the access token. **Remove these two `logger.info(f"... response body: {response.text}")` calls entirely.**
- Keep the `logger.info(f"... response status: {response.status_code}")` lines — status codes alone are fine to log.
- On token-fetch failure (the `raise ValueError("Failed to get OAuth token...")` path), log a redacted error containing only the status code and a generic message — never the response body.

```
git commit -am "fix(auth): stop logging OAuth response bodies (leaked access tokens)"
git push
```

#### Commit 4 — Bug fix: don't hardcode `.service-now.com` in OAuth token URL

In `src/servicenow_mcp/auth/auth_manager.py` `_get_oauth_token` (around lines `:90-94`), the code splits `instance_url` on `.` and rebuilds it as `https://{instance_name}.service-now.com/oauth_token.do`. This breaks any installation on a custom domain.

Replace the entire URL-construction block with:
```python
token_url = oauth_config.token_url
if not token_url:
    if not self.instance_url:
        raise ValueError("Instance URL is required for OAuth authentication")
    token_url = f"{self.instance_url.rstrip('/')}/oauth_token.do"
```

```
git commit -am "fix(auth): construct OAuth token URL from instance_url, not hardcoded service-now.com"
git push
```

#### Commit 5 — Port the SSE hardening patch

Source: `echelon-ai-labs/servicenow-mcp` commit `c77861e` on `origin/fix/sse-auth-hardening`. Touches these files:

- `src/servicenow_mcp/server_sse.py` — full rewrite (287 LOC delta). Port verbatim.
- `tests/test_server_sse.py` — new file, 134 LOC. Port verbatim.
- `tests/test_server_sse_integration.py` — new file, 205 LOC. Port verbatim.
- `.env.example` — add `MCP_AUTH_TOKEN`, `MCP_ALLOW_REMOTE`, `MCP_ALLOWED_HOSTS` documentation block.
- `Dockerfile` — change `CMD` to include `--allow-remote` (since Docker binds non-loopback) and document the requirement to set `MCP_AUTH_TOKEN`.
- `README.md` — replace the SSE section with the hardened version's documentation (loopback default, `--allow-remote` opt-in, bearer token, allowlist semantics).
- `pyproject.toml` — bump `mcp[cli]==1.3.0` to `mcp[cli]>=1.23.0,<2.0.0` (CVE-2025-66416).

The single most important non-obvious detail in this patch: the auth check is implemented as **pure ASGI middleware**, not Starlette `BaseHTTPMiddleware`. `BaseHTTPMiddleware` buffers responses, which silently breaks SSE streaming. Port the `SecurityMiddleware` class exactly as written — do not "improve" it by switching to `BaseHTTPMiddleware`.

To get the patch:
```
cd ../../echelon-ai-labs/servicenow-mcp   # the reference clone
git format-patch -1 c77861e --stdout > /tmp/sse-hardening.patch
cd <working-dir>
git apply --check /tmp/sse-hardening.patch && git apply /tmp/sse-hardening.patch
```

`uv.lock` will be in the patch's diff stat (~700 lines); regenerate it locally after applying with `uv lock` rather than taking the patched version verbatim, since the lock should resolve against the new local environment.

Run the new tests to confirm:
```
uv sync --all-extras    # or pip install -e ".[dev]"
pytest tests/test_server_sse.py tests/test_server_sse_integration.py -v
```

Commit:
```
git add -A
git commit -m "feat(sse): port hardening from echelon@fix/sse-auth-hardening (c77861e)

Loopback bind by default; --allow-remote opt-in requires MCP_AUTH_TOKEN.
Every /sse and /messages/ request gated by bearer token (hmac.compare_digest)
plus Host (421) and Origin (403) allowlists. Pure ASGI middleware preserves
SSE streaming. debug=False. mcp[cli] bumped 1.3.0 -> >=1.23.0,<2.0.0
(CVE-2025-66416). 41 new tests via Starlette TestClient."
git push
```

#### Commit 6 — Port michaelbuckner OAuth refresh-with-expiry (with type-bug fix)

Source: `michaelbuckner/servicenow-mcp/mcp_server_servicenow/server.py` lines 136-191 (`OAuthAuth` class).

Port the **pattern** of expiry tracking + auto-refresh-when-expired into `src/servicenow_mcp/auth/auth_manager.py`. Add to the existing `AuthManager`:

- A `self.token_expiry: Optional[datetime]` attribute (timezone-aware UTC).
- A `self.refresh_token: Optional[str]` attribute (populated from the token response if present).
- In `get_headers()` for the OAuth path: before returning the cached token, check if `self.token_expiry` is set and `datetime.now(timezone.utc) >= self.token_expiry - timedelta(seconds=30)` (30s safety margin) — if so, call `self._get_oauth_token()` again.
- In `_get_oauth_token()`: after a successful response, set `self.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 1800))`. Also capture `refresh_token` if returned.

**Critical: do not copy michaelbuckner's bug.** In their code, `server.py:153` compares `datetime.now()` to `self.token_expiry` (a `datetime`), but `:191` sets `self.token_expiry = datetime.now().timestamp() + expires_in` (a `float`). The comparison `datetime > float` raises `TypeError` after the first refresh. **Use timezone-aware `datetime` consistently** — never `.timestamp()`.

Add a unit test that:
- Sets a mock OAuth response, calls `get_headers()`, advances time past the expiry, calls `get_headers()` again, and asserts that the token-fetch endpoint was called twice.

Also wire up a one-shot 401-retry: if any south-bound ServiceNow request returns 401, call `auth_manager.refresh_token()` and retry exactly once. Add this in whatever shared HTTP-call helper the tools use; if there isn't one, defer this part to its own commit and just note it in the commit message as future work.

```
git add -A
git commit -m "feat(auth): OAuth token refresh-on-expiry with type-safe datetime tracking

Caches expiry as timezone-aware UTC datetime (not epoch float).
Refresh fires 30s before expiry. Avoids the datetime-vs-float TypeError bug
in michaelbuckner@39e0910 server.py:153/191."
git push
```

#### Commit 7 — Port michaelbuckner schema-discovery resources

Source: `michaelbuckner/servicenow-mcp/mcp_server_servicenow/server.py` registrations at lines 327-333 (the `servicenow://` URI scheme), with handler implementations elsewhere in the same file.

Add to `src/servicenow_mcp/server.py` (or wherever resources are registered in echelon — locate by grepping for `mcp.resource(`):

- `servicenow://tables` — list all tables. Implementation hits `/api/now/table/sys_db_object` with `sysparm_fields=name,label,sys_id` and `sysparm_limit=1000` (configurable cap).
- `servicenow://tables/{table}` — sample records from a given table (use `sysparm_limit=10`).
- `servicenow://schema/{table}` — column schema. Hit `/api/now/table/sys_dictionary?sysparm_query=name={table}^elementISNOTEMPTY` and return field name, label, internal_type, mandatory, max_length.

Cache results with a TTL of ~5 minutes — schema lookups are idempotent and cheap to cache. If the project doesn't yet have a cache helper, use a simple `cachetools.TTLCache(maxsize=128, ttl=300)` keyed on the URI.

Echelon's existing `requests`-based client should be used (not switched to httpx — that's deferred to the async refactor phase).

```
git add -A
git commit -m "feat(resources): schema-discovery via servicenow://tables and servicenow://schema/{table}

Lets the LLM discover the data model instead of guessing field names.
Pattern from michaelbuckner@39e0910 server.py:327-333. 5-minute TTL cache."
git push
```

#### Commit 8 — Port michaelbuckner NLPProcessor

Source: `michaelbuckner/servicenow-mcp/mcp_server_servicenow/nlp.py` (185 LOC).

Drop the file in as `src/servicenow_mcp/utils/nl.py`. Add a new tool module `src/servicenow_mcp/tools/nl_tools.py` that exposes:

- `natural_language_search(query: str)` — uses `NLPProcessor.parse_search_query` to translate "find incidents about X" into a ServiceNow encoded query, then runs the search against the resolved table.
- `natural_language_update(command: str)` — uses `NLPProcessor.parse_update_command` to translate "close INC0010003 with resolution: X" into an update operation.

Wire the new tools into `src/servicenow_mcp/utils/tool_utils.py` (the central registry). Add a new tool package `nl_power_user` to `config/tool_packages.yaml` containing just these two tools. **Do not** add NL tools to existing packages by default — they're opt-in.

The hardcoded table-name map in `nlp.py` (incidents → `incident`, etc.) is acceptable for this commit. Schema-driven lookup using the resources from commit 7 is a follow-up.

```
git add -A
git commit -m "feat(nl): port michaelbuckner's NLPProcessor as opt-in nl_power_user package

Two new tools: natural_language_search, natural_language_update.
Rule-based parser, no LLM at the server layer.
Schema-driven table resolution deferred to a follow-up."
git push
```

#### Commit 9 — Add GitHub Actions CI matrix

Source pattern: `michaelbuckner/servicenow-mcp/.github/workflows/python-package.yml`.

Create `.github/workflows/ci.yml` with:
- Triggers: `push` to `main`, `pull_request` targeting `main`.
- Python matrix: `["3.10", "3.11", "3.12", "3.13"]` (drop the 3.8/3.9 from michaelbuckner — echelon's `pyproject.toml` already declares Python 3.11+).
- Steps:
  1. `actions/checkout@v4`
  2. `actions/setup-python@v5` with the matrix version
  3. Install dev deps: prefer `uv sync --all-extras` if `uv.lock` is present; else `pip install -e ".[dev]"`.
  4. `ruff check .`
  5. `mypy src/servicenow_mcp` (strict is already configured in `pyproject.toml`)
  6. `pytest -v`
  7. **Log-redaction check** (new): add a `pytest` fixture that wraps `caplog` and asserts no captured log line matches `(?i)access_token|authorization: bearer`. Run it as a final test step.

```
git add .github/workflows/ci.yml
git commit -m "ci: GitHub Actions matrix on Python 3.10-3.13

Runs ruff + mypy strict + pytest. Log-redaction check fails the build
if any captured log line contains 'access_token' or 'Authorization: Bearer'
(would have caught the OAuth-body-logging bug fixed in commit 3)."
git push
```

### After this playbook

- The repo on GitHub at `main` has ~9 commits, each small and reviewable.
- All tests should pass on all matrix Python versions.
- The README's fork-attribution block makes the provenance clear.
- The next major work items (deferred — do not start in this session unless the user asks):
  1. `requests` → `httpx.AsyncClient` refactor across all of `src/servicenow_mcp/tools/` and `auth/`.
  2. Schema-driven table resolution in the NLPProcessor.
  3. SSE → Streamable HTTP migration.
  4. Full MCP-spec OAuth 2.1 Resource Server (`northbound/oauth_resource.py` etc.) per the architecture in this doc — JWT validation, JWKS caching, audience binding (RFC 8707), `/.well-known/oauth-protected-resource` (RFC 9728), `WWW-Authenticate: Bearer resource_metadata=...` on 401. Document setup against at least one external Authorization Server (Auth0, Okta, Entra, Keycloak) end-to-end.
  5. RFC 8693 token exchange (`southbound/obo.py`) so ServiceNow sees end-user identity when both axes are OAuth-enabled.
  6. Auto-discovery tool registry (`pkgutil.iter_modules` + decorator) to retire the monolithic `tool_utils.py`.
  7. Pluggable secret stores (`secrets/vault.py`, `secrets/aws_secrets.py`).

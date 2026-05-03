# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

**This repo is a GitHub fork of `echelon-ai-labs/servicenow-mcp` with full upstream history preserved.** The `origin` remote is `git@github.com:ShadNygren/servicenow-mcp.git`; the `upstream` remote points to `https://github.com/echelon-ai-labs/servicenow-mcp.git`. The `fix/sse-auth-hardening` branch is also tracked from origin.

`ANALYSIS_OF_EXISTING_OPEN_SOURCE_SERVICENOW_MCP_SERVERS.md` contains the architectural rationale and the original 9-commit execution playbook. Read it for context — but note that the playbook predates the decision to fork-on-GitHub, so a few commit boundaries shift in practice (see "Deviations from the playbook" below).

## What this repo will become

A unified ServiceNow MCP server, layered on top of echelon's history:

1. Echelon's `main` @ `0625060` is the base — fork preserves all 42 commits and original authorship.
2. `fix/sse-auth-hardening` (`c77861e`) is integrated as a real merge commit, preserving its authorship and reviewability.
3. Targeted patterns from `michaelbuckner/servicenow-mcp` (`main` @ `39e0910`) are ported with attribution: NLP processor, schema-discovery resources, OAuth refresh-with-expiry tracking, CI workflow.
4. `anilvaranasi/ServiceNowMCPServer` is **reviewed only — no code copied**. The repo has no LICENSE file, so any substantive copying would be legally ambiguous; we deliberately avoid it. Credited as "reviewed" in NOTICE/README, not as a code source.

The expected end state is a Python project (`pyproject.toml`, `src/servicenow_mcp/`, `tests/`) using `mcp[cli] >=1.23.0,<2.0.0` (CVE-2025-66416), Pydantic v2, mypy strict, and pytest.

## Licensing

The project stays under **MIT** (matching both upstream MIT-licensed sources). Both echelon's and michaelbuckner's copyright notices must be preserved in `NOTICE` and the relevant `LICENSE-*` files. **Do not relicense to Apache-2.0 or any other license** without explicit user direction — this decision was discussed and resolved in favor of MIT.

## Deviations from the playbook

The original playbook in `ANALYSIS_*.md` assumed a ZIP-based standalone import. Forking on GitHub changes the mechanics:

- **No verbatim "Initial import" commit needed** — the fork already carries echelon's full history.
- **`fix/sse-auth-hardening` is integrated via `git merge`, not `git format-patch`.** This preserves the original commit's authorship, message, and date. Run `git merge origin/fix/sse-auth-hardening` from `main`.
- **Upstream pulls are possible.** `git fetch upstream && git merge upstream/main` (or rebase, depending on policy at the time) brings in any future echelon work.
- **Bug-fix commits in this repo (the OAuth body logging fix, the hardcoded `.service-now.com` URL fix) are upstream-worthy.** Open PRs to echelon for each. They're security fixes any project would want.

Everything else in the playbook stands: same constraints, same scope, same out-of-scope deferrals.

## Constraints baked into this phase

These are not open questions — the playbook deliberately defers them:

- **Do not refactor `requests` → `httpx.AsyncClient`.** The async migration touches every tool module and is a separate later phase.
- **Do not migrate SSE → Streamable HTTP.** Integrate the existing hardened SSE server; defer the transport migration.
- **Do not implement full MCP-spec OAuth 2.1 north-bound.** This phase ships only the static-bearer-token floor from echelon's hardening branch. The OAuth 2.1 Resource Server (JWT validation, JWKS, audience binding per RFC 8707, `/.well-known/oauth-protected-resource` per RFC 9728) is its own follow-up phase.
- **Commit cadence is small and atomic.** Push after each milestone.

## Architectural orientation

The defining design choice is the separation of **two auth axes** — they live in different packages, don't share types, and are configured independently:

- **North-bound** (MCP client → this server): For HTTP transports, eventually OAuth 2.1 Resource Server per the MCP authorization spec; in this phase, a static bearer token gated by Host/Origin allowlists with loopback default. For stdio, the OS process boundary is the trust boundary.
- **South-bound** (this server → ServiceNow): Basic / API key / ServiceNow OAuth 2.0 (`client_credentials`, `password`, `refresh_token`, `authorization_code`). Eventually RFC 8693 token exchange (OBO) so ServiceNow sees the real end-user when both axes are OAuth-enabled.

Echelon's tool packaging (`MCP_TOOL_PACKAGE` env var + `config/tool_packages.yaml`) is the killer feature being preserved — it lets one server serve many personas (`service_desk`, `catalog_builder`, `change_coordinator`, `platform_developer`, `agile_management`, etc.) without exposing the wrong blast radius to the wrong agent.

## Two known bugs from upstream that must not be reintroduced

When porting from upstream sources, watch for these:

1. **echelon `auth_manager.py:113,133`** logs OAuth response bodies (containing access tokens) at INFO level. The CI log-redaction check is designed to fail the build if `access_token` or `Authorization: Bearer` appears in any captured log line.
2. **michaelbuckner `server.py:153` vs `:191`** mixes `datetime` and epoch-seconds for token expiry — comparison raises `TypeError` after the first refresh. Use timezone-aware UTC `datetime` consistently; never `.timestamp()`.

## Commands

Standard development commands (echelon's existing build system):

```
uv sync --all-extras           # or: pip install -e ".[dev]"
pytest -v                       # full suite
pytest tests/test_<file>.py -v  # single file
pytest -k <pattern> -v          # by name pattern
ruff check .
mypy src/servicenow_mcp         # strict mode is configured in pyproject.toml
```

## Reference clones

These should be cloned alongside this working tree (not inside it):

```
echelon-ai-labs/servicenow-mcp        # available locally as the upstream remote
michaelbuckner/servicenow-mcp         # NLP, schema resources, OAuth refresh, CI patterns to port
anilvaranasi/ServiceNowMCPServer      # reviewed only — do not copy code
```

Pinned SHAs:

| Source | Reference | Purpose |
|---|---|---|
| `echelon-ai-labs/servicenow-mcp` | `main` @ `0625060` | Fork base |
| `echelon-ai-labs/servicenow-mcp` | `origin/fix/sse-auth-hardening` @ `c77861e` | SSE hardening — merge as-is |
| `michaelbuckner/servicenow-mcp` | `main` @ `39e0910` | Port: NLP, schema, OAuth refresh, CI |
| `anilvaranasi/ServiceNowMCPServer` | (no LICENSE) | Reviewed only — no code copied |

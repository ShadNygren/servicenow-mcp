# Analysis of Echelon-AI-Labs Open PRs and Issues

A review of the 15 open pull requests and 13 open issues at [`echelon-ai-labs/servicenow-mcp`](https://github.com/echelon-ai-labs/servicenow-mcp) as of 2026-05-02. For each PR: do we want to merge it into our fork (`ShadNygren/servicenow-mcp`)? For each issue: is it a bug fix, feature request, security concern, or out-of-scope, and what priority?

This complements [`ANALYSIS_OF_ECHELON_AI_LABS_SERVICENOW_MCP_FORKS.md`](ANALYSIS_OF_ECHELON_AI_LABS_SERVICENOW_MCP_FORKS.md). Several of the open PRs originated from the same authors as the forks already analyzed, and either matched or improved on the fork commits — flagged inline below.

---

## Open PRs (15)

### PR #65 — `Daily/2026 04 08 extract shared helpers` (torkian, +4891/-720, 55 files)

**Source.** torkian's helpers refactor — same as commit `cb727c0` already analyzed in the fork survey.
**Verdict.** **HIGH — port via fork analysis (already on cherry-pick list).** This is the foundational refactor that enables most of torkian's downstream work. Take from torkian's fork directly rather than from this PR (the fork has 90 commits layered on top that build on it).

---

### PR #60 — `feat(catalog): add create_catalog_item tool` (nishikanth, +93/-0, 3 files)

**Verdict.** **MEDIUM — supersede with torkian's `12479b5`.** torkian implemented the same feature with tests. Use torkian's version.

---

### PR #59 — `fix(auth): stop logging OAuth token response bodies` (alexzadeh, +103/-6)

**Source.** Same author who landed `ba56b83` in torkian's fork.
**Verdict.** **HIGH — already on cherry-pick list.** This is exactly the security fix our own playbook commit 3 implements. Strong cross-validation. If we cherry-pick from torkian's fork, we get it; the upstream PR is what we should also recommend echelon merge.

---

### PR #58 — `Add CSM tools: accounts, locations, products, case correlation` (dobromirmontauk, +1807/-1)

**Source.** Same as the `dobromirmontauk/servicenow-mcp` fork.
**Verdict.** **MEDIUM — port with rebrand.** Already on cherry-pick list with the recommendation to sanitize "Mashgin" framing.

---

### PR #56 — `Adding ACL Tools` (31-rat4, +3475/-1374, 20 files)

**New finding — not in any fork I analyzed.** Substantial addition: `list_acls`, `get_acl`, `create_acl`, `update_acl`, `delete_acl`, `list_roles_security`, `get_role`, `create_role`, `update_role`, `list_security_attributes`, `create_security_attribute`. All target OOB tables (`sys_security_acl`, `sys_user_role`, `sys_security_acl_role`, `sys_security_attribute`).

**Concerns.**
- The minus 1374 lines suggests they removed substantial existing code. Need to inspect what was removed before importing — could be deletion of tests they considered "not working."
- Mixes the ACL feature with a Dockerfile change (`python:3.11-slim` → `python:3.12`) and a major README rewrite for test instructions. Not atomic.
- Includes the test-removal noted in the PR description ("removed some not working tests"). Risky: tests should be fixed, not removed.

**Verdict.** **HIGH (ACL tools) but selective.** Cherry-pick the ACL-related code with new tests; reject the test-removal commits and the Python-version bump as unrelated.

---

### PR #55 — `Add Scripted REST API tools` (haim-nizri, +1224/-1)

**Source.** Same as `haim-nizri/servicenow-mcp` fork's `e9c8dd0` + `f546c78`.
**Verdict.** **MEDIUM (selective) — already on cherry-pick list.** The PR also includes the 648-line `chatbot.py` and the xti-namespace fix; cherry-pick only the Scripted REST API portions.

---

### PR #51 — `Add client credentials OAuth support and configurable API paths` (dasarunava97, +233/-8)

**New finding.** Two changes bundled:
1. **Client-credentials OAuth grant support** — makes `username`/`password` optional in `OAuthConfig`, adds intelligent fallback (try client_credentials first, fall back to password grant if user creds provided). Adds `resource_url` parameter for Azure AD-backed ServiceNow instances.
2. **Configurable API path** — replaces hardcoded `api/` with `api_path` field; adds `ServerConfig.api_url` computed property.

**Verdict.** **HIGH — merge selectively.** The configurable API path is generic and clean; client-credentials-as-primary is sound design. The Azure AD `resource_url` parameter adds enterprise compatibility. Note: this addresses Issue #50 (same author).

**Risks.** Conflicts with our planned commit 4 (the hardcoded-`.service-now.com` fix from our own playbook). Resolve by: take their `instance_url`-driven token URL construction, take their `api_path` config, take their client-credentials priority, leave their fallback logic in for backward compat.

---

### PR #48 — `feat(docker): add Docker support with security best practices` (tigredonorte, +212/-7)

**New finding — partial overlap with `ericstarkey` fork.** Adds:
- Non-root user in Dockerfile
- `.dockerignore`
- `docker-compose.yml`
- `requirements.txt`
- README docs for Docker + Claude Desktop config

**Verdict.** **MEDIUM — supersede with `ericstarkey/71e10d2` from fork analysis.** ericstarkey's commit goes further (Nginx + SSL + ApiKeyMiddleware + 22 tests); take that instead of this PR. The non-root-user and `.dockerignore` patterns from this PR are worth pulling individually if missing from ericstarkey's.

---

### PR #46 — `feat: Add uvx compatibility` (sam-at-luther, +94/-29)

**New finding.** Same root cause as `patricebechard 48b0915`: `tool_packages.yaml` not bundled in pip-installed packages, causing 0 tools to load. **This PR's fix is more thorough than patricebechard's:**
- Moves `config/` → `src/servicenow_mcp/config/` (package-internal location)
- Updates `pyproject.toml` with hatchling config to include YAML in wheel
- Updates `server.py` to use `importlib.resources.files()` for Python ≥3.9, `pkg_resources` fallback for older
- Maintains backward compat with file-path loading for development

Tested against `uvx`, `uvx --from git+...`, `pip install`, and dev mode.

**Verdict.** **HIGH — prefer this PR over `patricebechard 48b0915`.** Same problem solved more comprehensively. Required for `uvx` users (a substantial population — `uvx` is the standard MCP-launch tool).

---

### PR #42 — `Feature/add oauth` (rangamani54, +85/-73)

**New finding.** Adds OAuth token expiry + refresh-on-expiry + refresh-token expiry handling.

**Verdict.** **MEDIUM — overlaps with our planned playbook commit 6 and michaelbuckner's pattern.** Their implementation is short (85 lines vs. michaelbuckner's pattern). Quick read suggests it's competently done. Decision: prefer michaelbuckner's pattern (already in our playbook) because it's already battle-tested in the wild. If we discover michaelbuckner's pattern has the datetime-vs-float bug we identified, this PR is a worthwhile alternative.

---

### PR #37 — `feat: Add get_incident_by_number tool (#1)` (debianmaster, +11/-0)

**New finding.** Tiny PR — the tool was already implemented in `incident_tools.py` but never registered in `tool_utils.py`. This PR adds the registration.

**Verdict.** **HIGH (trivial port).** A 3-line registration fix. Take this verbatim or fold into our cleanup of ghost tools (torkian's `84e10ac` did the inverse — commented out 11 ghost tools — so the canonical fix is to register the unregistered ones AND comment out the truly missing ones).

---

### PR #36 — `[FEAT] Allow the MCP server to be deployed to Google Cloud Run` (xiangshen-dk, +432/-0, 6 files)

**New finding.** Adds:
- `Dockerfile`: `COPY config/ ./config/` (subset of torkian's `3cb44bd`)
- `server_sse.py`: `/health` endpoint for Cloud Run health checks
- `tool_utils.py`: registers `get_incident_by_number` (overlaps with PR #37)
- `DEPLOYMENT_GUIDE.md`, `deploy-with-secrets.sh` (Google Secret Manager), `.gcloudignore`

**Verdict.** **MEDIUM — selective.** Take the `/health` endpoint (small, generic — useful for any cloud deployment with health checks: K8s liveness probes, ECS, App Runner, Cloud Run). Skip the Cloud Run-specific deployment scripts (their setup is fine for a `docs/deploying-to-gcp.md` example but shouldn't be the canonical deployment story — that's docker-compose per ericstarkey).

---

### PR #35 — `Fixed zero available tools when using sse with Docker image built from Dockerfile` (rangamani54, +2/-1)

**Verdict.** **SUPERSEDE.** torkian's `3cb44bd` is the canonical fix for this same bug; PR #46 (uvx compat) addresses the broader root cause.

---

### PR #33 — `Add MseeP.ai badge` (lwsinclair, +2/-0)

**Verdict.** **SKIP.** A discovery-platform listing badge. Already merged into echelon main (`5e0e3bb`), so it's in our fork. Nothing to do.

---

### PR #31 — `Fix OAuth authentication by passing instance_url to AuthManager` (jessems, +50/-25)

**New finding.** This is **the same bug** our planned playbook commit 4 fixes (`AuthManager._get_oauth_token` accessing `oauth_config.instance_url` which doesn't exist). The author proposes:
1. Add `instance_url` parameter to `AuthManager.__init__`
2. Update `server.py` to pass `self.config.instance_url`
3. (Optional) implement both `client_credentials` and `password` grant types

**Verdict.** **HIGH — converge with our planned commit 4.** Their approach (add `instance_url` to constructor) is cleaner than the fix we sketched (build URL from `oauth_config.instance_url` directly, but that field doesn't exist). Adopt their approach. Optional client_credentials work overlaps with PR #51.

---

## Open issues (13)

### #64 — `Maintained fork available: torkian/servicenow-mcp` (torkian, 2026-04-07)

**Type.** Meta / discoverability — torkian announcing his maintained fork.
**Action for us.** Informational; reinforces that torkian is the de-facto active maintainer in the fork network. No code action.

---

### #63 — `Your project is listed on Spark — claim your listing` (venturecrew, 2026-03-31)

**Type.** Promotional/spam.
**Action for us.** Ignore.

---

### #54 — `Add new filter for assignment_group` (clguo-tw, 2026-02-06)

**Type.** Feature request.
**Already addressed.** clguo-tw implemented it in their own fork (`7f9dc92`).
**Action for us.** Cherry-pick clguo-tw's fork commit — already on the cherry-pick list. Closes this issue.

---

### #52 — `Missing tool to query work_notes and additional_comments in the Incident thread` (yinshangwei, 2026-01-21)

**Type.** Feature request — legitimate gap.
**Background.** ServiceNow stores `work_notes` and `comments` as journal fields (`sys_journal_field` table). Querying them requires either (a) including them via `sysparm_display_value=true` and parsing the journal stream, or (b) directly querying `sys_journal_field` filtered by `element_id=<incident sys_id>`.
**Priority.** **MEDIUM-HIGH.** Common need; work_notes are core to incident management.
**Action for us.** Add a `get_incident_journal` (or `get_incident_comments`) tool that queries `sys_journal_field` for an incident's `sys_id`, returns ordered timeline of `work_notes` and `comments`. Fold into our incident-tool expansion task.

---

### #50 — `Enhanced OAuth Authentication and API Configuration Flexibility in ServiceNow MCP` (dasarunava97, 2026-01-15)

**Type.** Feature request — same content as PR #51 (same author).
**Action for us.** Closes when we merge their changes from PR #51.

---

### #49 — `Installation in Claude does not work` (AArdusso, 2025-12-01)

**Type.** Install bug — virtualenv activation issue with Claude Desktop on macOS.
**Background.** Common Python+Claude-Desktop problem: Claude launches the MCP server outside the venv, so the `mcp-server-servicenow` script can't find its dependencies.
**Priority.** **HIGH** — blocks adoption.
**Action for us.** Two-part fix:
1. Document the canonical macOS install pattern: use absolute path to the venv's `python` interpreter in `claude_desktop_config.json` (`"command": "/Users/.../venv/bin/python"`, then `"args": ["-m", "servicenow_mcp.cli"]`).
2. Better long-term: ship as a `uvx`-compatible package (PR #46 + patricebechard's PR's-equivalent fix), so users can `uvx servicenow-mcp` with no venv concerns.
Folds into the docs revision and the uvx-compat work.

---

### #47 — `Support for OpenAI models` (PavelVeeamer, 2025-11-10)

**Type.** Misunderstanding of MCP architecture.
**Background.** MCP is model-agnostic — the server doesn't care which LLM connects to it. Comments on the issue clarify this.
**Action for us.** **No code action.** Document in README that any MCP-compatible client works (Claude Desktop, OpenAI clients via MCP bridge, custom MCP clients).

---

### #45 — `Add support for CMDB and configuration_item fields` (largeblastradius, 2025-10-21)

**Type.** Feature request.
**Already addressed.** torkian implemented full CMDB tools (`01bf610` + `7f01fe5`).
**Action for us.** Closes when we cherry-pick torkian's CMDB work.

---

### #44 — `Missing examples/sse_server_example.py file` (thsmale, 2025-09-11)

**Type.** Bug — README references a file that doesn't exist.
**Already addressed.** torkian fixed it (`e073ac4`).
**Action for us.** Closes when we cherry-pick torkian's commit.

---

### #43 — `Vulnerabilities` (scottw-kr, 2025-09-09) — **CRITICAL**

**Type.** Security audit — four findings from [mcpscan.ai](https://mcpscan.ai/results/generic-mcp?job_id=2871e588e30c460bac4785fa83a1b6d5):

1. **CRITICAL — Remote Code Execution via Script Management Tools.**
   - `execute_script_include` / `create_script_include` / `update_script_include` / `delete_script_include` are in the default `platform_developer` package.
   - Together they form a proxy for arbitrary Glide-script execution on the ServiceNow instance.
   - **Recommendation from auditor.** Disable in default packages. If needed, gate behind explicit human-in-the-loop approval.

2. **HIGH — OAuth 2.0 Password Grant exposes user credentials.**
   - The MCP server handles plaintext username/password to obtain an OAuth token (deprecated by OAuth BCP).
   - **Recommendation.** Deprecate password grant. Move to Authorization Code Grant or client_credentials.

3. **MEDIUM — Plaintext password in `claude_desktop_config.json`.**
   - `install_claude_desktop.sh` writes the ServiceNow password into a JSON config file.
   - **Recommendation.** Use OS keyring (macOS Keychain / Windows Credential Manager) or env vars.

4. **MEDIUM — Insecure default network binding `0.0.0.0` in Dockerfile.**
   - `CMD ["servicenow-mcp-sse", "--host=0.0.0.0", "--port=8080"]` exposes the server on all interfaces.
   - **Recommendation.** Default to `127.0.0.1`; document `--allow-remote` opt-in.

**Status of each finding for our fork.**
| # | Finding | Status |
|---|---|---|
| 1 | RCE via script_include tools | **Open — must address.** Mitigation aligns with the north-bound OAuth scope-gating already in our architecture plan; until that lands, remove `execute_script_include` and the destructive script tools from default packages. |
| 2 | Password grant insecurity | **Open — addressed by PR #51.** Make client_credentials the primary path; keep password grant available but document its deprecation. |
| 3 | Plaintext password in config | **Open — partial.** Document the risk. Long-term: secret-store ABC per our architecture plan. Short-term: add a README warning + deprecate `install_claude_desktop.sh` as a default install path. |
| 4 | 0.0.0.0 default binding | **Resolved by `fix/sse-auth-hardening`** (loopback default + `--allow-remote` opt-in + bearer token). This is exactly what hardening implements. |

**Priority.** **HIGHEST.** Address #1 immediately (one-line YAML edit), document #2 and #3 in README, ensure #4 lands when we merge `fix/sse-auth-hardening`.

---

### #39 — `Suggestion: add TOOL_PACKAGE_CONFIG_PATH to README` (ahuliangbo, 2025-08-11)

**Type.** Documentation gap.
**Action for us.** **LOW priority.** Fold into README rewrite — document `MCP_TOOL_PACKAGE_CONFIG_PATH` (or whatever the actual env var name resolves to after PR #46's package-internal config move).

---

### #34 — `Docker File missing "Copy Config" as a result tools are not loaded` (amrelhusseiny, 2025-07-31)

**Type.** Bug.
**Already addressed.** torkian's `3cb44bd`, also PR #35 and PR #36.
**Action for us.** Closes when we cherry-pick the fix.

---

### #26 — `attribute 'model_json_schema' is missing` (ibeketov, 2025-06-03)

**Type.** Bug — Pydantic v1/v2 compatibility issue with `OptimizationRecommendationsParams` and `UpdateCatalogItemParams`.
**Background.** These two classes use `@dataclass` instead of inheriting from Pydantic `BaseModel`, so `.model_json_schema()` doesn't exist on them. Comments include a community-supplied fix.
**Priority.** **MEDIUM.** Real bug that prevents the server from starting in some environments.
**Action for us.** Fix as part of our type-safety pass — convert these two classes to proper Pydantic v2 `BaseModel` subclasses with field definitions. (Note: torkian's `cb727c0` and Flowbie's CRUD-strip refactor probably touched these files; verify they don't already fix it incidentally.)

---

## Cross-cutting takeaways

### Convergence with our existing plans

These open PRs validate or refine items already in our playbook:

- **OAuth body logging fix** — our commit 3 ↔ PR #59 + torkian `ba56b83`. Three independent paths confirm this is the right fix.
- **Hardcoded `.service-now.com` URL** — our commit 4 ↔ PR #31 (jessems). Their cleaner approach (pass `instance_url` to `AuthManager` constructor) supersedes our sketch.
- **OAuth token refresh** — our commit 6 ↔ PR #42 (rangamani54) ↔ michaelbuckner's pattern. Three-way option; prefer the michaelbuckner pattern with the datetime-vs-float bug fixed.
- **0.0.0.0 default binding** — our commit 5 (port hardening) ↔ Issue #43 finding #4. Hardening branch resolves this.
- **`tool_packages.yaml` package-data fix** — our planned `patricebechard 48b0915` cherry-pick ↔ PR #46 (more thorough). Adopt PR #46 instead.

### New required additions

These are findings not previously in our plan:

1. **Issue #43 finding #1 (RCE) — IMMEDIATE FIX.** Remove `execute_script_include`, `create_script_include`, `update_script_include`, `delete_script_include` from default `platform_developer` and `full` packages. One-line YAML edit. Document the security rationale.
2. **Configurable API path (PR #51)** — generic improvement worth taking.
3. **Client-credentials OAuth as primary (PR #51)** — addresses Issue #43 finding #2.
4. **`/health` endpoint (PR #36 subset)** — useful for any container deployment.
5. **`get_incident_by_number` registration (PR #37)** — trivial registration fix; fold into ghost-tools cleanup.
6. **`get_incident_journal` tool (Issue #52)** — query `sys_journal_field` for work_notes/comments timeline. New tool, generic.
7. **Pydantic v2 fix (Issue #26)** — convert `OptimizationRecommendationsParams` + `UpdateCatalogItemParams` from dataclass to BaseModel.
8. **ACL tools (PR #56)** — substantial generic feature; selective port (skip the test-removal commits).
9. **Install-path documentation (Issue #49)** — document venv-aware Claude Desktop config; long-term ship via `uvx`.
10. **README warnings (Issue #43 #3 + #2)** — flag plaintext-password risk, password-grant deprecation.

### Upstream-PR opportunities

After our own fixes land, we should open PRs back to echelon for the genuinely community-benefiting fixes — these are the strongest candidates:

- **Tool-package YAML packaging fix** (PR #46 supersedes our patricebechard option) — already a PR, advocate for it.
- **OAuth body logging fix** — PR #59 already exists. Comment in support; if echelon doesn't merge, our fork is the de-facto patched version.
- **Hardcoded `.service-now.com` URL** — PR #31 already exists. Same.
- **Issue #43 finding #1 mitigation** — open as a new PR since echelon hasn't acknowledged the security issue in 8 months.
- **Pydantic v2 fix** — small, novel; open a new PR.
- **`get_incident_by_number` registration** — PR #37 already exists.

The pattern is: many obvious fixes are stuck in PR limbo at echelon. Our fork can serve as the de-facto reviewed-and-tested version while we advocate upstream.

### What this changes about the original playbook

The original 9-commit playbook in `ANALYSIS_OF_EXISTING_OPEN_SOURCE_SERVICENOW_MCP_SERVERS.md` is now better understood as **phase 1 only**. With fork commits, open PRs, and security findings now characterized, the integrated plan should be:

- **Phase 1 (original playbook)** — security baseline + auth hygiene + schema resources + NLP + CI matrix. ~9 commits.
- **Phase 2 (fork-driven foundations)** — torkian's helpers refactor, retry/backoff, rate limiting, pagination, bulk batch API, packaging fixes. ~10 commits.
- **Phase 3 (security findings + open PR resolution)** — Issue #43 #1 RCE mitigation, PR #51 client-credentials + api_path, PR #46 uvx compat, README warnings, Pydantic v2 fix. ~5 commits.
- **Phase 4 (domain expansion)** — torkian's CMDB/asset/SCTASK/time-card/syslog tools, nathanolds22's E2E + AI Agent suite, Flowbie's flow-tools cluster, klapom's platform-admin, russ430's widgets, dobromirmontauk's CSM, haim-nizri's Scripted REST, PR #56 ACL tools. ~25-40 commits.
- **Phase 5 (deployment + docs)** — ericstarkey's Docker/Nginx/auth, PR #36's `/health`, README rewrite addressing Issues #39, #49.

CLAUDE.md will be updated to reflect this phased structure as the new canonical plan.

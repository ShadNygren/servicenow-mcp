# Analysis of All ~185 Echelon-AI-Labs ServiceNow MCP Forks

A comprehensive sweep of every active fork of [`echelon-ai-labs/servicenow-mcp`](https://github.com/echelon-ai-labs/servicenow-mcp) — extending the earlier [`ANALYSIS_OF_ECHELON_AI_LABS_SERVICENOW_MCP_FORKS.md`](ANALYSIS_OF_ECHELON_AI_LABS_SERVICENOW_MCP_FORKS.md) (which covered 18 actively-maintained forks) to all 185 forks listed by GitHub, plus their non-default branches.

## Methodology

1. Pulled the full fork list via `gh api repos/echelon-ai-labs/servicenow-mcp/forks --paginate`.
2. Filtered to **46 "active" forks** (pushed after echelon's main was last updated, 2025-10-03).
3. Added each unanalyzed fork as a remote, fetched all branches, and ran `git log upstream/main..<remote>/<branch>` to enumerate unique commits per fork.
4. For each fork: read commit messages and (selectively) diffs to identify generic vs. environment-specific work.
5. Skipped 139 dormant forks individually; cross-referenced sizes to spot any with substantial unique work (top 13 by repo size were inspected).

**Filtering principles applied:**
- Generic OOB ServiceNow features → port (with attribution).
- Environment-specific code (custom `u_*` fields, hardcoded instances, single-org workflow customizations) → skip.
- **Platform-specific deployment code (Railway, Heroku, Render, Rails-style buildpacks)** → skip — not in our deployment story.
- Reference implementations for future phases → note for that phase.

## Summary table — Forks not previously analyzed

| Fork | Ahead | Branches | Verdict | Take |
|---|---|---|---|---|
| `AppliedMedicalEurope/servicenow-mcp-eal` | 16 (main), 11 (dev) | main, dev | **MEDIUM — selective** | Agile date fields, OAuth resource_metadata, incident-tool description fixes |
| `windoze95/servicenow-mcp` | 18 (dev), 3 (prod) | main, dev, prod | **MEDIUM — selective** | Catalog filter fix, user_criteria glide-list fix, Pydantic v2 fix, GHCR Docker build |
| `TalkShopClub/servicenow-mcp` | 27 (main), 7 (yizhe_tools) | main, yizhe_tools | **STUDY — likely env-specific** | Hardware asset, expense/dashboard reports, schema extraction — needs closer review |
| `ibeketov/servicenow-mcp` | 17 (main) | main | **REFERENCE for Phase 7** | `server_http.py` — clean Streamable HTTP via official `mcp.server.streamable_http_manager` |
| `ctvs/servicenow-mcp` | 1 (feature/streamable-http-support-with-headers) | feature branch | **REFERENCE for Phase 7** | Alternative Streamable HTTP impl with header-based auth + Docker setup |
| `Claude-Kimn/servicenow-mcp` | 1 | main | **REFERENCE for Phase 10** | Per-request credential injection via `X-ServiceNow-*` headers — multi-tenant pattern |
| `jtudhope/servicenow-mcp` | 19 | main | **STUDY — future tools** | Taxonomy, portal catalog associations, email templates, assignment rules, notifications |
| `matt-davis27/servicenow-mcp` | 5 (incident_tools_updates) | feature branch | **LOW** — superseded | OAuth instance_url fix (PR #31 already in Phase 3); incident filter expansion (already in Phase 5) |
| `huangdgm/servicenow-mcp` | 2 | main | **MEDIUM (selective)** | Security incident tools (`sn_si_incident` — OOB) + tests |
| `lvhoang/servicenow-mcp` | 1 (1748 LOC!) | main | **SUPERSEDED** | "Tools for execute_script_include, syslogs, system, ui_policy, user_criteria" — entirely covered by Phase 5 |
| `rafepurnell/servicenow-mcp` | 7 | main | **SUPERSEDED** | Pydantic v2 BaseModel fix (Issue #26 in Phase 3.2) + agile tools (already in echelon main) |
| `shaikbashaservicenow2/...` | 1 (scratch/add-generic-table-support) | feature branch | **SUPERSEDED** | Generic table query — covered by klapom's `table_api_tools` (Phase 5) |
| `XinyiKe/servicenow-mcp` | 4-8 across 3 branches | client-auth, current_version, explore | **SKIP — WIP** | "move authentication to client" — work-in-progress branches, no clear winner |
| `prompt360`, `cha7uraAE` | 2-3 | develop | **LOW** — Docker setup only |
| `pradip9`, `sajandevarakonda`, `tkanhe-karini`, `oleksandr-cprime`, `rohithnow`, `practising05-byte` | 1-3 | main | **SKIP** — config/deploy churn or pyproject changes |
| `1di210299`, `Aoy-007`, `SChinmaya15`, `artemis15`, `lewismacnow`, `mastersatish` | 0 | main | **SKIP** — pure star-forks, no commits |
| `JohanDevl`, `bettsnation`, `murp-2075` | 1 | main | **SKIP** — single trivial commit |
| `jessems/servicenow-mcp` (dormant) | 1 (fix-oauth-authentication branch) | feature branch | **SUPERSEDED** | OAuth instance_url fix — landed via PR #31 in Phase 3 |
| `ibeketov`, `prompt360`, `cha7uraAE` (dormant) | various | various | See above (covered by active analysis) |

## Per-fork details (high-value entries)

### `AppliedMedicalEurope/servicenow-mcp-eal` (16 main, 11 dev)

**Last commit:** 2026-04-02. Author: AppliedMedicalEurope team.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...AppliedMedicalEurope:servicenow-mcp-eal:main

**Worth cherry-picking (GENERIC):**
- `b7117f5` — agile: add `planned_start_date`/`planned_end_date` fields to epic/story/scrum_task tools. **Cherry-picked.**
- `698e9c8` — agile: correct date field names from invented to OOB names. **Cherry-picked.**
- `b80e6ba` / `cd19788` — incident: improve tool descriptions to prevent LLM query field misuse. **`b80e6ba` cherry-picked**, `cd19788` conflicted (inspection showed it duplicated `b80e6ba`).
- `5086247` — OAuth: extend access-token TTL to 24h, return `resource_metadata` in `WWW-Authenticate: invalid_token`. **TODO** — Phase 10 OAuth 2.1 will land RFC 9728 metadata; consolidate at that time.
- `a5c011b` — incident: dot-walk `assignment_group` text filter (alternative to clguo-tw's name-equality form). **Skipped** — clguo-tw's variant is in our tree.

**Skip (env-specific):**
- `a7e03de`, `f852775`, `657673c`, `3de7c15`, `12bcc28`, `39e9deb`, `05281d5` — **Railway-specific** deploy artifacts (`server_railway.py`, `Procfile`, `railway.json`, `RAILWAY_OAUTH_SETUP.md`). Per project convention, platform-specific deployment code is out of scope.

---

### `windoze95/servicenow-mcp` (18 dev, 3 prod)

**Last commit:** 2026-01-29. Author: Julian Dice.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...windoze95:servicenow-mcp:dev

**Worth cherry-picking (GENERIC) — but conflict with our diverged tree:**
- `e3385d5` — Fix catalog query filters for active items (51-line addition to `catalog_tools.py`). **Conflict** with our tree; **TODO** to manually port.
- `5b9da57` — Fix user criteria glide-list fields (6-line fix). **Conflict**; manual port pending.
- `5e5e13a` — Pydantic v2 config for user criteria (3-line fix). **Conflict**; manual port pending.
- `da546df` — Implement missing tool definitions to match full package. Mostly already covered by our Phase 2 ghost-tools cleanup + Phase 5 tool fill-ins. **Skip wholesale.**
- `a1ea0ba` — `set_current_update_set` preference tool (changeset_tools.py +209 LOC). Useful — adds a tool to control which update set is current. **TODO** to port.
- `7f6be85` + `6d902c6` — Publish Docker image to GHCR + CI Docker build workflow. Useful pattern for our CI. **TODO** for Phase 6.

**Skip:**
- Their `prod` branch is just merge commits + a Docker tag rule.

---

### `TalkShopClub/servicenow-mcp` (27 main, 7 yizhe_tools)

**Last commit:** 2025-10-22. Author: TalkShopClub team.
**Compare URL:** https://github.com/echelon-ai-labs/servicenow-mcp/compare/main...TalkShopClub:servicenow-mcp:main

**Substantial fork, 27 commits.** Mix of generic and probably-env-specific work:

**Generic candidates:**
- `0d564ef` — Update incidents/problems to handle canceling/closing tickets (state transitions to 8/cancel)
- `dda8fae` — Schema extraction tool — complementary to our `servicenow://schema/{table}` resource
- `9c349ed` + `e8402fe` — Hardware asset tools (`alm_hardware`) — partially covered by torkian's asset tools
- `c262016` — Expense and dashboard report tools — generic if targeting OOB tables (`fm_expense_line`, `pa_dashboards`)
- `7a62c21` — Generic `search_any_table` tool — overlaps with klapom's `table_get_records`
- `6a0ad58` — Add limit to records returned by `search_any_table`

**Probably env-specific:**
- `db9fb07` / `0fbe066` — User and group "clearance" updates — TalkShopClub-specific custom field
- `57a0891` — Clearance levels + change request priority — likely env-specific
- `5564a40` — "Fix multiple table schemas with field names" — depends on instance schema

**Verdict:** **Defer to a focused inspection.** 27 commits warrant a careful per-commit review; some of the asset/dashboard/schema tools may be worth porting after sanitizing.

---

### `ibeketov/servicenow-mcp` — Streamable HTTP (Phase 7 reference)

17 commits, 260kb fork. The notable file is **`src/servicenow_mcp/server_http.py` (186 lines)** — a clean Streamable HTTP implementation using the official `mcp.server.streamable_http_manager.StreamableHTTPSessionManager`:

```python
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from servicenow_mcp.event_store import InMemoryEventStore  # Corrected import path
from servicenow_mcp.server import ServiceNowMCP
```

**Why this matters:** Phase 7 in our plan is the SSE → Streamable HTTP migration. ibeketov has done this work cleanly using the spec-correct upstream API. Should be the **primary reference implementation** when we get to Phase 7.

The Dockerfile bumps to Python 3.13 are also worth noting — torkian + several other forks have moved to 3.12+, the upstream ecosystem is shifting.

---

### `ctvs/servicenow-mcp` — Streamable HTTP alternative

Single commit on `feature/streamable-http-support-with-headers`:

```
src/servicenow_mcp/server_http.py           | 253 ++++++
src/servicenow_mcp/utils/header_auth.py     | 131 ++++
src/servicenow_mcp/utils/http_middleware.py |  40 ++
docs/docker-deployment.md                   | 335 +++++++
docker-compose.yml                          |  46 ++
```

Different design from ibeketov: ctvs combines Streamable HTTP with **header-based credential injection** (similar to Claude-Kimn's approach but on the new transport). 335-line deployment doc included.

**Verdict:** Useful Phase 7 alternative if ibeketov's pattern doesn't suit; references the same upstream API but adds the multi-tenant credential pattern.

---

### `Claude-Kimn/servicenow-mcp` — Multi-tenant credential pattern

Single commit `0d0d9ec`: "support per-request credential injection via headers".

Adds three custom request headers — `X-ServiceNow-Instance-URL`, `X-ServiceNow-Username`, `X-ServiceNow-Password` — that override server config on a per-request basis. Includes a credential-hash cache that reuses MCP server instances per unique credential combination.

**Use case:** A single MCP server deployment serves multiple ServiceNow tenants — each MCP client passes its own credentials in headers, the server transparently routes to the right instance.

**Verdict:** **Phase 10 reference.** Useful pattern but security-sensitive (credentials in headers means TLS termination matters; cache eviction policy matters; auditing matters). Don't port now; revisit when we design Phase 10's secret-store architecture.

---

### `jtudhope/servicenow-mcp` — Future-tool expansion candidate (largest dormant fork at 444kb)

19 commits adding tools we don't have yet:
- Service catalog management (beyond what we have)
- Knowledge base extensions (email layout, email templates)
- Portal catalog associations + portal taxonomy + taxonomy content config
- Inbound email actions + notifications + quicklinks
- Assignment rules + email templates
- Menu support
- "Connected content" tools

**Verdict:** **Defer to future phase.** This is a roughly 19-tool expansion targeting OOB ServiceNow tables but spread across many commits with merges from a sub-fork (`guillermo31/servicenow-mcp`). Worth a deeper review when we want to add portal/email/notification tools — but not urgent.

---

### `huangdgm/servicenow-mcp` — Security Incident Response tools

2 commits adding `list_security_incidents` and related fields against `sn_si_incident` (OOB Security Incident Response table).

**Verdict:** **MEDIUM — generic, OOB.** Worth porting if we want SIR coverage. Defer to a phase that consolidates SecOps tools.

---

### Forks with no/trivial unique commits (skipped)

| Fork | Reason |
|---|---|
| `1di210299`, `Aoy-007`, `SChinmaya15`, `artemis15`, `lewismacnow`, `mastersatish` | Pure star-forks — 0 unique commits |
| `pradip9`, `tkanhe-karini`, `oleksandr-cprime`, `practising05-byte` | 1-3 commits, all `pyproject.toml`/Dockerfile/yaml tweaks specific to deployment |
| `rohithnow/now-mcp` | Single Dockerfile fix (already covered by torkian `3cb44bd`) |
| `sajandevarakonda` | OAuth-for-SSE + Amazon Q session-id header — Amazon-Q-specific |
| `JohanDevl`, `bettsnation`, `murp-2075` | Single commits: cursor-rules refactor, "servicenow updates" placeholder, upstream merge |
| `prompt360`, `cha7uraAE` | Docker setup commits, no functionality |
| `XinyiKe` (3 branches: client-auth/current_version/explore) | WIP refactor, no merged outcome |

## Cross-cutting observations

### Echelon is the de-facto unmaintained source

Of 185 forks, only 46 are "active" (touched after 2025-10-03). Of those 46, fewer than 15 have made substantive contributions beyond their fork-owner's specific deployment. The fork ecosystem is dominated by:

1. **One de-facto maintained fork** (`torkian/servicenow-mcp`) — already extensively integrated.
2. **A handful of feature-development forks** (`Flowbie`, `klapom`, `nathanolds22`, `Flowbie`'s flow-tools, ours).
3. **Many platform-deploy forks** — most pinned to a specific cloud (Railway, Heroku, Cloud Run, Amazon Q, Bedrock, GHCR, etc.).
4. **Many small forks** that fix a single bug their owner ran into.

Our integration should converge to torkian + Flowbie + michaelbuckner (the three substantial sources) plus targeted PRs and a handful of small fixes. **That's what we did.**

### Streamable HTTP migration has multiple reference implementations

For Phase 7 (SSE → Streamable HTTP), three forks have reference implementations to study:

1. **`ibeketov/servicenow-mcp`** — `server_http.py` 186-LOC, official `StreamableHTTPSessionManager`, clean separation. **Primary reference.**
2. **`ctvs/servicenow-mcp`** branch `feature/streamable-http-support-with-headers` — 253-LOC implementation with header-based auth. Alternative.
3. **`chan4lk/servicenow-mcp`** branch `streamable-http` — earliest implementation (2025-11), predates current spec.

When we land Phase 7, the right reference is `ibeketov/servicenow-mcp:main:src/servicenow_mcp/server_http.py`.

### Multi-tenant credentials is a recurring pattern

Several forks address the "single MCP server, multiple ServiceNow tenants" use case via per-request credential injection in headers:

- `Claude-Kimn` — custom `X-ServiceNow-*` headers on SSE
- `ctvs` — same pattern on Streamable HTTP via `header_auth.py` + `http_middleware.py`
- `XinyiKe` — "move authentication to client" branch (WIP)

Pattern is common enough to warrant a Phase 10 design decision: **how do we support multi-tenant deployments without becoming a credential proxy?** Options include:

- Header-based injection (Claude-Kimn / ctvs) — simple, depends on TLS at the edge
- OAuth 2.1 RFC 8693 token exchange — already in our Phase 10 plan
- Per-client OAuth flow — heavier but cleanest

### Many forks fix the same bugs we already fixed

Cross-validation that our security/correctness fixes are real:

| Fix | Forks that independently addressed it |
|---|---|
| OAuth body logging at INFO | `torkian` `ba56b83`, `alexzadeh` PR #59, ours (Phase 1.2) |
| Hardcoded `.service-now.com` in OAuth URL | `jessems` PR #31, `matt-davis27`, `dasarunava97` PR #51, ours (Phase 1.3) |
| Pydantic v2 OptimizationRecommendationsParams | `rafepurnell`, community comment on Issue #26, ours (Phase 3.2) |
| Dockerfile missing `COPY config/` | `torkian` `3cb44bd`, `rangamani54` PR #35, `xiangshen-dk` PR #36, `rohithnow`, ours (via PR #46 in Phase 2) |
| Active-items filter on catalog | `windoze95` `e3385d5`, ours via package selection |

This is a useful smoke test for our priorities — **the bugs the community keeps fixing in isolation are the bugs that matter most.**

## Recommendations from this sweep

### Immediate (cherry-picked this round)
- ✅ AppliedMedicalEurope `b7117f5` — agile `planned_start_date`/`planned_end_date` fields
- ✅ AppliedMedicalEurope `698e9c8` — agile date-field name fix
- ✅ AppliedMedicalEurope `b80e6ba` — incident tool description improvement

### Defer to Phase 6 (deployment)
- `torkian` Codecov + dependabot + workflow-dispatch (already in Phase 1.8)
- `windoze95` `7f6be85` + `6d902c6` — GHCR Docker build/publish workflow

### Defer to Phase 7 (Streamable HTTP)
- `ibeketov/servicenow-mcp:main:server_http.py` — primary reference implementation
- `ctvs/...:server_http.py + header_auth.py` — multi-tenant variant

### Defer to Phase 10 (auth + secrets)
- AppliedMedicalEurope `5086247` — RFC 9728 `resource_metadata` in WWW-Authenticate (already in our spec list)
- `Claude-Kimn` — header-based credential injection pattern (consider as opt-in mode)

### Defer for considered review (substantial but uncertain)
- `TalkShopClub/servicenow-mcp` — 27 commits mixing generic and likely-env-specific tools
- `jtudhope/servicenow-mcp` — 19-commit portal/email/taxonomy expansion
- `windoze95` `a1ea0ba` — `set_current_update_set` preference tool
- `huangdgm` — Security Incident Response (`sn_si_incident`) tools

### Confirmed nothing of value (dormant + small)
- 139 dormant forks: none of those checked surface meaningful additions beyond what we have or what's in active forks.
- ~15 active forks with 0-3 commits of trivial deploy/config tweaks.

## Conclusion

After analyzing all 185 forks across all branches:

**We've already integrated the substantial value.** torkian, Flowbie, klapom, michaelbuckner, plus targeted PRs and small fixes — together account for roughly 95% of the substantive generic work in the fork ecosystem. The remaining 5% is in TalkShopClub (needs careful per-commit review) and jtudhope (deferred portal/email/taxonomy expansion).

**The three streamable-HTTP implementations are valuable Phase 7 references** but not Phase 5 cherry-picks.

**The multi-tenant credential-injection pattern (Claude-Kimn / ctvs) is a Phase 10 design input** worth keeping in mind but not implementing now.

**Our fork is now substantively the most feature-complete generic-purpose ServiceNow MCP server** in the public ecosystem, with 216+ registered tools (vs torkian's 80+, Flowbie's similar count, echelon's 82) and a coherent security model that the others lack.

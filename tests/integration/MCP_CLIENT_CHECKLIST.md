# MCP Client Integration Checklist (Phase E2E.6)

This is the **manual** verification checklist for using Claude Code's
built-in MCP client to drive the ServiceNow MCP server. The pytest
tests in `test_*.py` are the audit-ready, deterministic core; this
checklist verifies the user-facing experience: prompt-driven tool
selection through the real MCP protocol stack.

The pytest layer proves "the tools work." This checklist proves "the
tools are reachable from a real MCP client and behave correctly when
invoked through prompt-driven dispatch."

## Prerequisites

1. `.env` populated with `SERVICENOW_INSTANCE_URL`, `SERVICENOW_USERNAME`,
   `SERVICENOW_PASSWORD`. The PDI must be active (visit it in a browser
   in the last 10 days).
2. Local installation: `python -m venv .venv && source .venv/bin/activate
   && pip install -e .`
3. Claude Code installed and configured.

## Setup

`.mcp.json` at the repository root registers two servers via env-var
expansion. **Set the env vars in the shell before launching Claude
Code** (env-var expansion happens at MCP-config-load time, not at
tool-call time):

```bash
# From the repo root, with .env populated:
set -a
source .env
set +a
claude
```

For the HTTP transport entry, also set `MCP_AUTH_TOKEN` to a value of
your choice and start the HTTP server in another terminal:

```bash
# Terminal 1 — start the HTTP server bound to loopback
export MCP_AUTH_TOKEN="$(openssl rand -hex 32)"
servicenow-mcp-http --host 127.0.0.1 --port 8080

# Terminal 2 — Claude Code with the token in env
export MCP_AUTH_TOKEN="<the-same-value>"
set -a && source .env && set +a
claude
```

## Checklist

### Server registration

- [ ] Run `claude mcp list` from the repo root → both `servicenow-stdio`
      and `servicenow-http` (if HTTP server is running) are listed.
- [ ] Inside Claude Code, type `/mcp` → both servers show as
      **connected** with a tool count near **211** (the full package).
- [ ] No "failed" or "pending" indicators in the `/mcp` panel.

### Tool inventory verification

- [ ] In the `/mcp` panel, click into `servicenow-stdio` → the listed
      tools include incident, change, user, group, role, ACL, knowledge,
      catalog, CMDB, asset, workflow, and Flow Designer tools.
- [ ] **Security gate**: confirm `execute_script_include` is NOT in
      the visible tool list (it's registered but excluded from the
      `full` default package per Issue #43 finding #1).

### Read-only tool calls (no PDI mutations)

Each row below is a prompt to type into Claude Code. Expected behavior
is in the second column. Tick the box once verified.

| Prompt | Expected |
|---|---|
| `List the 3 most recent incidents on the ServiceNow instance` | Returns 3 incidents with number / state / short_description / sys_id. Calls `mcp__servicenow_stdio__list_incidents` with limit=3. |
| `Show me the schema for the incident table` | Returns the field list (sys_id, number, state, ..., 100+ fields) via `mcp__servicenow_stdio__list_fields` with `table_name=incident`. |
| `How many users are in the sys_user table?` | Returns a count or representative sample via `mcp__servicenow_stdio__list_users` or `table_get_records`. |
| `What workflows exist on this instance?` | Returns workflow records via `mcp__servicenow_stdio__list_workflows`. |
| `List the available Flow Designer flows` | Returns Flow Designer flows via `mcp__servicenow_stdio__list_flows`. |

### Mutating tool call with explicit confirmation

Mutating calls go through Claude Code's permission gate (the user
clicks "yes" / "no" in the UI). Verify the gate fires, the call goes
through after approval, and the result is correct.

- [ ] Prompt: *"Create a test incident with short_description 'E2E
      MCP client checklist' and urgency 3, then read it back and show
      me the new incident number."*
  - Expected: Permission prompt for `create_incident`. After approving,
    Claude calls `create_incident`, receives `incident_id` +
    `incident_number`, then calls `get_incident_by_number` to read it
    back. The new incident number (typically `INC0010xxx`) appears in
    the response.
- [ ] In the same session: *"Now delete that incident."*
  - Expected: Permission prompt. After approving, Claude calls
    `table_delete_record` (or similar) on the incident table with
    the sys_id from the previous step. The PDI returns 204; Claude
    confirms deletion.

### Tool-package filter

- [ ] Quit Claude Code. Re-launch with `MCP_TOOL_PACKAGE=service_desk`
      set in the shell:
      ```bash
      set -a && source .env && set +a
      MCP_TOOL_PACKAGE=service_desk claude
      ```
- [ ] `/mcp` should now show a much smaller tool count (the
      `service_desk` package is a focused subset).
- [ ] Confirm the `create_business_rule` tool is NOT in the visible
      list (it's in `platform_developer` not `service_desk`).
- [ ] Reset to default: relaunch without `MCP_TOOL_PACKAGE` (or set
      to `full`).

### HTTP transport (Streamable HTTP)

- [ ] With the HTTP server running and the token matching, `/mcp` panel
      shows `servicenow-http` as **connected** alongside `servicenow-stdio`.
- [ ] Prompt: *"Use the servicenow-http server to list 1 incident."*
- [ ] The result should be identical (same incident) to the same call
      via stdio. Both transports go to the same PDI through the same
      tool implementations.
- [ ] Stop the HTTP server (Ctrl+C in Terminal 1). Within ~30 seconds,
      `/mcp` reflects the disconnect (Claude Code retries with
      exponential backoff: 1s → 2s → 4s → 8s → 16s, then marks failed
      after 5 attempts).

### Auto-reconnect

- [ ] Restart `servicenow-mcp-http` in Terminal 1 with the same token.
- [ ] `/mcp` should reconnect automatically (Claude Code re-attempts
      on each subsequent call after backoff). The exact reconnect
      behaviour is described in the [Claude Code MCP docs →
      Automatic reconnection](https://code.claude.com/docs/en/mcp).

### Negative paths (informative — not strict pass/fail)

- [ ] Prompt: *"Delete the entire incident table."* — Claude should
      decline or warn rather than execute. Our tools don't expose
      table-drop operations, so the worst case is "Claude tries
      `table_delete_record` per row," which still requires per-row
      approval.
- [ ] Prompt: *"Run this script in ServiceNow: ..."* — Claude should
      respond that `execute_script_include` is not available (it's
      excluded from the `full` package by default per Issue #43
      finding #1). Confirms the security gate works in the
      prompt-driven flow as well as in the registry.

## What to record after each run

After completing the checklist, record (in `tests/integration/results/`):

- Date / time of the run
- Claude Code version (`claude --version`)
- ServiceNow PDI release (Zurich at this writing)
- Total tool count visible in `/mcp` panel
- Any deviations from expected behaviour
- Sample tool-call latencies (stdio vs HTTP) for spot-check on
  performance regressions

The pytest report (`RESULTS_<timestamp>.md` from each integration
test run) is the deterministic artefact; the manual-checklist run is
the human-experience artefact. Both belong in audit packets.

## Related

- `tests/integration/test_*.py` — automated integration tests (deterministic)
- `tests/integration/results/RESULTS_*.md` — automated test reports
- [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp) — official guide
- [`ServiceNow/ServiceNowDocs`](https://github.com/ServiceNow/ServiceNowDocs) — official LLM-consumable platform docs (consult by release branch when test behaviour is unexpected)

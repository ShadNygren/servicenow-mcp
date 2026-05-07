# ServiceNow MCP Server

A Model Context Protocol (MCP) server for ServiceNow. Lets Claude (and any MCP-compatible client) read ServiceNow data and execute actions through the ServiceNow Table and REST APIs.

> **216+ tools registered · 919 tests passing · 4 mcpscan.ai security findings mitigated · MIT licensed.**

## Fork notice

This is a maintained, security-hardened, feature-consolidated fork of [`echelon-ai-labs/servicenow-mcp`](https://github.com/echelon-ai-labs/servicenow-mcp). Upstream has been effectively dormant since October 2025 (no PRs merged in 7+ months as of writing). This fork serves as the de-facto reviewed-and-tested version of the project.

**Sources integrated** (all MIT-licensed; see [`NOTICE`](NOTICE) for per-component copyright):

| Source | What we took |
|---|---|
| `echelon-ai-labs/servicenow-mcp` | Core server, 80+ baseline tools, the `fix/sse-auth-hardening` branch (merged as a real merge commit, preserving upstream authorship) |
| `michaelbuckner/servicenow-mcp` | Natural-language processor + `nl_power_user` tool package |
| `torkian/servicenow-mcp` | Helpers refactor (-740 LOC duplication), retry/backoff, rate limiting, pagination, bulk batch API, 80% test coverage, GH Actions CI/CodeQL/Dependabot, CMDB tools, asset tools, asset-contract tools, SCTASK + time-card, syslog tools, UI policy + user criteria, security-gated `execute_script_include` |
| `Flowbie/servicenow-mcp` | SnowResponse envelope, identifier resolver, integration-test gate, full Flow Designer suite (36 tools targeting `sys_hub_*`) |
| `klapom/servicenow-mcp` | Platform admin (business rule, OAuth, REST message, scheduled job, sys_dictionary, table API tools), data integration (import sets, transform maps, scheduled imports) |
| `nathanolds22/servicenow-mcp` | Used as design reference (deferred large port due to security-sensitive script-execution tools) |
| `russ430/servicenow-mcp` | Service Portal widget tools (`sp_widget`) |
| `dobromirmontauk/servicenow-mcp` | CSM tools (case correlation, accounts, locations, products) — sanitized of fork-specific framing |
| `haim-nizri/servicenow-mcp` | Scripted REST API tools (`sys_ws_definition` + `sys_ws_operation`) |
| `ericstarkey/servicenow-mcp` | Docker Compose + Nginx (opt-in) deployment recipe |
| `AppliedMedicalEurope/servicenow-mcp-eal` | Agile date field fixes, incident tool description hardening |
| **PRs cherry-picked from echelon** | PR #46 (uvx packaging), PR #51 (client-credentials OAuth + configurable api_path), PR #56 (ACL/Role/Security Attribute tools), PR #36 (`/health` endpoint) |
| **Issues fixed** | #26 (Pydantic v2), #43 findings 1/2/4 (RCE, password-grant, 0.0.0.0 binding), #45 (CMDB), #49 (install path), #50 (OAuth flexibility), #52 (work_notes/comments timeline), #54 (assignment_group filter) |

The full architectural rationale, fork survey, PR/issue analysis, and 185-fork comprehensive sweep:

- [`ANALYSIS_OF_EXISTING_OPEN_SOURCE_SERVICENOW_MCP_SERVERS.md`](ANALYSIS_OF_EXISTING_OPEN_SOURCE_SERVICENOW_MCP_SERVERS.md) — 3-server comparative review + original execution playbook
- [`ANALYSIS_OF_ECHELON_AI_LABS_SERVICENOW_MCP_FORKS.md`](ANALYSIS_OF_ECHELON_AI_LABS_SERVICENOW_MCP_FORKS.md) — 18 active-fork survey
- [`ANALYSIS_OF_ECHELON_AI_LABS_PRS_AND_ISSUES.md`](ANALYSIS_OF_ECHELON_AI_LABS_PRS_AND_ISSUES.md) — 15 open PRs + 13 open issues at echelon
- [`ANALYSIS_OF_ALL_ECHELON_FORKS.md`](ANALYSIS_OF_ALL_ECHELON_FORKS.md) — comprehensive 185-fork sweep with verdicts

License is MIT (matching all upstream sources). See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for per-component attribution.

## Security notice

Before deploying this server, read these:

1. **Default packages do NOT expose `execute_script_include` and the script-management write/delete tools.** Together, those tools form an arbitrary-code-execution sink on the connected ServiceNow instance — an LLM with access to them can write and run Glide scripts in your tenant. They remain registered in code; opt in only behind a human-in-the-loop approval flow. (Issue [#43 finding #1](https://github.com/echelon-ai-labs/servicenow-mcp/issues/43), addressed in this fork.)

2. **OAuth password grant is supported but discouraged.** It requires the server to handle plaintext ServiceNow user credentials — the OAuth Best Current Practice deprecates it. Prefer the `client_credentials` grant. The server still supports password grant for environments that have it as a hard requirement.

3. **Never put your ServiceNow password in `claude_desktop_config.json` directly.** Configure credentials via environment variables loaded at runtime instead. Plaintext passwords in user-readable JSON files are a real exfiltration risk if your machine is shared, your shell history is logged, or your dotfiles are synced.

4. **HTTP transport binds to loopback by default** (since the `fix/sse-auth-hardening` merge). To expose the server to a non-loopback interface, pass `--allow-remote` AND set `MCP_AUTH_TOKEN` — without both, the server refuses to bind. Bearer-token, Host-allowlist, and Origin-allowlist defenses are all on by default.

5. **Phase 7 retired the SSE transport in favor of Streamable HTTP** (the MCP spec's current HTTP transport). The single `/mcp` endpoint replaces the older `/sse` + `/messages/` pair. Run `servicenow-mcp-http` instead of `servicenow-mcp-sse`. Migration table is in [Streamable HTTP Mode → Migration from SSE](#migration-from-sse) below.

6. **Phase 9 (v0.9.x) made the entire HTTP path async.** All ~211 tool functions and the OAuth refresh path now use `httpx.AsyncClient` instead of sync `requests`. The server can serve many concurrent MCP sessions from many AI agents simultaneously without one slow tool call blocking the event loop, with built-in connection pooling and a serialised OAuth refresh that fires exactly one token POST per expiry window even under heavy concurrent load. See [Concurrency and async architecture](#concurrency-and-async-architecture) below.

## Quick start with a ServiceNow Personal Developer Instance (PDI)

ServiceNow provides free, fully-featured developer instances at `https://devXXXXX.service-now.com`. Best testing target.

1. **Sign up** at [developer.servicenow.com](https://developer.servicenow.com) and click "Request Instance" — provisioning takes a few minutes.
2. **Save the admin password and instance URL.** You'll need them for `SERVICENOW_INSTANCE_URL`, `SERVICENOW_USERNAME`, `SERVICENOW_PASSWORD`.
3. **Log in at least once every 10 days** — idle instances are reclaimed.
4. **The standard ITSM stack ships pre-activated** (incident, change, problem, knowledge, catalog, CMDB, sys_user). Specialized plugins (Agile 2.0, AI Agent platform, Service Portal extensions) need explicit activation.

For local testing during development:
- Use **basic auth** (admin user/pass) — simplest path.
- Run [**MCP Inspector**](https://github.com/modelcontextprotocol/inspector) against the local server to exercise tools manually.
- Use the PDI's built-in **REST API Explorer** to validate auth and query syntax before debugging from the MCP layer.

**Recommended LLM knowledge source.** [`ServiceNow/ServiceNowDocs`](https://github.com/ServiceNow/ServiceNowDocs) is ServiceNow's official, free, monthly-updated markdown documentation explicitly formatted for LLM consumption (one branch per release: `xanadu`, `yokohama`, `zurich`, `australia`, `main`); we consult it as the authoritative reference when designing tests, validating platform behavior (e.g., confirming the incident `state=6` ACL restriction on Zurich is documented platform behavior rather than a tool bug), and resolving questions about specific releases.

## Installation

### Prerequisites

- Python 3.11 or higher
- A ServiceNow instance with appropriate access credentials (a free PDI is fine)

### Setup

1. Clone this repository:
   ```
   git clone https://github.com/ShadNygren/servicenow-mcp.git
   cd servicenow-mcp
   ```

2. Create a virtual environment and install the package:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

3. Create a `.env` file with your ServiceNow credentials:
   ```
   SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com
   SERVICENOW_USERNAME=your-username
   SERVICENOW_PASSWORD=your-password
   SERVICENOW_AUTH_TYPE=basic  # or oauth, api_key
   ```

## Usage

### Standard (stdio) Mode

To start the MCP server:

```
python -m servicenow_mcp.cli
```

Or with environment variables:

```
SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com SERVICENOW_USERNAME=your-username SERVICENOW_PASSWORD=your-password SERVICENOW_AUTH_TYPE=basic python -m servicenow_mcp.cli
```

### Using with Claude Code (built-in MCP client)

A project-scoped [`.mcp.json`](.mcp.json) at the repo root registers the server with Claude Code's built-in MCP client. To use it, set the env vars from your `.env` in the shell, then launch Claude Code from the project root:

```bash
set -a && source .env && set +a
claude
```

`claude mcp list` should show `servicenow-stdio: ✓ Connected`. Inside Claude Code, the `/mcp` panel reports the tool count (~211 for the `full` package). To run the HTTP transport instead, start `servicenow-mcp-http` in a second terminal with `MCP_AUTH_TOKEN` set; the same `.mcp.json` registers `servicenow-http` against `127.0.0.1:8080/mcp` with bearer auth.

The full manual verification flow (server registration, read-only tool calls, mutating-call permission gates, tool-package filtering, HTTP transport, auto-reconnect) is in [`tests/integration/MCP_CLIENT_CHECKLIST.md`](tests/integration/MCP_CLIENT_CHECKLIST.md).

### Streamable HTTP Mode

The ServiceNow MCP server can run as a network server using **Streamable HTTP** — the MCP spec's HTTP transport. A single endpoint at `/mcp` handles both request/response and server-pushed streaming over chunked HTTP.

> Phase 7 retired the older Server-Sent Events (SSE) transport (`/sse` + `/messages/` endpoints). The Streamable HTTP endpoint at `/mcp` replaces both. See [Migration from SSE](#migration-from-sse) below if you're upgrading from a pre-v0.7 deployment.

> **Security:** the HTTP transport authenticates every request with a bearer token and rejects requests whose `Host` or `Origin` headers are not in an allowlist. By default it binds to `127.0.0.1` only; non-loopback bind requires `--allow-remote` and an explicit `MCP_AUTH_TOKEN`. The `/health` endpoint bypasses the bearer-token check (so platform liveness probes work) but still enforces the Host allowlist.

#### Starting the HTTP Server (loopback, local dev)

```
servicenow-mcp-http
```

The server binds `127.0.0.1:8080`, generates a random bearer token, and prints it once to stderr:

```
[servicenow-mcp-http] generated auth token: <random-token>
```

Use that token on every request:

```
curl -N -H "Authorization: Bearer <random-token>" http://127.0.0.1:8080/mcp
```

Liveness probe (no token needed):

```
curl http://127.0.0.1:8080/health
# → OK
```

To pin a stable token, set `MCP_AUTH_TOKEN` in `.env` (then no token is auto-generated).

#### Exposing the HTTP Server beyond loopback

Non-loopback bind is opt-in and requires both `--allow-remote` and an explicit `MCP_AUTH_TOKEN`:

```
MCP_AUTH_TOKEN=$(openssl rand -hex 32) \
servicenow-mcp-http --host=0.0.0.0 --port=8080 --allow-remote
```

If your reverse proxy (nginx, Caddy, ALB, Cloudflare, etc.) forwards a non-loopback `Host` header, set the env var:

```
MCP_ALLOWED_HOSTS=mcp.internal,mcp.internal:8080
```

Loopback hosts (`127.0.0.1`, `localhost`, `[::1]`) are always allowed.

#### Endpoints

- `/mcp` — Streamable HTTP MCP endpoint (bearer-token required)
- `/health` — Liveness probe, returns `200 OK` (Host allowlist applies; bearer not required)

#### Programmatic example

```python
from servicenow_mcp.server_http import create_servicenow_mcp
from servicenow_mcp.transport_security import (
    build_allowed_hosts, build_allowed_origins, resolve_auth_token,
)

mcp = create_servicenow_mcp(
    instance_url="https://your-instance.service-now.com",
    username="your-username",
    password="your-password",
)

# Loopback bind, auto-generated bearer token (printed to stderr).
auth_token = resolve_auth_token(
    allow_remote=False, transport_name="my-app",
)
allowed_hosts = build_allowed_hosts(host="127.0.0.1", port=8080)
allowed_origins = build_allowed_origins(allowed_hosts)
mcp.start(
    host="127.0.0.1", port=8080,
    auth_token=auth_token,
    allowed_hosts=allowed_hosts,
    allowed_origins=allowed_origins,
)
```

#### Migration from SSE

The pre-v0.7 SSE transport (`servicenow-mcp-sse`, `/sse` + `/messages/`) was removed in Phase 7. To migrate:

| Was | Becomes |
|---|---|
| `servicenow-mcp-sse` (console script) | `servicenow-mcp-http` |
| `http://host:port/sse` (client URL) | `http://host:port/mcp` |
| `/messages/` (POST endpoint) | `/mcp` (single unified endpoint) |
| `from servicenow_mcp.server_sse import ...` | `from servicenow_mcp.server_http import ...` |
| `from servicenow_mcp.server_sse import SecurityMiddleware` | `from servicenow_mcp.transport_security import SecurityMiddleware` |

Bearer token, Host allowlist, Origin allowlist, `MCP_AUTH_TOKEN`, `MCP_ALLOW_REMOTE`, `MCP_ALLOWED_HOSTS`, and the `/health` endpoint behave identically — only the URL paths changed.

## Tool Packaging (Optional)

To manage the number of tools exposed to the language model (especially in environments with limits), the ServiceNow MCP server supports loading subsets of tools called "packages". This is controlled via the `MCP_TOOL_PACKAGE` environment variable.

### Configuration

1.  **Environment Variable:** Set the `MCP_TOOL_PACKAGE` environment variable to the name of the desired package.
    ```bash
    export MCP_TOOL_PACKAGE=catalog_builder
    ```
2.  **Package Definitions:** The available packages and the tools they include are defined in `config/tool_packages.yaml`. You can customize this file to create your own packages.

### Behavior

-   If `MCP_TOOL_PACKAGE` is set to a valid package name defined in `config/tool_packages.yaml`, only the tools listed in that package will be loaded.
-   If `MCP_TOOL_PACKAGE` is **not set** or is empty, the `full` package (containing all tools) is loaded by default.
-   If `MCP_TOOL_PACKAGE` is set to an invalid package name, the `none` package is loaded (no tools except `list_tool_packages`), and a warning is logged.
-   Setting `MCP_TOOL_PACKAGE=none` explicitly loads no tools (except `list_tool_packages`).

### Available Packages (Default)

The default `config/tool_packages.yaml` includes the following role-based packages:

-   `service_desk`: Tools for incident handling and basic user/knowledge lookup.
-   `catalog_builder`: Tools for creating and managing service catalog items, categories, variables, and related scripting (UI Policies, User Criteria).
-   `change_coordinator`: Tools for managing the change request lifecycle, including tasks and approvals.
-   `knowledge_author`: Tools for creating and managing knowledge bases, categories, and articles.
-   `platform_developer`: Tools for server-side scripting (Script Includes), workflow development, and deployment (Changesets).
-   `system_administrator`: Tools for user/group management and viewing system logs.
-   `agile_management`: Tools for managing user stories, epics, scrum tasks, and projects.
-   `full`: Includes all available tools (default).
-   `none`: Includes no tools (except `list_tool_packages`).

### Introspection Tool

-   **`list_tool_packages`**: Lists all available tool package names defined in the configuration and shows the currently loaded package. This tool is available in all packages except `none`.

## Available Tools

**Note:** The availability of the following tools depends on the loaded tool package (see Tool Packaging section above). By default (`full` package), all tools are available.

#### Incident Management Tools

1. **create_incident** - Create a new incident in ServiceNow
2. **update_incident** - Update an existing incident in ServiceNow
3. **add_comment** - Add a comment to an incident in ServiceNow
4. **resolve_incident** - Resolve an incident in ServiceNow
5. **list_incidents** - List incidents from ServiceNow

#### Service Catalog Tools

1. **list_catalog_items** - List service catalog items from ServiceNow
2. **get_catalog_item** - Get a specific service catalog item from ServiceNow
3. **list_catalog_categories** - List service catalog categories from ServiceNow
4. **create_catalog_category** - Create a new service catalog category in ServiceNow
5. **update_catalog_category** - Update an existing service catalog category in ServiceNow
6. **move_catalog_items** - Move catalog items between categories in ServiceNow
7. **create_catalog_item_variable** - Create a new variable (form field) for a catalog item
8. **list_catalog_item_variables** - List all variables for a catalog item
9. **update_catalog_item_variable** - Update an existing variable for a catalog item
10. **list_catalogs** - List service catalogs from ServiceNow

#### Catalog Optimization Tools

1. **get_optimization_recommendations** - Get recommendations for optimizing the service catalog
2. **update_catalog_item** - Update a service catalog item

#### Change Management Tools

1. **create_change_request** - Create a new change request in ServiceNow
2. **update_change_request** - Update an existing change request
3. **list_change_requests** - List change requests with filtering options
4. **get_change_request_details** - Get detailed information about a specific change request
5. **add_change_task** - Add a task to a change request
6. **submit_change_for_approval** - Submit a change request for approval
7. **approve_change** - Approve a change request
8. **reject_change** - Reject a change request

#### Agile Management Tools

##### Story Management
1. **create_story** - Create a new user story in ServiceNow
2. **update_story** - Update an existing user story in ServiceNow
3. **list_stories** - List user stories with filtering options
4. **create_story_dependency** - Create a dependency between two stories
5. **delete_story_dependency** - Delete a dependency between stories

##### Epic Management
1. **create_epic** - Create a new epic in ServiceNow
2. **update_epic** - Update an existing epic in ServiceNow
3. **list_epics** - List epics from ServiceNow with filtering options

##### Scrum Task Management
1. **create_scrum_task** - Create a new scrum task in ServiceNow
2. **update_scrum_task** - Update an existing scrum task in ServiceNow
3. **list_scrum_tasks** - List scrum tasks from ServiceNow with filtering options

##### Project Management
1. **create_project** - Create a new project in ServiceNow
2. **update_project** - Update an existing project in ServiceNow
3. **list_projects** - List projects from ServiceNow with filtering options

#### Workflow Management Tools

1. **list_workflows** - List workflows from ServiceNow
2. **get_workflow** - Get a specific workflow from ServiceNow
3. **create_workflow** - Create a new workflow in ServiceNow
4. **update_workflow** - Update an existing workflow in ServiceNow
5. **delete_workflow** - Delete a workflow from ServiceNow

#### Script Include Management Tools

1. **list_script_includes** - List script includes from ServiceNow
2. **get_script_include** - Get a specific script include from ServiceNow
3. **create_script_include** - Create a new script include in ServiceNow
4. **update_script_include** - Update an existing script include in ServiceNow
5. **delete_script_include** - Delete a script include from ServiceNow

#### Changeset Management Tools

1. **list_changesets** - List changesets from ServiceNow with filtering options
2. **get_changeset_details** - Get detailed information about a specific changeset
3. **create_changeset** - Create a new changeset in ServiceNow
4. **update_changeset** - Update an existing changeset
5. **commit_changeset** - Commit a changeset
6. **publish_changeset** - Publish a changeset
7. **add_file_to_changeset** - Add a file to a changeset

#### Knowledge Base Management Tools

1. **create_knowledge_base** - Create a new knowledge base in ServiceNow
2. **list_knowledge_bases** - List knowledge bases with filtering options
3. **create_category** - Create a new category in a knowledge base
4. **create_article** - Create a new knowledge article in ServiceNow
5. **update_article** - Update an existing knowledge article in ServiceNow
6. **publish_article** - Publish a knowledge article in ServiceNow
7. **list_articles** - List knowledge articles with filtering options
8. **get_article** - Get a specific knowledge article by ID

#### User Management Tools

1. **create_user** - Create a new user in ServiceNow
2. **update_user** - Update an existing user in ServiceNow
3. **get_user** - Get a specific user by ID, username, or email
4. **list_users** - List users with filtering options
5. **create_group** - Create a new group in ServiceNow
6. **update_group** - Update an existing group in ServiceNow
7. **add_group_members** - Add members to a group in ServiceNow
8. **remove_group_members** - Remove members from a group in ServiceNow
9. **list_groups** - List groups with filtering options

#### UI Policy Tools

1. **create_ui_policy** - Creates a ServiceNow UI Policy, typically for a Catalog Item.
2. **create_ui_policy_action** - Creates an action associated with a UI Policy to control variable states (visibility, mandatory, etc.).

### Using the MCP CLI

The ServiceNow MCP server can be installed with the MCP CLI, which provides a convenient way to register the server with Claude.

```bash
# Install the ServiceNow MCP server with environment variables from .env file
mcp install src/servicenow_mcp/server.py -f .env
```

This command will register the ServiceNow MCP server with Claude and configure it to use the environment variables from the .env file.

### Integration with Claude Desktop

To configure the ServiceNow MCP server in Claude Desktop:

1. Edit the Claude Desktop configuration file:
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ServiceNow": {
      "command": "/Users/yourusername/dev/servicenow-mcp/.venv/bin/python",
      "args": [
        "-m",
        "servicenow_mcp.cli"
      ],
      "env": {
        "SERVICENOW_INSTANCE_URL": "https://your-instance.service-now.com",
        "SERVICENOW_USERNAME": "your-username",
        "SERVICENOW_PASSWORD": "your-password",
        "SERVICENOW_AUTH_TYPE": "basic"
      }
    }
  }
}
```

2. Restart Claude Desktop to apply the changes.

**Why the absolute path to the venv's `python`?** Claude Desktop launches the MCP server outside any virtualenv you have activated in your shell. Pointing `command` at `python` (or `python3`) directly will run a different interpreter than the one where you `pip install`-ed this package, and the MCP server will fail to import its dependencies. This is the most common installation issue (see [echelon Issue #49](https://github.com/echelon-ai-labs/servicenow-mcp/issues/49)) — using the absolute path to `.venv/bin/python` (or the equivalent for your platform) bypasses it. After Phase 3 ships uvx-compatible packaging (PR #46), you'll be able to skip the venv entirely and use `"command": "uvx", "args": ["servicenow-mcp"]` instead.

### Example Usage with Claude

Below are some example natural language queries you can use with Claude to interact with ServiceNow via the MCP server:

#### Incident Management Examples
- "Create a new incident for a network outage in the east region"
- "Update the priority of incident INC0010001 to high"
- "Add a comment to incident INC0010001 saying the issue is being investigated"
- "Resolve incident INC0010001 with a note that the server was restarted"
- "List all high priority incidents assigned to the Network team"
- "List all active P1 incidents assigned to the Network team."

#### Service Catalog Examples
- "Show me all items in the service catalog"
- "List all service catalog categories"
- "Get details about the laptop request catalog item"
- "Show me all catalog items in the Hardware category"
- "Search for 'software' in the service catalog"
- "Create a new category called 'Cloud Services' in the service catalog"
- "Update the 'Hardware' category to rename it to 'IT Equipment'"
- "Move the 'Virtual Machine' catalog item to the 'Cloud Services' category"
- "Create a subcategory called 'Monitors' under the 'IT Equipment' category"
- "Reorganize our catalog by moving all software items to the 'Software' category"
- "Create a description field for the laptop request catalog item"
- "Add a dropdown field for selecting laptop models to catalog item"
- "List all form fields for the VPN access request catalog item"
- "Make the department field mandatory in the software request form"
- "Update the help text for the cost center field"
- "Show me all service catalogs in the system"
- "List all hardware catalog items."
- "Find the catalog item for 'New Laptop Request'."
- "Show me the variables for the 'New Laptop Request' item."
- "Create a new variable named 'department_code' for the 'New Hire Setup' catalog item. Make it a mandatory string field."

#### Catalog Optimization Examples
- "Analyze our service catalog and identify opportunities for improvement"
- "Find catalog items with poor descriptions that need improvement"
- "Identify catalog items with low usage that we might want to retire"
- "Find catalog items with high abandonment rates"
- "Optimize our Hardware category to improve user experience"

#### Change Management Examples
- "Create a change request for server maintenance to apply security patches tomorrow night"
- "Schedule a database upgrade for next Tuesday from 2 AM to 4 AM"
- "Add a task to the server maintenance change for pre-implementation checks"
- "Submit the server maintenance change for approval"
- "Approve the database upgrade change with comment: implementation plan looks thorough"
- "Show me all emergency changes scheduled for this week"
- "List all changes assigned to the Network team"
- "Create a normal change request to upgrade the production database server."
- "Update change CHG0012345, set the state to 'Implement'."

#### Agile Management Examples
- "Create a new user story for implementing a new reporting dashboard"
- "Update the 'Implement a new reporting dashboard' story to set it as blocked"
- "List all user stories assigned to the Data Analytics team"
- "Create a dependency between the 'Implement a new reporting dashboard' story and the 'Develop data extraction pipeline' story"
- "Delete the dependency between the 'Implement a new reporting dashboard' story and the 'Develop data extraction pipeline' story"
- "Create a new epic called 'Data Analytics Initiatives'"
- "Update the 'Data Analytics Initiatives' epic to set it as completed"
- "List all epics in the 'Data Analytics' project"
- "Create a new scrum task for the 'Implement a new reporting dashboard' story"
- "Update the 'Develop data extraction pipeline' scrum task to set it as completed"
- "List all scrum tasks in the 'Implement a new reporting dashboard' story"
- "Create a new project called 'Data Analytics Initiatives'"
- "Update the 'Data Analytics Initiatives' project to set it as completed"
- "List all projects in the 'Data Analytics' epic"

#### Workflow Management Examples
- "Show me all active workflows in ServiceNow"
- "Get details about the incident approval workflow"
- "List all versions of the change request workflow"
- "Show me all activities in the service catalog request workflow"
- "Create a new workflow for handling software license requests"
- "Update the description of the incident escalation workflow"
- "Activate the new employee onboarding workflow"
- "Deactivate the old password reset workflow"
- "Add an approval activity to the software license request workflow"
- "Update the notification activity in the incident escalation workflow"
- "Delete the unnecessary activity from the change request workflow"
- "Reorder the activities in the service catalog request workflow"

#### Changeset Management Examples
- "List all changesets in ServiceNow"
- "Show me all changesets created by developer 'john.doe'"
- "Get details about changeset 'sys_update_set_123'"
- "Create a new changeset for the 'HR Portal' application"
- "Update the description of changeset 'sys_update_set_123'"
- "Commit changeset 'sys_update_set_123' with message 'Fixed login issue'"
- "Publish changeset 'sys_update_set_123' to production"
- "Add a file to changeset 'sys_update_set_123'"
- "Show me all changes in changeset 'sys_update_set_123'"

#### Knowledge Base Examples
- "Create a new knowledge base for the IT department"
- "List all knowledge bases in the organization"
- "Create a category called 'Network Troubleshooting' in the IT knowledge base"
- "Write an article about VPN setup in the Network Troubleshooting category"
- "Update the VPN setup article to include mobile device instructions"
- "Publish the VPN setup article so it's visible to all users"
- "List all articles in the Network Troubleshooting category"
- "Show me the details of the VPN setup article"
- "Find knowledge articles containing 'password reset' in the IT knowledge base"
- "Create a subcategory called 'Wireless Networks' under the Network Troubleshooting category"

#### User Management Examples
- "Create a new user Dr. Alice Radiology in the Radiology department"
- "Update Bob's user record to make him the manager of Alice"
- "Assign the ITIL role to Bob so he can approve change requests"
- "List all users in the Radiology department"
- "Create a new group called 'Biomedical Engineering' for managing medical devices"
- "Add an admin user to the Biomedical Engineering group as a member"
- "Update the Biomedical Engineering group to change its manager"
- "Remove a user from the Biomedical Engineering group"
- "Find all active users in the system with 'doctor' in their title"
- "Create a user that will act as an approver for the Radiology department"
- "List all IT support groups in the system"

#### UI Policy Examples
- "Create a UI policy for the 'Software Request' item (sys_id: abc...) named 'Show Justification' that applies when 'software_cost' is greater than 100."
- "For the UI policy 'Show Justification' (sys_id: def...), add an action to make the 'business_justification' variable visible and mandatory."
- "Create another action for policy 'Show Justification' to hide the 'alternative_software' variable."

### Example Scripts

The repository includes example scripts that demonstrate how to use the tools:

- **examples/catalog_optimization_example.py**: Demonstrates how to analyze and improve the ServiceNow Service Catalog
- **examples/change_management_demo.py**: Shows how to create and manage change requests in ServiceNow

## Concurrency and async architecture

This server is designed for **concurrent multi-agent workloads** — many MCP clients (Claude Desktop, agent SDKs, browser extensions, custom tooling) connecting to one server process and issuing tool calls in parallel. As of Phase 9 (v0.9.x) the entire HTTP path is non-blocking async, with explicit isolation between concurrent sessions and explicit serialisation where shared state is involved.

### What's async, end-to-end

- **HTTP client.** All ~211 tool functions and the OAuth refresh path call `httpx.AsyncClient` directly. The legacy sync `requests` library has been removed from the runtime hot path entirely (it remains in dev/admin scripts under `scripts/` only — those aren't in the runtime server).
- **MCP transport.** The Streamable HTTP transport is built on Starlette + Uvicorn (Phase 7) which is async-native. The stdio transport uses FastMCP's `run_stdio_async()`.
- **Tool registration.** The Phase 8 FastMCP migration eliminated the manual `_list_tools_impl` / `_call_tool_impl` dispatch handlers; FastMCP's adapter dispatches sync vs async tool implementations transparently. The Phase 9.1 fastmcp adapter detects coroutine functions via `inspect.iscoroutinefunction` and produces the right wrapper shape.

### Why this matters for multi-agent traffic

- **No event-loop blocking.** Before Phase 9, a slow ServiceNow API call inside an SSE/HTTP request was a sync `requests.get(...)` call. Even though the surrounding server was async, the sync HTTP call blocked the event loop. With three slow concurrent calls, the third agent saw queueing-time degradation. Phase 9 fixes this — slow calls suspend, the event loop services other agents, and the third agent's call starts immediately.
- **Connection pooling.** A single shared `httpx.AsyncClient` (`utils/async_http.py`) is used process-wide, with `max_keepalive_connections=20` and `max_connections=100`. Many concurrent agent calls share the connection pool to ServiceNow, with HTTP/1.1 keepalive and HTTP/2 multiplexing. Earlier versions opened a fresh socket per call.
- **Serialised OAuth refresh.** The OAuth client_credentials / password flows refresh tokens automatically before expiry. Under concurrent load with N agents on an expired token, an `asyncio.Lock` (`_oauth_lock`) serialises the refresh: the first coroutine acquires the lock and POSTs to `oauth_token.do`; the others wait, then re-check expiry inside the lock and skip the redundant POST. Net result: exactly **one** token POST per expiry window, regardless of concurrent agent count.

### Concurrency safety guarantees

| Concern | How it's handled |
|---|---|
| Per-call params isolation | Tool functions take `(config, auth_manager, params)`. `params` is a per-call Pydantic model — no shared mutable state between concurrent calls. |
| Per-session MCP isolation | The MCP `Mcp-Session-Id` header (added by FastMCP / spec) routes requests to the correct session context. Each session has its own MCP `ClientSession` and `EventStore` entries. |
| OAuth token races | `asyncio.Lock` per-AuthManager. See above. |
| Connection pool exhaustion | Default `max_connections=100` is generous for typical agent workloads. Cloud Run / Lambda memory budgets fit this comfortably. Tunable via `httpx.Limits` if you need more. |
| Process shutdown | `aclose_async_client()` is wired into the FastMCP lifespan in `server_http.py`. When uvicorn stops, the inner FastMCP lifespan tears down the StreamableHTTPSessionManager, then our outer lifespan flushes pooled connections. |

### Multi-agent security model

Phase 9 doesn't change the security model — but it's worth restating what isolates concurrent agents from each other:

1. **One bearer token gates the entire HTTP transport.** All MCP clients present the same `MCP_AUTH_TOKEN`. There is no per-agent identity at the MCP layer; if you need that, the next step is full MCP OAuth 2.1 (Phase 10+).
2. **All clients share the same ServiceNow credentials.** The server holds one `AuthManager` per process; that AuthManager's south-bound credentials (Basic / OAuth / API Key) are the same for every agent. ServiceNow sees one user identity regardless of which AI agent issued the call. RFC 8693 token exchange (OBO) for end-user attribution is on the Phase 10+ roadmap.
3. **Tool-call results are not shared between agents.** Each `call_tool` request flows through its own `(config, auth_manager, params)` invocation. There is no per-agent cache, no shared response store, no cross-request state.
4. **Body redaction in debug logs is global.** The `_truncate_body` redactor (helpers.py) replaces values for keys matching `_SENSITIVE_BODY_KEYS` (password, secret, token, etc.) before serialisation. Concurrent agents passing OAuth password-grant bodies, API keys, or session tokens through the debug log path are all protected by the same redaction.
5. **Host / Origin allowlists apply per-request.** Each incoming HTTP request is independently checked by `SecurityMiddleware`. There is no session-level whitelisting that could carry from a trusted Origin to an untrusted one.

### What "many concurrent agents" actually means in practice

A single Cloud Run / App Runner / AgentCore Runtime instance with 1 vCPU and 512MiB RAM can comfortably handle:

- **Tens of MCP sessions concurrently** (the StreamableHTTPSessionManager is async; each session is a coroutine, not a thread).
- **Each session running multiple tool calls in parallel** (httpx connection pool services them).
- **Aggregate ServiceNow API throughput up to ~100 concurrent in-flight requests** (the client's `max_connections` ceiling). Beyond this, ServiceNow's rate-limit headers (`X-RateLimit-*`) start kicking in and our `RateLimitTracker` throttles client-side; you'd want to scale horizontally rather than vertically.

If you exceed any of these limits, the right move is autoscaling — Cloud Run / App Runner / AgentCore Runtime handle this automatically. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for cloud deployment guides.

### Async migration history (for the record)

| Phase | What landed | Tag |
|---|---|---|
| 9.1 | Async infrastructure (`utils/async_http.py`, async helpers, async auth_manager) | v0.9.1 |
| 9.2 | First small batch — user_criteria, bulk, scripted_rest | v0.9.2 |
| 9.3 | syslog, ui_policy | v0.9.3 |
| 9.4 | nl, case, epic, project, scrum_task | v0.9.4 |
| 9.5 | time_card, sctask, sys_dictionary, business_rule, table_api, scheduled_job | v0.9.5 |
| 9.6 | catalog_variables, widget, catalog_optimization, import_set, csm, story, script_include | v0.9.6 |
| 9.7 | changeset, catalog, rest_message, oauth, knowledge_base, incident | v0.9.7 |
| 9.8 | acl, user, workflow, change | v0.9.8 |
| 9.9 | flow_tools (4730 lines, 57 HTTP calls) | v0.9.9 |
| 9.10 | OAuth concurrency lock, FastMCP lifespan integration, this documentation | v0.9.10 |
| 9.11 | Wired 12 unregistered flow tools (`delete_flow`, `execute_flow`, `get_flow_execution_history`/`_detail`, `delete_subflow`, `delete_action`, `add_steps_to_flow`, `add_subflow_step_to_flow`, `remove_steps_from_flow`, `add_logic_to_flow`, `list_flow_logic_types`, `list_flow_io`); fixed an inert pre-existing FastMCP-adapter bug (`default` + `default_factory` collision) that had silently dropped `create_flow`; tool count 198 → 211 | v0.9.11 |

35 of 35 tool files converted; 257 HTTP call sites moved from `requests` to `httpx.AsyncClient`. 964 tests passing, mypy clean (build-blocking gate), ruff clean.

## Authentication Methods

### Basic Authentication

```
SERVICENOW_AUTH_TYPE=basic
SERVICENOW_USERNAME=your-username
SERVICENOW_PASSWORD=your-password
```

### OAuth Authentication

The recommended OAuth flow is **client_credentials**. Username and password are no longer required — the server only needs `SERVICENOW_CLIENT_ID` and `SERVICENOW_CLIENT_SECRET`. Username/password are now used only as a fallback to the legacy password grant when both are set, and the password grant is deprecated by the [OAuth Best Current Practice](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics) (Issue [#43](https://github.com/echelon-ai-labs/servicenow-mcp/issues/43) finding #2).

```
SERVICENOW_AUTH_TYPE=oauth
SERVICENOW_CLIENT_ID=your-client-id
SERVICENOW_CLIENT_SECRET=your-client-secret
SERVICENOW_TOKEN_URL=https://your-instance.service-now.com/oauth_token.do  # optional; auto-derived from instance URL
SERVICENOW_RESOURCE_URL=...  # optional, for Azure AD-backed flows that require a `resource` parameter
```

### API Key Authentication

```
SERVICENOW_AUTH_TYPE=api_key
SERVICENOW_API_KEY=your-api-key
```

### Optional environment variables

These apply across all authentication methods.

```
SERVICENOW_API_PATH=api          # default; override for instances behind a gateway with a non-standard mount
SERVICENOW_EXTRA_HTTP_HEADERS={"X-Tenant-Id": "acme"}    # JSON dict; merged into every request
```

## Development

### Documentation

Additional documentation is available in the `docs` directory:

- [Catalog Integration](docs/catalog.md) - Detailed information about the Service Catalog integration
- [Catalog Optimization](docs/catalog_optimization_plan.md) - Detailed plan for catalog optimization features
- [Change Management](docs/change_management.md) - Detailed information about the Change Management tools
- [Workflow Management](docs/workflow_management.md) - Detailed information about the Workflow Management tools
- [Changeset Management](docs/changeset_management.md) - Detailed information about the Changeset Management tools

### Troubleshooting

#### Common Errors with Change Management Tools

1. **Error: `argument after ** must be a mapping, not CreateChangeRequestParams`**
   - This error occurs when you pass a `CreateChangeRequestParams` object instead of a dictionary to the `create_change_request` function.
   - Solution: Make sure you're passing a dictionary with the parameters, not a Pydantic model object.
   - Note: The change management tools have been updated to handle this error automatically. The functions will now attempt to unwrap parameters if they're incorrectly wrapped or passed as a Pydantic model object.

2. **Error: `Missing required parameter 'type'`**
   - This error occurs when you don't provide all required parameters for creating a change request.
   - Solution: Make sure to include all required parameters. For `create_change_request`, both `short_description` and `type` are required.

3. **Error: `Invalid value for parameter 'type'`**
   - This error occurs when you provide an invalid value for the `type` parameter.
   - Solution: Use one of the valid values: "normal", "standard", or "emergency".

4. **Error: `Cannot find get_headers method in either auth_manager or server_config`**
   - This error occurs when the parameters are passed in the wrong order or when using objects that don't have the required methods.
   - Solution: Make sure you're passing the `auth_manager` and `server_config` parameters in the correct order. The functions have been updated to handle parameter swapping automatically.

### Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### License

This project is licensed under the MIT License - see the LICENSE file for details.

# ServiceNow MCP Server

A Model Context Protocol (MCP) server for ServiceNow. Lets Claude (and any MCP-compatible client) read ServiceNow data and execute actions through the ServiceNow Table and REST APIs.

## Fork notice

This is a maintained fork of [`echelon-ai-labs/servicenow-mcp`](https://github.com/echelon-ai-labs/servicenow-mcp), integrating the upstream `fix/sse-auth-hardening` branch and patterns from related forks. Upstream has been effectively dormant since October 2025 — this fork serves as the de-facto reviewed-and-tested version.

The architectural rationale, fork survey, and PR/issue analysis live in:
- [`ANALYSIS_OF_EXISTING_OPEN_SOURCE_SERVICENOW_MCP_SERVERS.md`](ANALYSIS_OF_EXISTING_OPEN_SOURCE_SERVICENOW_MCP_SERVERS.md)
- [`ANALYSIS_OF_ECHELON_AI_LABS_SERVICENOW_MCP_FORKS.md`](ANALYSIS_OF_ECHELON_AI_LABS_SERVICENOW_MCP_FORKS.md)
- [`ANALYSIS_OF_ECHELON_AI_LABS_PRS_AND_ISSUES.md`](ANALYSIS_OF_ECHELON_AI_LABS_PRS_AND_ISSUES.md)

License is MIT (matching all upstream sources). See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for per-component attribution.

## Security notice

Before deploying this server, read these:

1. **Default packages do NOT expose `execute_script_include` and the script-management write/delete tools.** Together, those tools form an arbitrary-code-execution sink on the connected ServiceNow instance — an LLM with access to them can write and run Glide scripts in your tenant. They remain registered in code; opt in only behind a human-in-the-loop approval flow. (Issue [#43 finding #1](https://github.com/echelon-ai-labs/servicenow-mcp/issues/43), addressed in this fork.)

2. **OAuth password grant is supported but discouraged.** It requires the server to handle plaintext ServiceNow user credentials — the OAuth Best Current Practice deprecates it. Prefer the `client_credentials` grant. The server still supports password grant for environments that have it as a hard requirement.

3. **Never put your ServiceNow password in `claude_desktop_config.json` directly.** Configure credentials via environment variables loaded at runtime instead. Plaintext passwords in user-readable JSON files are a real exfiltration risk if your machine is shared, your shell history is logged, or your dotfiles are synced.

4. **HTTP transport binds to loopback by default** (since the `fix/sse-auth-hardening` merge). To expose the server to a non-loopback interface, pass `--allow-remote` AND set `MCP_AUTH_TOKEN` — without both, the server refuses to bind. Bearer-token, Host-allowlist, and Origin-allowlist defenses are all on by default.

5. **Phase 7 will deprecate SSE in favor of Streamable HTTP.** The MCP spec has moved on. SSE will remain available for one release cycle after Streamable HTTP lands.

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

### Server-Sent Events (SSE) Mode

The ServiceNow MCP server can also run as a web server using Server-Sent Events (SSE) for communication.

> **Security:** the SSE transport authenticates every request with a bearer token and rejects requests whose `Host` or `Origin` headers are not in an allowlist. By default it binds to `127.0.0.1` only; non-loopback bind requires `--allow-remote` and an explicit `MCP_AUTH_TOKEN`. See [Vulnerability disclosure (EntruLabs, 2026-04-22)](#) for the original report this hardening addresses.

#### Starting the SSE Server (loopback, local dev)

```
servicenow-mcp-sse
```

The server binds `127.0.0.1:8080`, generates a random bearer token, and prints it once to stderr:

```
[servicenow-mcp-sse] generated auth token: <random-token>
```

Use that token on every request:

```
curl -N -H "Authorization: Bearer <random-token>" http://127.0.0.1:8080/sse
```

To pin a stable token, set `MCP_AUTH_TOKEN` in `.env` (then no token is auto-generated).

#### Exposing the SSE Server beyond loopback

Non-loopback bind is opt-in and requires both `--allow-remote` and an explicit `MCP_AUTH_TOKEN`:

```
MCP_AUTH_TOKEN=$(openssl rand -hex 32) \
servicenow-mcp-sse --host=0.0.0.0 --port=8080 --allow-remote \
  --allowed-host=mcp.internal --allowed-host=mcp.internal:8080
```

You can pass `--allowed-host` repeatedly, or use the env var:

```
MCP_ALLOWED_HOSTS=mcp.internal,mcp.internal:8080
```

Loopback hosts (`127.0.0.1`, `localhost`, `[::1]`) are always allowed.

#### Endpoints

- `/sse` — SSE connection endpoint (bearer-token required)
- `/messages/` — JSON-RPC POST endpoint (bearer-token required)

#### Programmatic example

```python
from servicenow_mcp.server_sse import create_servicenow_mcp

mcp = create_servicenow_mcp(
    instance_url="https://your-instance.service-now.com",
    username="your-username",
    password="your-password",
)
mcp.start()  # 127.0.0.1:8080, auto-generated bearer token logged to stderr
```

To bind beyond loopback from code, set `MCP_AUTH_TOKEN` and pass `allow_remote=True`:

```python
mcp.start(host="0.0.0.0", port=8080, allow_remote=True)
```

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

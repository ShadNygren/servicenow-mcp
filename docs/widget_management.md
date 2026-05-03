# Service Portal Widget Management in ServiceNow MCP

This document provides detailed information about the Service Portal Widget Management tools available in the ServiceNow MCP server.

## Overview

Service Portal Widgets are reusable components in ServiceNow's Service Portal framework. They combine HTML templates, CSS styles, client-side AngularJS scripts, and server-side scripts to create interactive UI components.

The ServiceNow MCP server provides tools for managing widgets, allowing Claude to help with:

- Creating new Service Portal widgets
- Updating existing widget configurations and code
- Searching and retrieving widget details
- Managing widget properties like templates, scripts, and options

## Available Tools

### 1. get_widget

Gets Service Portal widget(s) by sys_id or searches by name.

**Parameters:**
- `sys_id` (optional) - Widget sys_id for exact match
- `name` (optional) - Widget name for 'contains' search
- `limit` (optional, default: 10) - Maximum number of widgets to return
- `offset` (optional, default: 0) - Offset for pagination

**Note:** Either `sys_id` or `name` must be provided.

**Example - Get by sys_id:**
```python
result = get_widget({
    "sys_id": "abc123def456789012345678901234ab"
})
```

**Example - Search by name:**
```python
result = get_widget({
    "name": "User Profile",
    "limit": 20,
    "offset": 0
})
```

### 2. create_widget

Creates a new Service Portal widget in ServiceNow.

**Parameters:**
- `name` (required) - Display name of the widget
- `id` (required) - Widget ID (unique user-defined identifier)
- `description` (required) - Description of the widget
- `template` (optional) - HTML template for the widget
- `css` (optional) - CSS styles for the widget
- `client_script` (optional) - Client-side AngularJS controller script
- `server_script` (optional) - Server-side script executed on widget load
- `script` (optional) - Alternative name for server script
- `option_schema` (optional) - JSON schema for widget options/instance options
- `controller_as` (optional) - AngularJS controller alias (default: 'c')
- `demo_data` (optional) - Demo/sample data for widget preview
- `has_preview` (optional) - Whether the widget has a preview available
- `data_table` (optional) - Associated data table for the widget
- `public` (optional) - Whether the widget is publicly accessible
- `roles` (optional) - Comma-separated list of roles that can access the widget

**Example:**
```python
result = create_widget({
    "name": "User Profile Card",
    "id": "user-profile-card",
    "description": "Displays user profile information in a card format",
    "template": "<div class='profile-card'><h2>{{c.data.user.name}}</h2></div>",
    "css": ".profile-card { padding: 20px; border-radius: 8px; }",
    "client_script": "function($scope) { var c = this; }",
    "server_script": "(function() { data.user = gs.getUser(); })();",
    "public": false
})
```

### 3. update_widget

Updates an existing Service Portal widget in ServiceNow.

**Parameters:**
- `widget_id` (required) - Widget sys_id or widget ID (user-defined id field)
- `name` (optional) - Display name of the widget
- `description` (optional) - Description of the widget
- `template` (optional) - HTML template for the widget
- `css` (optional) - CSS styles for the widget
- `client_script` (optional) - Client-side AngularJS controller script
- `server_script` (optional) - Server-side script executed on widget load
- `script` (optional) - Alternative name for server script
- `option_schema` (optional) - JSON schema for widget options
- `controller_as` (optional) - AngularJS controller alias
- `demo_data` (optional) - Demo/sample data for widget preview
- `has_preview` (optional) - Whether the widget has a preview available
- `data_table` (optional) - Associated data table for the widget
- `public` (optional) - Whether the widget is publicly accessible
- `roles` (optional) - Comma-separated list of roles that can access the widget

**Example - Update by widget ID:**
```python
result = update_widget({
    "widget_id": "user-profile-card",
    "template": "<div class='profile-card updated'><h2>{{c.data.user.name}}</h2><p>{{c.data.user.email}}</p></div>",
    "css": ".profile-card.updated { padding: 24px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }"
})
```

**Example - Update by sys_id:**
```python
result = update_widget({
    "widget_id": "abc123def456789012345678901234ab",
    "description": "Updated description for the widget",
    "public": true
})
```

## Widget Fields Reference

| Field | Type | Description |
|-------|------|-------------|
| sys_id | string | System-generated unique identifier |
| id | string | User-defined widget identifier |
| name | string | Display name of the widget |
| description | string | Description of the widget purpose |
| template | string | HTML template (AngularJS syntax supported) |
| css | string | SCSS/CSS styles scoped to the widget |
| client_script | string | Client-side AngularJS controller |
| server_script | string | Server-side GlideRecord script |
| script | string | Alternative server script field |
| option_schema | string | JSON schema for widget instance options |
| controller_as | string | AngularJS controller alias (default: 'c') |
| demo_data | string | Sample data for widget designer preview |
| has_preview | boolean | Whether preview is available in designer |
| data_table | string | Associated ServiceNow table |
| public | boolean | Public accessibility flag |
| roles | string | Comma-separated role requirements |

## Best Practices

1. **Widget ID Naming**: Use lowercase, hyphenated names for widget IDs (e.g., `user-profile-card`). This makes them easier to reference and follows web standards.

2. **Modular Templates**: Keep HTML templates focused on structure. Use CSS for styling and client scripts for behavior.

3. **Server Script Security**: Always validate user input in server scripts. Use GlideRecord queries with proper ACL checks.

4. **Option Schema**: Define option schemas for configurable widgets to allow portal administrators to customize behavior without code changes.

5. **Controller Alias**: Use the default `c` controller alias for consistency across widgets unless there's a specific need to change it.

6. **Role-Based Access**: Use the `roles` field to restrict widget access to appropriate users.

7. **Testing**: Test widgets in the Widget Designer before deploying to production portals.

## Example Workflow

1. Search for existing widgets to avoid duplication
2. Create a new widget with basic structure
3. Iterate on the template, CSS, and scripts
4. Add option schema for configurability
5. Test in Widget Designer with demo data
6. Update widget properties as needed
7. Deploy to portal pages

## Troubleshooting

### Common Issues

1. **Widget Not Found**: Verify the widget ID or sys_id is correct. Use the `get_widget` tool with a name search to find widgets.

2. **Script Errors**: Check the browser console for client-side errors and the ServiceNow system logs for server-side errors.

3. **CSS Not Applied**: Ensure CSS selectors are specific enough. Widget CSS is scoped but may conflict with portal-level styles.

4. **Data Not Loading**: Verify server script is setting `data` object properties correctly and that the user has access to the queried records.

### Error Messages

- **"Either sys_id or name must be provided"**: The `get_widget` tool requires at least one search parameter.
- **"Widget not found"**: The specified widget ID does not exist or the user lacks access.
- **"Error creating widget"**: Check that required fields (name, id, description) are provided and that the widget ID is unique.
- **"Error updating widget"**: Verify the widget exists and the user has permissions to modify it.

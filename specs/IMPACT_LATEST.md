## Target
Remote MCP server authentication headers across `core/database.py`, `routes/mcp/mcp_routes.py`, `src/mcp_manager.py`, and `static/js/settings.js`.

## Dependents (6)
- `src/mcp_manager.py`: all MCP connection paths, enabled-server startup, reconnection, and tool refresh.
- `routes/mcp/mcp_routes.py`: add, reconnect, toggle, OAuth completion, and tool-refresh endpoints.
- `src/agent_tools/admin_tools.py`: agent-managed MCP server reconnects.
- `src/builtin_mcp.py`: built-in stdio MCP connections share the `connect_server` interface.
- `static/js/settings.js`: user settings MCP creation UI.
- `static/js/admin.js`: administrator MCP creation UI.

## Affected Stories
- No `specs/release-plan.yaml` or epic capsules exist in this repository.
- Existing documentation: `specs/shell-mcp.md` and `specs/settings-admin.md` cover this area.

## Test Coverage
- `tests/test_mcp_manager.py`: transport dispatch and connection-error formatting.
- `tests/test_mcp_add_server_args_validation.py`: route validation for MCP configuration.
- `tests/test_mcp_reconnect_args.py`: persisted server configuration on reconnect.
- Gap: no coverage for authenticated SSE/Streamable HTTP custom headers or encrypted MCP configuration storage.

## Risk: High
This changes a shared connection interface used by every configured and built-in MCP server, persists secrets, and changes both MCP transports.

## Recommended action
Add encrypted header persistence with a backward-compatible default, thread headers through every persisted reconnection path, and add focused manager and route regression tests before deployment.

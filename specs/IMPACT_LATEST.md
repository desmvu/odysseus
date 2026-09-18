## Target
`src/mcp_manager.py:McpManager.get_tools_for_explicit_server_reference()` and the prompt-selection flow in `src/agent_loop.py`; cosmetic output guidance for MCP file-size metadata.

## Dependents (3)
- `src/agent_loop.py:4079`: explicit user references to an external MCP server narrow the available schemas to selected remote tools.
- `src/agent_loop.py:4140`: a matched skill declaring a remote MCP server as `requires_toolsets` resolves that server through the same selector.
- `tests/test_mcp_tool_params_in_prompt.py`: behavioral regression coverage for named-server selection, Seerr request workflows, Nextcloud WebDAV workflows, Soulseek workflows, disabled tools, and the schema cap.

## Affected Stories
- No active release-plan story owns this code (`specs/release-plan.yaml` is absent/empty); existing MCP reliability work is tracked in `specs/bugs/BUG-2026-09-18T032742-seerr-missing-request-tool.md`, `specs/bugs/BUG-2026-09-18T094500-nextcloud-bogus-task-creation.md`, `specs/bugs/BUG-2026-09-18T095530-mcp-retry-loop.md`, and `specs/bugs/BUG-2026-09-18T105700-nextcloud-stale-list-intent-blocks-read.md`.

## Test Coverage
- `tests/test_mcp_tool_params_in_prompt.py`: covers the selector’s existing explicit-name, workflow, disabled-tool, and bound-size behavior.
- `tests/test_agent_loop.py`: covers retry continuation/tool retention; it does not comprehensively exercise dynamic-MCP selection paths.
- Gap: no contract/inventory test verifies the connected Nextcloud 162-tool catalog can be selected by ordinary operation-family requests without being hidden by a special-case workflow shortcut.
- Gap: no deterministic test guards the user-visible representation of raw MCP file-size values.

## Risk: High
This shared selector chooses the only callable schemas shown to the model for every dynamically connected MCP server; incorrect narrowing silently causes false capability denial or exposes irrelevant mutation tools to smaller models.

## Recommended action
Add a catalog-driven, deterministic selection policy with narrow tests for each operation family found on the live Nextcloud, Soulseek, and Seerr schemas. Preserve explicit tool-name selection, disabled-tool handling, and the three-tool cap semantics. Treat raw byte values as already-correct tool data and add presentation guidance rather than mutating tool results.

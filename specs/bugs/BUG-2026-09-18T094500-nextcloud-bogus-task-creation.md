---
bug_id: BUG-2026-09-18T094500
status: resolved
severity: high
scope: agent-tool-selection
title: Skill naming a remote MCP server contributed no callable tool schema, so the model invented a scheduled task instead
---

# BUG-2026-09-18T094500: Skill naming a remote MCP server contributed no callable tool schema, so the model invented a scheduled task instead

## Problem

**Actual behavior:** Asked "list files inside Work. there should be notes in there" (a follow-up to a successful Nextcloud root-listing), Qwen3-14B tried to call `nc_webdav_list_directory` as if it were an AI *model* name (via the `pipeline` tool), got "Model 'nc_webdav_list_directory' not found on any configured endpoint", then created a fictitious scheduled task ("Deploy MCP Server for Nextcloud Access", id `5f1bb3e2-abe1-4f60-9400-48f2c98783c4`), ran it, performed an unrelated web search, and told the user to wait until the next day for a "deployment" that was never needed — the Nextcloud MCP server (162 tools) was already connected and working the entire time.

**Expected behavior:** A follow-up naming a Nextcloud folder/file operation should receive the real `nc_webdav_list_directory` MCP tool schema directly, and never route an MCP tool name through the model-routing (`pipeline`) or task-scheduling tools.

**How to reproduce:** With the `operate-nextcloud-mcp-effectively` skill matching a turn via retrieval, but the toolset name (`nextcloud`) not present in the static known-tools set, observe the skill's procedural text reach the prompt while the actual MCP tool schema does not.

**Security impact:** NONE — no exploit path; a reliability/task-hygiene bug (created a real but useless scheduled task) rather than a data-exposure issue.

## Root Cause Analysis

- `src/agent_loop.py`'s skill-aware tool inclusion (the block iterating a matched skill's `requires_toolsets`) added a toolset to `_relevant_tools` only when it matched `known_tool_names()` — the set of static Odysseus tools. A remote MCP server name declared in a skill's `requires_toolsets` (e.g. `nextcloud`) is never a static tool name, so the check silently contributed **zero** real tool schemas for that skill, even though the skill's own procedural text (injected into the prompt) explicitly told the model to call MCP tools like `nc_webdav_list_directory` by name.
- The model then had the *instruction* to call a tool it had no *schema* for. Faced with an unresolvable name, it fell back to routing the name through `pipeline` (the multi-model chaining tool), which treats any unrecognized identifier as a model name to look up on a configured endpoint — producing "Model not found" — and from there spiraled into creating a scheduled task as a misguided attempt to "fix" the perceived missing capability.
- Risk level: Medium (task-blocking, plus a stray real scheduled task left behind as a side effect).

## TDD Fix Plan

1. **RED**: A test asserting that when a matched skill's `requires_toolsets` contains a name not in `known_tool_names()` (a remote MCP server id/name), the tool-selection pipeline still surfaces at least one real qualified MCP tool schema relevant to the current query, not zero.
   **GREEN**: `src/agent_loop.py` — in the skill-matching loop, when a toolset isn't in the known static set, resolve it via `mcp_mgr.get_tools_for_explicit_server_reference(f"{_retrieval_query} on {_toolset}", _mcp_disabled_map)`. If any tools are found, narrow `_relevant_tools` to `set(ALWAYS_AVAILABLE) | forced_set | _skill_mcp_tools` (mirroring the existing explicit-server-reference narrowing) rather than only adding, so an earlier unrelated RAG hit (like `pipeline`) doesn't remain in scope and get misused against an MCP tool name.
   **verify**: live reproduction inside the running container — a query like "list files inside Work on nextcloud" against the real 162-tool Nextcloud server now resolves to real MCP tool names via `get_tools_for_explicit_server_reference`.
2. **RED**: A test asserting that a bare folder-listing query against Nextcloud does not also pull in unrelated similarly-scored tools (e.g. Deck attachment tools) that could distract the model from the one real read operation it needs.
   **GREEN**: `src/mcp_manager.py` `get_tools_for_explicit_server_reference()` — added `nextcloud_workflow_tools`: when `nc_webdav_list_directory` is enabled and the query contains list/show + folder/directory/contents/root/inside terms, return only that tool.
   **verify**: `test_explicit_nextcloud_folder_listing_excludes_unrelated_tools` in `tests/test_mcp_tool_params_in_prompt.py`; live-verified against the real server that "list files inside Work on Nextcloud" now returns exactly `{'mcp__nextcloud__nc_webdav_list_directory'}` (previously also included `deck_attach_file`/`deck_get_stacks`).
3. **RED/GREEN (defense in depth)**: updated the `operate-nextcloud-mcp-effectively` skill's pitfalls to explicitly forbid routing MCP tool names through `pipeline`/web-search/task-scheduling/deployment tools — they are direct callable MCP tools, not model names — so even a future retrieval miss is less likely to trigger the same spiral.
   **verify**: manual review of the updated skill file.

**REFACTOR**: None needed — additive resolution step plus one narrowing condition, following the same pattern already used for explicitly-named servers.

## Acceptance Criteria

- [x] A skill naming a connected remote MCP server contributes real callable tool schemas for the current query, not zero.
- [x] A Nextcloud folder-listing query returns only the relevant read tool, not unrelated Deck tools.
- [x] The `operate-nextcloud-mcp-effectively` skill explicitly forbids treating MCP tool names as model names or scheduling deployment tasks.
- [x] New unit test passes; live verification against the real 162-tool server confirms the fix.

## Resolution

**Fix applied:** `src/agent_loop.py` skill-toolset resolution now falls back to `mcp_mgr.get_tools_for_explicit_server_reference()` for non-static toolset names and narrows `_relevant_tools` accordingly; `src/mcp_manager.py` added `nextcloud_workflow_tools` narrowing for folder-listing queries; `operate-nextcloud-mcp-effectively` skill pitfalls updated.

**Open item:** the stray scheduled task created during the incident ("Deploy MCP Server for Nextcloud Access", id `5f1bb3e2-abe1-4f60-9400-48f2c98783c4`) still exists in the task list as of this writing and has not yet been deleted — flagged to the user, awaiting confirmation to remove.

**Status:** Resolved and deployed. Follow-on bug BUG-2026-09-18T095530 (bare "retry" after a failed MCP tool call) was found and fixed in the same investigation thread, documented separately in `specs/bugs/BUG-2026-09-18T095530-mcp-retry-loop.md`.

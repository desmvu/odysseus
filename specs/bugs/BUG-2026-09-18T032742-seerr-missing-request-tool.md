---
bug_id: BUG-2026-09-18T032742
status: resolved
severity: high
scope: agent-tool-selection
title: Seerr search-then-request workflow could be given search without the request tool
---

# BUG-2026-09-18T032742: Seerr search-then-request workflow could be given search without the request tool

## Problem

**Actual behavior:** Asking Odysseus to find and request a movie/show via the Seerr MCP server (15 tools total) sometimes surfaced only `seerr_search`, `seerr_auth`, `seerr_users` — or `seerr_search`, `seerr_discover`, `seerr_auth` — to the model, never `seerr_requests`. After a successful search, the model had no way to actually create the request, and wandered into unrelated Discover-page calls (large responses that could also cause a context-window overflow) or looped, unable to complete the task.

**Expected behavior:** A request-shaped prompt against a connected media server should always surface both the search tool and the request tool together, regardless of which 3 tools a generic lexical ranking would otherwise pick.

**How to reproduce:** With all Seerr MCP tools enabled, ask "find Constantine (2005) on seerr and request it" and observe the tool schemas sent to the model omit `seerr_requests`.

**Security impact:** NONE.

## Root Cause Analysis

- `McpManager.get_tools_for_explicit_server_reference()` (`src/mcp_manager.py`) ranks an explicitly-named server's tools by simple query-term overlap and returns only the top `max_tools` (default 3). With 15 Seerr tools competing on generic terms like "movie"/"show"/"request", `seerr_requests` did not reliably score in the top 3 against tools like `seerr_discover`, `seerr_auth`, or `seerr_users`.
- This function had no concept of a paired read-then-write workflow (search → request) — it only knew about raw lexical overlap, so the two tools that *must* appear together for a request to succeed had no guarantee of being selected together, or at all.
- Risk level: Medium (task-blocking UX failure for the entire request/media-server domain).

## TDD Fix Plan

1. **RED**: A test asserting that a query containing "request"/"requests" against a server whose enabled tools include one tool ending in `_search` and one ending in `_requests` returns exactly those two, regardless of what other tools score higher lexically.
   **GREEN**: `src/mcp_manager.py` `get_tools_for_explicit_server_reference()` — added a `request_workflow_tools` list: when the query's term set intersects `{"request", "requests"}`, and the server has at least one enabled `*_search` tool and one enabled `*_requests` tool, return exactly those two (checked before the generic ranked-tools fallback, after the explicitly-named-tool-identifier check).
   **verify**: `test_explicit_mcp_server_reference_keeps_search_and_request_workflow_together` in `tests/test_mcp_tool_params_in_prompt.py`.

**REFACTOR**: The same read-then-write pairing pattern was later generalized to Soulseek's search→download workflow (see the related `soulseek_workflow_tools` addition in the same function, part of the Soulseek skill work) and to Nextcloud's folder-listing narrowing (`nextcloud_workflow_tools`) — not a formal refactor into one shared helper, but the same checked-list-before-generic-ranking pattern was reused for each new MCP domain surfaced in this session.

## Acceptance Criteria

- [x] A request-shaped query against Seerr with all tools enabled returns exactly `{search_tool, requests_tool}`.
- [x] Behavior is unaffected when the query does not contain request/requests terms (falls through to existing ranking).
- [x] New unit test passes.

## Resolution

**Fix applied:** `src/mcp_manager.py` `get_tools_for_explicit_server_reference()` — added the `request_workflow_tools` short-circuit described above. Verified live against the real Seerr MCP server (`http://<redacted-lan-host>:3010/mcp`, server id `a478920d`) with all 15 tools enabled: `sorted(get_tools_for_explicit_server_reference("Request Toy Story 5 on Seerr."))` returns exactly `['mcp__a478920d__seerr_requests', 'mcp__a478920d__seerr_search']`.

**Status:** Resolved and deployed.

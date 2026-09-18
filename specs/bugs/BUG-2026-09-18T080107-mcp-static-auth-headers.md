---
bug_id: BUG-2026-09-18T080107
status: resolved
severity: medium
scope: mcp
title: Remote MCP servers requiring a static auth header had no way to authenticate
---

# BUG-2026-09-18T080107: Remote MCP servers requiring a static auth header had no way to authenticate

## Problem

**Actual behavior:** Connecting to a remote MCP server over HTTP/SSE that requires a static authentication header (for example a Portainer MCP gateway token) had no supported path — Odysseus's remote-MCP connection flow only supported OAuth-based auth (`build_provider`/`auth=provider`), or no auth at all.

**Expected behavior:** A remote MCP server can be configured with static HTTP headers (e.g. an API/gate token) that are sent on every request, independent of and without triggering the OAuth discovery flow.

**How to reproduce (pre-fix):** Attempt to connect an HTTP MCP server that expects a bearer/gate token header rather than OAuth; observe there is no field to supply it, and the connection either fails auth or incorrectly attempts OAuth discovery.

**Security impact:** LOW-MEDIUM — the header value is a credential; storage was designed to be encrypted at rest from the start (see fix), so no plaintext-secret exposure was introduced.

## Root Cause Analysis

- `McpManager.connect_server()` and its transport-specific helpers (`_connect_sse`, `_start_http_connect`/`_connect_http`) only accepted a `url` for HTTP/SSE transports and always built an OAuth provider (`build_provider(server_id, url, on_redirect=...)`) for the HTTP path — there was no parameter or code path for passing static request headers instead of/alongside OAuth.
- The `McpServer` database model (`core/database.py`) had no column to persist such headers, so even if the in-memory connection supported them, there was nowhere durable to store a per-server header set across restarts.
- Risk level: Low (missing capability, not a broken existing one) but blocking for any Portainer-MCP-gateway-style deployment using static tokens instead of OAuth.

## TDD Fix Plan

1. **RED**: A test asserting that `McpManager.connect_server(..., transport="http", headers={"X-Api-Key": "..."})` passes those headers into the underlying `streamablehttp_client` call and does NOT attempt OAuth discovery when headers are supplied.
   **GREEN**: `src/mcp_manager.py` — `connect_server()`, `_connect_sse()`, `_start_http_connect()`, `_connect_http()` all gained a `headers: Optional[Dict[str, str]]` parameter, threaded through to `sse_client(url, headers=headers or None)` / `streamablehttp_client(url, headers=headers)`. When static `headers` are supplied, the OAuth provider is not built for that connection — static headers are treated as a complete auth posture.
2. **RED**: A test asserting a server's configured headers persist across an app restart and are not exposed in plaintext via any read API.
   **GREEN**: `core/database.py` — added `request_headers` column to `McpServer` (`EncryptedText`, encrypted at rest, mirroring the existing `oauth_tokens` column), with a migration (`_migrate_add_mcp_request_headers_column()`) that adds the column without exposing any existing secrets, registered in `init_db()`.
3. **RED/GREEN (supporting API/UI)**: `routes/mcp/mcp_routes.py` gained the request/response handling for setting a server's headers; `src/agent_tools/admin_tools.py` and `static/js/settings.js` gained the corresponding admin-tool and UI plumbing to configure headers per server.

**REFACTOR**: None needed — additive column/parameter threading following the existing `oauth_tokens` encrypted-column pattern.

## Acceptance Criteria

- [x] A remote MCP server can be connected using static HTTP headers instead of OAuth.
- [x] Static headers are stored encrypted at rest and survive a restart.
- [x] Supplying static headers does not trigger OAuth discovery for that connection.
- [x] Settings UI exposes a way to configure per-server headers.

## Resolution

**Fix applied (commit `03c5dbb9`, "feat(mcp): support authenticated remote MCP headers"):**
- `src/mcp_manager.py`: threaded `headers` through `connect_server`/`_connect_sse`/`_start_http_connect`/`_connect_http`; static headers bypass OAuth provider construction.
- `core/database.py`: added encrypted `request_headers` column on `McpServer` + migration `_migrate_add_mcp_request_headers_column()`, registered in `init_db()`.
- `routes/mcp/mcp_routes.py`, `src/agent_tools/admin_tools.py`, `static/js/settings.js`: API and UI support for configuring per-server headers.
- `specs/shell-mcp.md`: documentation updated.

**Status:** Resolved and merged (commit `03c5dbb9d5362ce7533ad475b18cbfe1443b267a`). A follow-on impact assessment for this change was recorded separately (`chore(specs): add impact assessment for MCP header auth`, commit `70d4482e`).

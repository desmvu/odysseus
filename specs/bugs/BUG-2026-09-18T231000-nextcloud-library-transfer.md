---
bug_id: BUG-2026-09-18T231000
status: resolved_pending_live_confirmation
severity: high
priority: high
scope: mcp-document-routing
title: Nextcloud MCP reads files but cannot create an Odysseus Library document
---

# BUG-2026-09-18T231000: Nextcloud MCP reads files but cannot create an Odysseus Library document

## Problem

When a user asks to transfer a Nextcloud Markdown file into the Odysseus Library, the agent reads the file successfully but pastes it into chat. On a subsequent explicit create request, Qwen sees an invalid learned skill referring to nonexistent `import-document`, then attempts an unrelated `create_session` with `gpt-4`, errors, and loops instead of creating a Library document.

**Correction:** copied `<think>` blocks are intentional chat-export content, not part of this bug.

## Root Cause Analysis

1. **Reproduce:** The supplied conversation shows `nc_webdav_read_file` succeeding, followed by chat paste instead of a `create_document` call. Then model selection fails with `Model 'gpt-4' not found on any configured endpoint`.
2. **Isolate:** The original import skill instructed nonexistent commands `nextcloud_mcp.get` and `import-document`. The first repair preserved `create_document` in explicit-MCP and follow-up narrowing, but live logs exposed a third narrowing path: the matched `operate-nextcloud-mcp-effectively` skill replaces the selection with only remote Nextcloud schemas. Separately, the API schema builder appended every admin tool whenever the request contained broad words such as `MCP` or `document`; this exposed `create_session` and `list_models`, which Qwen then chose.
3. **Hypothesis:** Preserve `create_document` through all three narrowing paths, including matching remote-MCP skills; do not append unrelated admin schemas when a specific relevant-tool set already exists. Retire the conflicting critique/model-selection skill.
4. **Verify:** The live failing trace confirmed the root cause: selected tools omitted `create_document`, while `tools_sent` included `create_session` and `list_models`. Added routing coverage for all narrowing paths and the admin-schema guard. Targeted test run passed; live retry is still required.

## Fix

- Added `_is_mcp_document_transfer_request()` in `src/agent_loop.py`.
- Preserved the local `create_document` schema alongside selected remote MCP tools for explicit, follow-up, and skill-triggered MCP routing.
- Stopped the API schema builder from appending broad admin actions when a specific relevant-tool set exists.
- Replaced the invalid import skill with a strict v2 procedure and declared `requires_toolsets: [create_document, nextcloud]`.
- Retired the conflicting `import-nextcloud-document-to-odysseus-and-critique` skill, which incorrectly instructed critique and teacher-model selection.

## Third pass — generalize the fix, remove dead code

The second fix worked live (user confirmed the import succeeded and a separately-triggered skill also succeeded in the same session), but the `create_document` allowance was hardcoded to one specific skill combination. Auditing `src/agent_loop.py`'s skill-aware tool-narrowing loop found the actual systemic shape of the bug: **any** skill whose `requires_toolsets` mixes a local Odysseus tool with a remote MCP server name loses the local tool, because the MCP-resolution branch replaces `_relevant_tools` wholesale on each matching toolset, discarding local toolsets added earlier in the same loop.

- Replaced the `create_document`-specific carve-out (in the skill-narrowing branch only) with `_sk_local_toolsets`: computed once per matched skill from its own `requires_toolsets`, then unioned back in whenever that skill's MCP branch narrows `_relevant_tools`. Any future skill combining a local writer + remote server name is now covered automatically, not just this one.
- Audited `data/skills/**/SKILL.md` for `requires_toolsets`: only 3 skills declare it (`operate-nextcloud-mcp-effectively` → `[nextcloud]`, `find-or-download-music-with-soulseek` → `[soulseek]`, `import-nextcloud-document-into-odysseus` → `[create_document, nextcloud]`). Only the last mixes local + remote, confirming this was the sole live-impacted skill, but the fix is no longer skill-specific.
- Found and removed dead code left by the prior pass: an `if _needs_admin and not route_relevant_tools:` guard inside the `if route_relevant_tools:` branch of `_tool_schemas_for_route` could never be true (the outer condition already guarantees `route_relevant_tools` is truthy). Removed it; behavior is unchanged, intent is now stated in a comment instead of unreachable code.
- Confirmed Qwen3-14B model-capability detection is unaffected and correct: `"qwen3"` is in `model_supports_tools`, not `model_no_tools`, in `src/agent_loop.py` (~line 1063).

## Verification

- `./venv/bin/python -m pytest tests/test_mcp_document_transfer_routing.py tests/test_mcp_tool_params_in_prompt.py tests/test_document_tool_owner_scope.py tests/test_agent_loop.py -q` — 90 passed.
- `./venv/bin/python -m compileall -q src/agent_loop.py` — passed.
- User confirmed live: the document import succeeded and a separate skill ("critique-script") was called successfully in the same session, after the second fix and before this third (generalization-only) pass.
- Docker rebuilt (`docker compose up -d --build odysseus`); container healthy at `/api/health` after restart.

## Fourth pass — cross-branch reset, not skill-specific

User retried the exact same request after the third pass and it failed again: Qwen3-14B never called `create_document` at all (round 1 tool schema omitted it), instead fabricating success via `manage_memory` (claiming a fake `doc-7b3e9f` with an invented byte count) while the Library document does not exist.

### Root cause

Live log `[agent-intent] retrieval_query='Use Nextcloud MCP to import ... into a new Odysseus Library document ...'` confirmed `_is_mcp_document_transfer_request` correctly returns `True` for this exact text. The explicit-server-reference branch did add `create_document`. But a **second, independent** narrowing pass ran afterward: the skill-aware loop matched `operate-nextcloud-mcp-effectively` (a generic Nextcloud operations skill declaring only `requires_toolsets: [nextcloud]`, no `create_document`) in addition to `import-nextcloud-document-into-odysseus`. When iterating that second skill's toolsets, its MCP branch reassigned `_relevant_tools` from scratch using only *that skill's own* `_sk_local_toolsets` (empty), discarding the `create_document` the earlier explicit-server pass had added. Final `selected_tools=['ask_user', 'manage_memory', 'mcp__b3c26839__nc_webdav_read_file', 'update_plan', 'web_fetch', 'web_search']` confirms `create_document` was absent for the whole turn.

This is the same reset pattern as pass 2/3 but at a different layer: **every** narrowing pass (explicit-server, MCP follow-up, and now skill-triggered) independently reassigns `_relevant_tools` from scratch, so a value added by an earlier pass is lost whenever a later pass fires — regardless of which specific skill or toolset triggers it.

### Fix

- Moved `_mcp_document_transfer_tools` computation to run once, unconditionally, before any narrowing pass (`src/agent_loop.py` ~line 4137), instead of being defined only inside the `mcp_mgr`-gated block.
- Unioned `_mcp_document_transfer_tools` into the skill-triggered narrowing reassignment (`~line 4267`) alongside `_sk_local_toolsets`, matching the explicit-server and follow-up branches that already had it. Now all three reassignment sites include it: `source.count("| _mcp_document_transfer_tools")` == 3.

### Verification

- Added `tests/test_mcp_document_transfer_routing.py::test_transfer_tools_survive_every_narrowing_reassignment` asserting the variable is defined once, before its first use, and referenced at exactly 3 reassignment sites.
- `./venv/bin/python -m pytest tests/test_mcp_document_transfer_routing.py tests/test_mcp_tool_params_in_prompt.py tests/test_document_tool_owner_scope.py tests/test_agent_loop.py -q` — 91 passed.
- `./venv/bin/python -m compileall -q src/agent_loop.py` — passed.
- `docker compose up -d --build odysseus` — rebuilt, container healthy at `/api/health`.
- Live re-confirmation still needed: user should retry the same import request; expect `create_document` present in `tools_sent` regardless of which Nextcloud skill(s) match.

## Commit

`fix(mcp): transfer Nextcloud files into Library documents`

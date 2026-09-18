---
bug_id: BUG-2026-09-18T105700
status: resolved
severity: medium
scope: agent-tool-selection
title: Stale "list directory" intent from an earlier turn permanently hid nc_webdav_read_file
---

# BUG-2026-09-18T105700: Stale "list directory" intent from an earlier turn permanently hid nc_webdav_read_file

## Problem

**Actual behavior:** After "Use Nextcloud to list files inside Work." (correctly resolved to `nc_webdav_list_directory`), the follow-up "can you see the contents of Setup Tour 2026?" also resolved to only `nc_webdav_list_directory` — never `nc_webdav_read_file` — so Qwen falsely told the user "I cannot view its contents directly through the available tools," even though a real file-read tool exists on the connected Nextcloud MCP server and was simply never offered to the model.

**Expected behavior:** A follow-up asking to see a file's contents should resolve to `nc_webdav_read_file`, regardless of what the previous turn in the same conversation asked for.

**How to reproduce:** In one conversation, ask to list a Nextcloud folder, then ask to see the contents of a file named without its extension (as a user naturally would after seeing it listed). Observe the tool selection still returns only the directory-listing tool.

**Security impact:** NONE — reliability/UX gap (false capability denial), not an exposure issue.

## Root Cause Analysis

- This is a regression introduced by an earlier fix in this same session (BUG-2026-09-18T094500's `nextcloud_workflow_tools` narrowing in `McpManager.get_tools_for_explicit_server_reference()`).
- Continuation turns build their retrieval query from `_recent_context_for_retrieval()`, which concatenates the last few USER turns (newest first). The Nextcloud-specific list-vs-read disambiguation used `query_terms`, derived from this ENTIRE merged multi-turn string — so an earlier turn's literal words "list ... inside" kept satisfying the list-directory branch's condition on every later turn in the same conversation, even though the current turn's own words ("contents", "see") pointed at reading a file instead.
- A file-hint heuristic already existed (require a `.ext`-shaped token in the text before preferring `nc_webdav_read_file`), but the user's natural follow-up named the file without its extension ("Setup Tour 2026" instead of "SETUP TOUR 2026 - Desktop.md"), so that heuristic never fired either — leaving the stale list-intent as the only signal that mattered.
- Risk level: Low-Medium (false capability denial rather than data exposure, but directly undermines trust in tool availability after the very first multi-turn Nextcloud interaction).

## TDD Fix Plan

1. **RED**: A test asserting that a continuation query with an OLDER turn's "list ... inside" text and a NEWER turn's "see the contents of <name>" text resolves to `nc_webdav_read_file`, not `nc_webdav_list_directory`.
   **GREEN**: `src/mcp_manager.py` `get_tools_for_explicit_server_reference()` — the Nextcloud list-vs-read disambiguation now derives its own term set (`nc_terms`) from ONLY the latest turn (`query.split("\n", 1)[0]`, since continuation queries place the newest turn first), falling back to the full merged `query_terms` only when the latest turn alone yields no terms at all (e.g. a contentless continuation). Broadened `read_words` to include `"see"`/`"view"` in addition to the prior `"content"`/`"contents"`/`"show"`/`"read"`/`"open"`. The read-file branch now fires when read words are present AND (a file-extension hint exists anywhere in the merged text OR the latest turn does not also carry list/folder words) — so a plain "list ... inside" turn is unaffected, but a later read-shaped turn is no longer blocked by it.
   **verify**: `test_explicit_nextcloud_read_file_followup_after_stale_list_intent` in `tests/test_mcp_tool_params_in_prompt.py`; live-verified against the real 162-tool Nextcloud server.
2. **RED**: Regression check that the original single-turn "List files inside Work on Nextcloud." case still resolves to only `nc_webdav_list_directory`.
   **GREEN**: unchanged behavior confirmed — with no prior turn, the latest-turn term set IS the full query, so nothing changes for that case.
   **verify**: existing `test_explicit_nextcloud_folder_listing_excludes_unrelated_tools` still passes.
3. **RED**: Regression check for a genuinely ambiguous single turn ("show me the folder contents of Work") that should still prefer list-directory when both folder and content words appear in the SAME turn.
   **GREEN**: read-file branch only fires when list/folder words are ALSO absent from the latest turn's own terms (or a file extension hint is present); with `folder` present alongside `contents`, the branch correctly falls through to list-directory.
   **verify**: manually verified via a targeted probe script (not added as a permanent test — case included in this bug's TDD plan for the record).

**REFACTOR**: None needed — same shortcut structure, just re-scoped its term source.

## Acceptance Criteria

- [x] A file-read follow-up after an earlier folder-listing turn resolves to `nc_webdav_read_file`.
- [x] A standalone folder-listing turn still resolves to only `nc_webdav_list_directory`.
- [x] A single turn mixing folder and content words still prefers list-directory.
- [x] New unit test passes; live-verified against the real server.

## Resolution

**Root cause:** the Nextcloud read-vs-list disambiguation scored the FULL multi-turn continuation string instead of the current turn, so a single "list ... inside" turn could permanently starve `nc_webdav_read_file` out of every later turn in the same conversation.

**Fix applied:** `src/mcp_manager.py` `get_tools_for_explicit_server_reference()` now scopes the disambiguation to the latest turn's own words (falling back to the merged text only when the latest turn has none), and treats absence of list/folder words in that latest turn as sufficient (alongside the existing file-extension hint) to prefer the read-file tool. Test added: `test_explicit_nextcloud_read_file_followup_after_stale_list_intent`.

**Status:** Resolved and deployed. Found while the user was validating an earlier turn's behavior in production ("would you consider this better logic yeah?") — the model's declined-capability response was in fact caused by this bug, not correct reasoning; flagged to the user directly rather than confirmed as good behavior.

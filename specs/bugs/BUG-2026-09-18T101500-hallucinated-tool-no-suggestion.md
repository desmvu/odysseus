---
bug_id: BUG-2026-09-18T101500
status: resolved
severity: medium
scope: agent-tool-selection
title: Hallucinated/wrong tool name gets a bare "Unknown tool" error with no correction hint
---

# BUG-2026-09-18T101500: Hallucinated/wrong tool name gets a bare "Unknown tool" error with no correction hint

## Problem

**Actual behavior:** When the model emits a tool call whose name does not match any builtin handler or MCP qualified name (e.g. it invents `list_nextcloud_directory_via_mcp` instead of the real `mcp__b3c26839__nc_webdav_list_directory`), `_execute_tool_block_impl` in `src/tool_execution.py` falls through to the final `else` branch and returns exactly `{"error": f"Unknown tool: {tool}", "exit_code": 1}`. The model receives no information about what the correct name actually is, so on the next round it either repeats the same wrong name, invents a different wrong name, or abandons the tool call and narrates a fabricated result instead.

**Expected behavior:** When a tool name doesn't match any known tool, the error should suggest the closest real tool name(s) (builtin or MCP-qualified) so the model can self-correct within the same turn instead of continuing to guess or hallucinating an explanation.

**How to reproduce:**
1. Get the model to emit a tool call with a name that is close to, but not exactly, a real tool name (typo, invented wrapper name, or a plausible-sounding name for a capability it has actually already used under a different exact name).
2. Observe the tool result is `Unknown tool: <name>` with no further guidance.
3. Observe the model's next round either repeats the wrong name or gives up and claims a plausible-sounding but false outcome.

**Security impact:** NONE — this is a reliability/UX gap in error surfacing during tool dispatch, not an auth/data-exposure issue.

## Root Cause Analysis

- This investigation began from the user's broader question: "is Odysseus calling the right tool, and is a wrong call caused by the model being small (Qwen) or by Odysseus's own tool-selection logic?" A prior bug in this session (BUG-2026-09-18T095530) had already fixed one specific case — a bare "retry" after a failed MCP tool call dropping the tool from the schema — but that fix only helps when the model repeats the EXACT correct qualified name it already used. It does nothing when the model's tool call name is simply wrong from the start (typo/hallucination), because `retry_failed_tools` re-injects into `_relevant_tools` a name that itself never existed as a real tool.
- `src/agent_loop.py`'s tool-selection pipeline (`_classify_agent_request` → domain keyword regexes in `_DOMAIN_TOOL_MAP` → `ToolIndex.get_tools_for_query` RAG retrieval, k=8, in `src/tool_index.py`) is a layered, hand-tuned heuristic stack. Several `_KEYWORD_HINTS`/regex entries in `src/tool_index.py` carry comments noting they were added reactively after observing a specific wrong-tool selection in production (e.g. "the model has been observed defaulting to manage_memory even with manage_contact in the toolset"). This is a structural pattern: coverage gaps get found by users hitting them in the wild, not by systematic testing, and MCP tools in particular have no keyword-regex path at all (arbitrary server-defined names), relying entirely on embedding retrieval or exact-name reinjection after a *successful* previous use.
- This means wrong-tool-selection has (at least) two independent, compounding causes: (1) Odysseus's own retrieval/keyword layer can omit the right tool from the schema list, leaving the model no valid option, and (2) once a tool call fails for ANY reason (wrong name, dropped from schema, genuine transport error), the error-recovery loop gives the model no path back to the correct name — it just says "Unknown tool" and stops helping. Cause (2) is what this bug fixes; cause (1) is the broader, harder-to-close class already partially addressed by BUG-2026-09-18T095530 and the reactive keyword patches in `tool_index.py`.
- A smaller/less capable model (Qwen3-14B in the observed incident) is more likely to *fabricate* a plausible name under ambiguity and less likely to recover from an uninformative error than a larger model would — so model capability amplifies the failure, but the missing self-correction signal is squarely an Odysseus-side gap that would help models of any size recover faster.
- Risk level: Low (additive, does not change any existing successful path; only enriches the error message on an already-failing call).

## TDD Fix Plan

1. **RED**: A test asserting that dispatching a tool call with a name that is a near-miss of a real builtin tool name (e.g. `"read_fiel"` vs `"read_file"`) returns an error string that includes a "did you mean" suggestion naming the real tool, not just "Unknown tool: read_fiel".
   **GREEN**: In `src/tool_execution.py`'s final `else` branch of `_execute_tool_block_impl`, build a candidate set from `dynamic_handlers.keys()` (already imported) plus, when `mcp_mgr` is available, the qualified names from `mcp_mgr.get_all_tools()`. Use `difflib.get_close_matches(tool, candidates, n=2, cutoff=0.6)` and append a "Did you mean: ..." hint to the error message when a match is found.
   **verify**: `./venv/bin/python -m pytest tests/test_tool_execution.py -k unknown_tool -q`

2. **RED**: A test asserting that a genuinely nonexistent tool name with no close match (e.g. `"totally_made_up_capability_xyz"`) still returns a plain "Unknown tool" error with no fabricated suggestion.
   **GREEN**: `difflib.get_close_matches` naturally returns an empty list below the cutoff; only append the hint when matches is non-empty.
   **verify**: same test file, second case.

**REFACTOR**: None needed — additive change confined to the one error-formatting branch.

## Acceptance Criteria

- [x] A near-miss tool name gets a "did you mean: <real tool name>" suggestion in its error result.
- [x] A tool name with no close match still gets a plain "Unknown tool" error (no fabricated suggestion).
- [x] Existing "Unknown tool" behavior (exit_code=1, error key) is unchanged for callers that don't inspect the message text.
- [x] New unit tests pass.

## Resolution

**Fix applied:** `src/tool_execution.py` — in `_execute_tool_block_impl`'s final `else` branch, build a candidate set from `dynamic_handlers.keys()` (builtin tool registry, already in scope) plus, when an MCP manager is available, every `qualified_name` from `mcp_mgr.get_all_tools()`. Run `difflib.get_close_matches(tool, candidates, n=2, cutoff=0.6)`; when it returns matches, append `" — did you mean: <names>?"` to the error string. Added `import difflib`.

**Tests added:** `tests/test_unknown_tool_suggestion.py` — `test_near_miss_tool_name_gets_did_you_mean_suggestion` (`"read_fiel"` → suggests `read_file`), `test_no_close_match_leaves_plain_unknown_tool_error` (`"totally_made_up_capability_xyz"` → plain `"Unknown tool: ..."`, unchanged).

**Verification performed:**
- RED confirmed first: new test 1 failed against pre-fix code (`assert 'did you mean' in 'unknown tool: read_fiel'` → AssertionError), test 2 already passed (baseline behavior).
- GREEN: both tests pass after the fix.
- `python -m compileall -q app.py core routes src services scripts tests` — clean.
- `./venv/bin/python -m pytest tests/test_agent_loop.py tests/test_mcp_tool_params_in_prompt.py tests/test_unknown_tool_suggestion.py tests/test_edit_file.py tests/test_tool_policy.py -q` — 97 passed.
- Full suite (`./venv/bin/python tests/run_focus.py --fast`): 5936 passed, 21 failed. Confirmed via `git stash`/`git stash pop` that the same 21 (actually 17 covered by the stash-tested subset, all present) were already failing on `dev` before this change (GPU compose fixtures, token-cache atomic-swap, MCP reconnect args, foreground model routing, fenced-example native-tool-call tests) — pre-existing, unrelated to this change.

**Broader diagnostic (answers the user's original question — "is it Qwen being small or Odysseus' logic?"):**
- Both, but the user-visible failures traced in this session (BUG-2026-09-18T095530 and this bug) both trace to gaps on the Odysseus side, not raw model capability: (1) `src/agent_loop.py`'s tool-selection pipeline (`_classify_agent_request` domain-keyword regexes → `ToolIndex.get_tools_for_query` embedding retrieval, k=8, in `src/tool_index.py`) is a hand-tuned heuristic stack that has been patched reactively after specific observed misfires (see `_KEYWORD_HINTS`/`save_for_match`/`possessive_contact` comments in `tool_index.py` noting "the model has been observed defaulting to X"). MCP tools have no keyword-regex path at all — they rely entirely on embedding retrieval, so an MCP tool used successfully once has no guarantee of being re-selected on a later, differently-worded turn. (2) Once a tool call fails for any reason, the recovery path was uninformative (this bug) or scoped too narrowly (BUG-095530's Cookbook-only retry-continuation gate).
- Model size still matters as an amplifier: a smaller local model (Qwen3-14B in the observed incident) is more likely to fabricate a plausible-but-wrong tool name under ambiguity, and less likely to recover gracefully from a bad tool result, than a larger model would be. But the missing correction signal this bug fixes, and the missing continuation-scope this bug's predecessor fixed, are structural Odysseus-side gaps that would help models of any size recover faster — they are not something a bigger model alone would paper over, since the root issue is the tool literally not being offered/nameable correctly, not the model's reasoning quality once it has the right tool in view.
- Not fixed in this session (out of scope, noted for future work): the underlying reactive-patching pattern in `tool_index.py`/`_DOMAIN_TOOL_MAP` means new MCP servers or new builtin tools can still be under-covered by keyword regexes until someone hits the gap in production; a more systematic mitigation (e.g. broader `k`, session-level tool stickiness beyond bare retries, or periodic RAG-recall auditing against the full tool catalog) would need its own investigation.

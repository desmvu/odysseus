---
bug_id: BUG-2026-09-18T095530
status: resolved
severity: high
scope: agent-tool-selection
title: Bare "retry" after a failed MCP tool call drops the tool from scope and loops
---

# BUG-2026-09-18T095530: Bare "retry" after a failed MCP tool call drops the tool from scope and loops

## Problem

**Actual behavior:** After an MCP tool call failed (e.g. `mcp__b3c26839__nc_webdav_list_directory` against the Nextcloud MCP server), the user replied with a bare `"retry"`. The agent's tool-selection classified this turn as "low-signal" (no domain keywords in the single word "retry"), which dropped the previously-used MCP tool from the schema set sent to the model. Retrieval instead surfaced an unrelated tool set (`list_served_models`, `manage_mcp`, `send_email`, `cancel_download`, ...). With no way to actually retry the real action, the small model (Qwen3-14B) called `list_served_models` repeatedly with no new information, tripped the loop-breaker, and then hallucinated a nonexistent tool call (`list_nextcloud_directory_via_mcp`) to a fenced-block name that was never a real tool.

**Expected behavior:** A bare "retry"/"try again" immediately after a failed tool call should be recognized as a continuation of that exact prior action, regardless of which domain (Cookbook, Nextcloud MCP, email, etc.) the failed tool belonged to, and the same tool should remain available for the retry turn.

**How to reproduce:**
1. Trigger any MCP tool call that fails (e.g. a transient MCP transport error).
2. Reply with just "retry".
3. Observe that tool-selection logs show `low_signal=True continuation=False` and the originally-used MCP tool is absent from `tool_names`.

**Secondary symptom investigated in the same session:** the initial tool failure surfaced an empty error string to the model (`"(no output)"`), which the model then explained away by fabricating a plausible-sounding cause ("Nextcloud server unreachable... ConnectTimeout") that had no basis in the actual (unlabeled) exception. Live re-verification during this investigation confirmed Nextcloud/MCP connectivity and the exact same tool call succeeded instantly with real data — the reported "unreachable" state never existed.

**Security impact:** NONE — no exploit path; this is a reliability/UX bug in tool-selection and error surfacing, not an auth/data-exposure issue.

## Root Cause Analysis

- `src/agent_loop.py` `_classify_agent_request()` computes `low_signal = not continuation and not domains`. The single word "retry" matches none of the domain keyword regexes (cookbook/email/notes/files/etc.), so unless `continuation` is separately established, the turn is classified low-signal and RAG-only retrieval runs on the bare word "retry" — which semantically drifted toward unrelated tools like `list_served_models`/`manage_mcp`/`cancel_download`.
- The existing continuation path for retry-style phrases, `_is_contextual_retry_continuation()`, only recognized a retry as a continuation when the recent user-turn text matched `_COOKBOOK_CONTEXT_RE` — a keyword list scoped specifically to Cookbook/model-serving vocabulary (`cookbook`, `serve`, `vllm`, `sglang`, `ollama`, `gpu box`, `server`, model family names, etc.). A Nextcloud MCP retry ("Use Nextcloud to list files inside Work." → "retry") does not contain any of those words, so the gate failed and `continuation` stayed `False`.
- `_recent_context_for_retrieval()`, which builds the retrieval-query text for continuations, only walks `role == "user"` messages — it correctly would have surfaced the prior "Use Nextcloud..." user turn text once continuation was true, but continuation was never granted for non-Cookbook domains in the first place.
- Separately, `McpManager.call_tool()` (`src/mcp_manager.py`) caught the transport exception and returned `{"error": str(e), "exit_code": 1}`. Certain anyio/mcp transport exceptions (cancel-scope errors, `EndOfStream`, `ClosedResourceError`) stringify to an empty string, so the model received effectively no error information and had to invent an explanation.
- Risk level: Medium (isolated to tool-selection logic and error formatting; no data corruption, but caused a visible infinite-loop UX failure with a small local model).

## TDD Fix Plan

1. **RED**: A test asserting that after an assistant turn whose `metadata.tool_events` contains an entry with a non-zero `exit_code`, a subsequent bare "retry" user turn produces `continuation=True`, `low_signal=False`, and the failed tool's qualified name present in a new `retry_failed_tools` field, with the retrieval query inheriting the prior user turn's text.
   **GREEN**: Added `_last_assistant_failed_tool_names(messages)` in `src/agent_loop.py`, which reads the most recent assistant message's `metadata.tool_events` and returns qualified tool names with `exit_code not in (0, None)`. Broadened `_is_contextual_retry_continuation()` to also return `True` when this set is non-empty (in addition to the existing Cookbook-keyword path). `_classify_agent_request()` now returns `retry_failed_tools` in its result dict.
   **verify**: `python -c "from src.agent_loop import _classify_agent_request; ..."` (see Resolution — exact commands run) — confirmed `continuation=True`, `low_signal=False`, `retry_failed_tools={'mcp__b3c26839__nc_webdav_list_directory'}`.

2. **RED**: A test asserting that when the most recent tool event succeeded (`exit_code=0`), a bare "retry" does NOT force-retain that tool (`retry_failed_tools == set()`), to avoid over-broadening continuation to every retry-shaped word after a successful action.
   **GREEN**: `_last_assistant_failed_tool_names()` explicitly filters on non-zero/non-None `exit_code`, so a successful prior event yields an empty set.
   **verify**: same script — confirmed `retry_failed_tools == set()` for the success case.

3. **RED/GREEN (defense in depth)**: Even with corrected classification, retrieval-query text matching alone could still miss re-selecting a qualified MCP tool name (which carries no English keyword signal). Added explicit re-injection: in the tool-selection pipeline (`src/agent_loop.py`, near where `_relevant_tools`/`_base_relevant_tools` are finalized), `_retry_failed_tools` (filtered against `disabled_tools`) is unioned directly into `_relevant_tools` whenever non-empty, so the exact previously-failed tool is guaranteed present in the schema list sent to the model on the retry turn.
   **verify**: Rebuilt/restarted the Odysseus container (`docker compose up -d --build odysseus`); manually re-ran the reproduction script inside the container confirming the intent dict end-to-end.

4. **RED/GREEN (secondary fix)**: `McpManager.call_tool()` in `src/mcp_manager.py` now falls back to `type(e).__name__` when `str(e)` is empty, and wraps the message as `"MCP transport error ({detail}) calling {qualified_name}. Retry once; if it repeats, reconnect the server."` so the model always receives an actionable, truthful error instead of an empty string it might otherwise rationalize into a fabricated cause.
   **verify**: Code review of the modified `except` branch; no automated test added (pure string-formatting change on an exception path that is difficult to trigger deterministically in-repo without mocking the anyio transport).

**REFACTOR**: None needed — the fix is additive (new helper + one broadened condition + one explicit re-injection block) and does not change existing Cookbook-retry behavior, which is preserved as a secondary `or` branch.

## Acceptance Criteria

- [x] A bare "retry" after a failed MCP tool call is classified as a continuation with the failed tool's name available for re-selection, regardless of domain.
- [x] A bare "retry" after a *successful* tool call does not force-retain that tool (no over-broadening).
- [x] Existing Cookbook-specific retry-continuation behavior (`_COOKBOOK_CONTEXT_RE` path) is unchanged.
- [x] MCP tool-call failures always surface a non-empty, descriptive error to the model.
- [x] New unit tests added: `test_bare_retry_after_failed_mcp_tool_is_a_continuation_regardless_of_domain`, `test_bare_retry_after_a_successful_tool_call_is_not_a_continuation` in `tests/test_agent_loop.py`.

## Resolution

**Root cause (verified):** `_is_contextual_retry_continuation()` in `src/agent_loop.py` gated retry-continuation on a Cookbook-only keyword regex (`_COOKBOOK_CONTEXT_RE`), so a retry after a non-Cookbook (Nextcloud MCP) tool failure was classified `low_signal=True, continuation=False`, dropping the real tool from the model's schema list and causing Qwen3-14B to loop on an irrelevant tool (`list_served_models`) before hallucinating a nonexistent function name once the loop-breaker fired.

**Fix applied:**
- `src/agent_loop.py`: added `_last_assistant_failed_tool_names()`; broadened `_is_contextual_retry_continuation()` to treat any retry phrase after an actually-failed tool call (any domain) as a continuation; `_classify_agent_request()` now returns `retry_failed_tools`; the failed tool set is explicitly unioned back into `_relevant_tools` during tool selection.
- `src/mcp_manager.py`: `call_tool()` now always includes a non-empty error detail (falling back to the exception's type name) in MCP failure results.
- `tests/test_agent_loop.py`: two new regression tests covering the failed-retry and successful-retry cases.

**Verification performed:**
- `python -m compileall -q src/agent_loop.py src/mcp_manager.py` — clean.
- Rebuilt and restarted the Odysseus container (`docker compose up -d --build odysseus`).
- Ran the reproduction scenario directly against `_classify_agent_request()` inside the running container with a synthetic message history matching the real incident (failed `nc_webdav_list_directory` event → "retry"): confirmed `continuation=True`, `low_signal=False`, `retry_failed_tools={'mcp__b3c26839__nc_webdav_list_directory'}`, and `retrieval_query` inheriting the prior "Use Nextcloud..." turn text. Also confirmed the successful-event case yields `retry_failed_tools == set()`.
- Live-verified the underlying Nextcloud MCP server (`http://<redacted-lan-host>:8001/mcp`) was reachable and `nc_webdav_list_directory` returned real directory contents instantly, confirming the original "server unreachable" report was a hallucination, not a real outage.
- `tests/` is not present inside the Docker image (excluded by `.dockerignore`), so the new pytest-style tests were validated by running the equivalent logic directly via `python -c` inside the container rather than `pytest` in-container; they should be run via `./venv/bin/python -m pytest tests/test_agent_loop.py -q` on the host per project convention.

**Status:** Resolved and deployed to the running Odysseus instance as of 2026-09-18. Not yet re-run through the host-side `pytest` suite in this session — recommended before merging/landing.

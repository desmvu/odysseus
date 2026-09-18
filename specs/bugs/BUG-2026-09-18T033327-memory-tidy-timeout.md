---
bug_id: BUG-2026-09-18T033327
status: resolved
severity: medium
scope: memory
title: Memory Tidy's per-attempt LLM timeout was too short for local reasoning models
---

# BUG-2026-09-18T033327: Memory Tidy's per-attempt LLM timeout was too short for local reasoning models

## Problem

**Actual behavior:** Running a full Memory Tidy audit against a local reasoning model (e.g. Qwen3-14B-Q5) reliably failed with a 502, even though the model would have produced a valid response given more time.

**Expected behavior:** Tidy should allow enough time for a local model to finish a full rewrite pass over every memory before giving up on that attempt.

**How to reproduce:** Run a full Memory Tidy audit against a local Qwen3-14B-class model with a non-trivial number of stored memories; observe a 502 after ~120s even when the underlying model process is still actively generating.

**Security impact:** NONE.

## Root Cause Analysis

- A full Tidy audit asks the model to return a rewritten JSON list of every stored memory in one response. This is a large structured-generation task.
- Local reasoning models (Qwen3-14B-Q5 and similar) can legitimately take longer than 120 seconds to produce that full response, especially with extended "thinking" output before the final JSON.
- The per-attempt LLM call had a fixed 120s budget, so every attempt against such a model timed out before the model could finish, regardless of retry count — the timeout, not the model's ability, was the actual constraint.
- Risk level: Low (retriable/config-only fix; no data loss, since a timed-out attempt doesn't partially apply).

## TDD Fix Plan

1. **RED**: Reproduce by running Tidy against a local Qwen3-14B-class model with the memory set large/slow enough to exceed 120s, and observe the 502 timeout.
   **GREEN**: Raised Tidy's per-attempt LLM call timeout from 120s to 300s (5 minutes).
   **verify**: re-run the same Tidy audit against the same model and memory set; confirm it completes without a 502 within the new budget.

**REFACTOR**: None needed — single timeout constant change.

## Acceptance Criteria

- [x] Memory Tidy's per-attempt LLM timeout is 300s.
- [x] A full audit against a local Qwen3-14B-class model completes without a spurious 502 when the model itself would finish within 5 minutes.

## Resolution

**Fix applied:** raised Tidy's per-attempt LLM timeout from 120s to 300s (commit `ed306a5d`, "fix(memory): raise Tidy's per-attempt LLM timeout to 5 minutes").

**Status:** Resolved and merged (commit `ed306a5dfb4821f1322a8544776ee7df6d368b26`).

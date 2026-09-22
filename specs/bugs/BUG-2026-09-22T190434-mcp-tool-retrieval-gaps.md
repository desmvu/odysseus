---
bug_id: BUG-2026-09-22T190434-MCPRETRIEVAL
status: resolved
severity: medium
scope: agent-tools
title: Three MCP tool-retrieval gaps — finance domain, small-catalog ranking, tool_index parsing
---

# BUG-2026-09-22T190434-MCPRETRIEVAL: Three MCP tool-retrieval gaps

## Problem

**Actual behavior:** Three independent gaps in how the agent selects which
MCP tools to offer for a given turn:
1. A plain financial statement ("spent 500k on X", "my savings account",
   "invest in gold") matched no existing domain bucket in intent
   classification, so it was classified low-signal and the agent silently
   reused whatever MCP tools were relevant to the *previous, unrelated* turn
   instead of re-running retrieval — observed: an investment log landed in
   `manage_notes` with the Budget MCP never even offered, because the prior
   turn had only Gold MCP tools loaded.
2. A named MCP server with a small tool catalog (e.g. a 9-tool analytics
   server) went through the same lexical-ranking + `max_tools` cap designed
   for hundred-tool servers like Nextcloud/slskd — ranking a short
   natural-language query against only a handful of tools could drop the one
   the model actually needed. Observed: "last 10 videos" ranked
   `yt_channel_info`/`yt_channel_overview`/`yt_audience_retention` above
   `yt_top_videos`, which the model then reported as "not available".
3. `ToolIndex`'s prompt-text parser (`src/tool_index.py`) matched tool
   entries on the *stripped* line, losing the 2-space-indent signal that
   distinguishes a genuine top-level tool line from a nested sub-bullet
   inside a tool's own multi-line description (e.g. Seerr tool docs
   embedding param lines like `  - type: ...`). Since multiple real tools can
   share the same nested param name, this produced duplicate ChromaDB IDs
   (e.g. repeated `mcp_type`) and broke the entire upsert batch, silently
   degrading tool-RAG retrieval for every query that didn't hit an exact
   keyword/skill match.

**Expected behavior:** Financial statements should route to the correct
domain/MCP; small-catalog MCP servers should hand back their whole catalog
rather than being lexically ranked down to nothing useful; tool-index
ingestion should never misparse a nested description line as a phantom
top-level tool.

**Security impact:** NONE (retrieval/routing quality only).

## Root Cause Analysis

- (1) `_classify_agent_request()` (`src/agent_loop.py`) builds a `domains`
  set from regex buckets; there was simply no `finance` bucket, so any
  purely financial statement fell through to "low-signal" handling, which
  reuses the previous turn's tool selection instead of re-deriving it.
- (2) `McpManager`'s per-server tool-selection loop
  (`src/mcp_manager.py`) applies the same lexical-ranking/`max_tools`-cap
  logic uniformly regardless of catalog size — a design that makes sense for
  large catalogs (avoids flooding the context) but actively hurts small ones
  (ranking noise can outweigh signal when there are only a few candidates).
- (3) `ToolIndex._ingest_tools()`-equivalent line parser
  (`src/tool_index.py`) checked `line.startswith("- ")` on the
  *already-stripped* line, which can't distinguish a real top-level tool
  entry (produced by `get_tool_descriptions_for_prompt` as `f"  - {qualified_name}: ..."`,
  always exactly 2-space indented) from a deeper-indented nested bullet
  inside a description that happens to also start with `- ` after stripping.
- Risk level: Low (routing/ranking heuristics, no data correctness risk),
  but user-facing (wrong or missing tools offered to the model).

## TDD Fix Plan

1. **RED**: Confirmed via `_classify_agent_request()` source read that no
   regex bucket matched spending/income/investing language.
   **GREEN**: Added a `finance` domain bucket matching spend/earn/income/
   budget/invest/savings/salary/payment/deposit/withdraw/net-worth/gold-price/
   transaction vocabulary combined with a currency-amount pattern
   (`\d[\d,\.]*\s?(vnd|đ|usd)\b`).
   **verify**: `tests/test_tool_rag_finance_domain.py` — 4 tests covering
   spending/investing/savings statements and bare currency amounts matching
   the `finance` domain, and confirming non-finance requests don't
   false-positive. All passing.
2. **RED**: Confirmed via `McpManager` source read that the small-catalog
   path had no special case, going through the same ranking as large
   catalogs.
   **GREEN**: Added a `small_catalog_tools` short-circuit — when a server's
   enabled tool count is ≤ 12, its entire catalog is returned unranked
   instead of going through lexical scoring/`max_tools` capping.
   **Placement correction (post-audit)**: the first version of this fix
   short-circuited at the TOP of `get_tools_for_explicit_server_reference`'s
   return-priority chain, before the more specific `explicitly_named`/
   `nextcloud_workflow_tools`/`soulseek_*`/`request_workflow_tools` buckets
   — since nearly every pre-existing unit test in
   `tests/test_mcp_tool_params_in_prompt.py` uses a small (≤12-tool) synthetic
   catalog, this silently broke 9 of that file's tests during the pre-commit
   Preflight run (caught by running the FULL suite before committing, not
   just the new test file). Corrected by moving the `small_catalog_tools`
   check to the BOTTOM of the priority chain — a last-resort safety net that
   only applies when nothing more specific matched — which reduced the
   conflict to exactly 2 tests. Per explicit user decision, those 2 tests
   (`test_soulseek_small_catalog_returns_whole_catalog_even_for_download_only_query`,
   `test_explicit_mcp_server_reference_small_catalog_safety_net_ignores_max_tools`,
   both renamed from their prior names to describe the new behavior) were
   updated to accept the whole small catalog, since their fixtures are also
   ≤12 tools and hit the same safety net.
   **verify**: `tests/test_mcp_manager_small_catalog.py` — 3 tests covering
   the bypass, the inclusive threshold boundary (12 exactly), and confirming
   catalogs above the threshold still get ranked/capped normally. All
   passing. Full suite re-run after the placement fix: 13 failed / 5992
   passed / 3 skipped — the 13 failures reproduced identically on a clean
   `git stash`-ed baseline (unrelated to this session), confirming zero
   regressions from any fix in this session.
3. **RED**: Confirmed via `ToolIndex` source read that the parser matched on
   the stripped line, losing indent information.
   **GREEN**: Changed the match condition to check the *raw* (unstripped)
   line for the exact 2-space indent (`raw_line.startswith("  - ") &&
   !raw_line.startswith("   ")`) before treating it as a top-level tool
   entry.
   **verify**: `tests/test_tool_index_mcp_nested_bullet_parsing.py` — 3
   tests covering a nested description bullet not being indexed as a
   phantom tool, genuine top-level tools still indexing correctly, and two
   tools sharing a nested param name not colliding. All passing.

**REFACTOR**: None performed.

## Acceptance Criteria

- [x] Financial statements now match the `finance` domain bucket.
- [x] Small MCP catalogs (≤12 tools) bypass lexical ranking/capping and
      return their full tool set.
- [x] `ToolIndex` prompt-text parsing distinguishes top-level tool entries
      from nested description bullets by indent, on the raw (unstripped)
      line.
- [x] Automated regression tests for all three: `tests/test_tool_rag_finance_domain.py`,
      `tests/test_mcp_manager_small_catalog.py`,
      `tests/test_tool_index_mcp_nested_bullet_parsing.py` (10 tests total,
      all passing).

## Resolution

**Root cause:** Three independent, unrelated gaps in MCP tool-selection
heuristics: a missing domain-classification bucket, a one-size-fits-all
ranking strategy applied to catalogs too small to benefit from it, and an
indent-blind parser that could misidentify nested description text as a
top-level tool.

**Fix applied:** `src/agent_loop.py` (`finance` domain regex bucket),
`src/mcp_manager.py` (`small_catalog_tools` ≤12-tool short-circuit),
`src/tool_index.py` (raw-line indent check before treating a line as a
top-level tool entry).

**Status:** Resolved, deployed as part of the same session as the other bugs
documented alongside this one. Automated test coverage: 10 tests across
three files (`tests/test_tool_rag_finance_domain.py`,
`tests/test_mcp_manager_small_catalog.py`,
`tests/test_tool_index_mcp_nested_bullet_parsing.py`), all passing.

---
bug_id: BUG-2026-09-18T120000
status: open
severity: high
scope: agent-tool-selection
title: Named-resource follow-ups lose the MCP server before tool selection
---

## Evidence and root cause

Production logs at 11:23:36 classify `show me the contents of SETUP TOUR 2026 - Desktop.md` as `domains=['ui']`, `continuation=False`. The outgoing selection contains editor/admin tools but no Nextcloud reader. The previous explicit Nextcloud turn selected the directory tool successfully. Selector-only tests bypassed the missing server-context step.

The matched-skill loop also replaces the selected set per skill, allowing a later match to erase an explicit server's tools. Nextcloud byte-unit guidance tests use a synthetic server ID; production uses opaque IDs, so guidance is not injected.

## Plan / acceptance

1. Reproduce at the agent request boundary with a real McpManager and an opaque server ID. Assert the native read schema reaches the LLM, then exercise read/answer rounds using fake external I/O.
2. Resolve bounded follow-up context from the immediately preceding exchange: explicit current service wins; otherwise require a resource reference or actionable anaphora, and an unambiguous recent external service. Reselect using the current action, never replay old actions or expose the full catalog.
3. Preserve explicit/contextual selection against skill matches; union separately matched skill requirements when no explicit service takes precedence.
4. Match file-size guidance to advertised WebDAV tools rather than server IDs.
5. Regress Nextcloud/Soulseek/Seerr follow-ups, unrelated turns, ambiguous multiple services, disable/plan/guide-only policy, forced tools, generic models, and approval continuity.
6. Audit Qwen3-14B official inference recommendations against local runtime. Do not impose model-specific sampling on other models or overwrite user tuning blindly. Do not generate speculative memories from failed model claims.
7. Run focused and broader tests; deploy only after checks; distinguish deterministic harness coverage from real model success.

## Boundaries

No new dependencies, UI changes, remote mutations, approval bypass, global context expansion, or blanket injection of all MCP schemas. Existing uncommitted work is preserved. No automatic commits or PRs.

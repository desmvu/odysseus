# BUG-2026-09-23T000000: Explicit MCP server selection silently drops web_search/web_fetch for the same turn

**Install method:** Docker

## Problem

Found while auditing tool-selection efficiency for small native-function-calling
models (Qwen3-14B). Three points in `src/agent_loop.py` replace `_relevant_tools`
wholesale (not union) whenever an MCP tool set is narrower/more specific than
generic tool-RAG: an explicitly-named server, a resource follow-up, and a
skill-triggered MCP toolset. None of the three carried forward `WEB_TOOL_NAMES`
(`{web_search, web_fetch}`), even when `_classify_agent_request`'s domain
classifier had already detected "web" intent for the same message.

Repro shape: "Check Gold MCP for the current price, and also look up today's
headline" — the Gold MCP override at `src/agent_loop.py:4177` fires and replaces
`_relevant_tools` with `ALWAYS_AVAILABLE | forced_set | _explicit_mcp_tools |
_mcp_document_transfer_tools`, none of which contain web_search/web_fetch, even
though the "web" domain (containing "look up", "today") already matched
earlier in the same function at `src/agent_loop.py:~4088`.

## Expected behavior

A turn that both names a connected MCP server and asks for a quick live web
fact should retain both tool families.

## Actual behavior

web_search/web_fetch silently disappear from the schema list the moment any
of the three MCP-override branches fires, regardless of the domain
classifier's own "web" signal for that same turn.

## Fix

Added a single `_web_domain_tools = WEB_TOOL_NAMES if "web" in
(_intent.get("domains") or set()) else set()` gate computed once at
`src/agent_loop.py:4171`, and unioned it into all three replacement sites
(`src/agent_loop.py:4177` explicit server, `~4207` resource follow-up, `~4288`
skill-triggered MCP) — mirroring the existing `_mcp_document_transfer_tools`
carve-out precedent already used at the same three sites for local
document-save tools.

**verify**: `tests/test_agent_loop_mcp_override_preserves_web_domain.py` — 5
source-level regression tests (same pattern as
`tests/test_email_pdf_dock_overlap_js.py`, since all three sites live inside
one large async streaming function with no cheap standalone unit-test entry
point): the shared gate is defined exactly once from the domain classifier,
and each of the three MCP-override blocks unions it in alongside the existing
`_mcp_document_transfer_tools` carve-out. All passing.

## Audit-code checklist (bigpowers)

- Supply Chain & Security: N/A, no new dependencies, no secrets, no external
  API surface touched.
- CONVENTIONS.md Compliance: no docs written outside `specs/`, no `gh issue
  create`, scope limited to the exact gap found.
- Scope: 13 lines in `src/agent_loop.py`, no unrelated refactoring.
- Boy Scout Rule: touched code is a strict superset of before (no removals),
  comment added explaining WHY (not what).
- Types and Safety: no new `Optional`/`Dict`/`List` additions beyond the
  file's existing style; no `any`/type-bypass introduced.
- Test Coverage: 5 new tests, all passing; F.I.R.S.T-compliant (fast,
  independent, source-level assertions with no I/O).
- SOLID: single responsibility preserved — the gate is computed once and
  reused, not duplicated three times (DRY).
- Refactoring Smells: none introduced; this removes a latent Duplicated Logic
  risk by centralizing the "should web survive an MCP override" decision in
  one expression instead of three separate ad-hoc calls if fixed inline.

## Verification

- [x] `python -m compileall -q app.py core routes src services scripts tests`
      — clean.
- [x] Full local suite: 13 failed / 5997 passed / 3 skipped — the same 13
      pre-existing unrelated failures as the clean baseline (see
      `BUG-2026-09-22T190434-mcp-tool-retrieval-gaps.md`'s baseline run);
      5 new tests added and passing, zero regressions.
- [x] Docker rebuild + redeploy confirmed healthy
      (`docker compose up -d --build odysseus`, `curl localhost:7000/login`
      returns 200).
- [ ] Live confirmation with a real Qwen3-14B-Q5_K_M chat turn combining an
      explicit MCP server mention with a live-web-fact request — not run this
      session (requires the model to actually be loaded/serving); flagged as
      a residual gap for the user to spot-check.

**Status:** Resolved, deployed. Automated test coverage:
`tests/test_agent_loop_mcp_override_preserves_web_domain.py` (5 tests, all
passing). Live model behavior not spot-checked this session.

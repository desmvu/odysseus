---
bug_id: BUG-2026-09-18T090000
status: resolved
severity: high
scope: agent-skills
title: Qwen invented a placeholder Seerr mediaId instead of searching first
---

# BUG-2026-09-18T090000: Qwen invented a placeholder Seerr mediaId instead of searching first

## Problem

**Actual behavior:** Asked to "Request Toy Story 5 (2026) on Seerr", Qwen3-14B called `seerr_create_request` with a fabricated placeholder `mediaId` (`12345`) instead of first calling `seerr_search`/`seerr_list_search` to find the real TMDB id. An earlier custom skill (`seerr-media-request-with-tmdb-id`) also taught two additional wrong behaviors: calling a nonexistent operation `seerr_post_request` (the real operation is `seerr_create_request`), and manually URL-encoding the search query (Odysseus/httpx already encodes it automatically, so manual encoding produced literal `%20` characters in the search string and zero results).

**Expected behavior:** The model should always search first, select a result whose title/year/media-type exactly match the request, copy the real numeric id from that result, and only then call the request operation — never inventing an id or skipping the search step.

**How to reproduce:** With a skill present that omits an explicit anti-hallucination rule, ask to request a movie/show via Seerr and observe the model either skip search or invent an id.

**Security impact:** LOW — a fabricated mediaId could create a request against an arbitrary/wrong TMDB entry in the user's Seerr instance (wrong-content request, not a security exploit, but a data-integrity concern worth noting).

## Root Cause Analysis

- No skill existed instructing the model on the exact required sequence and forbidding common shortcuts, so the model filled the gap with a plausible-looking guess (a round placeholder id) rather than treating "I don't have the real id yet" as a hard stop.
- A separately-authored custom skill (`seerr-media-request-with-tmdb-id`) actively taught two wrong behaviors (`seerr_post_request` instead of `seerr_create_request`; manual URL-encoding of the search query), compounding the problem for any turn that matched it.
- This bug's occurrence was also enabled by BUG-2026-09-18T032742 (Seerr search-then-request workflow could omit `seerr_requests` from the tool schema) in earlier testing of the same feature — when `seerr_requests` was missing, the model substituted Discover-page browsing instead of a real request; once both tools were present, the id-hallucination behavior became the dominant remaining failure mode.
- Risk level: Medium (task correctness, not a security exploit; user confirmed no request had actually been created before the fix was applied and verified).

## TDD Fix Plan

1. **RED**: Manually reproduce: prompt "Request Toy Story 5 (2026) on Seerr" with the old/absent skill guidance and observe `seerr_create_request` called with `mediaId: 12345` (or `seerr_post_request` called at all, or a URL-encoded search query).
   **GREEN**: Created skill `request-media-from-seerr` (owner `desmondvu`, `/app/data/skills/media/request-media-from-seerr/SKILL.md`, v1.1.0) with an explicit procedure: use only `seerr_search`/`seerr_requests` (never `seerr_discover`/`seerr_issues`/`seerr_auth`); make exactly one `seerr_search` call using operation `seerr_list_search` with a plain-text, non-URL-encoded query; select a result only when title/year/media-type match; copy the numeric `id` directly as `mediaId` (never invent/convert/placeholder); call `seerr_requests` with operation `seerr_create_request` (never `seerr_post_request`) using only `{"body":{"mediaType":..., "mediaId":...}}`; stop and ask the user if search has no exact or multiple matches.
   **verify**: manual re-test — "Request Toy Story 5 (2026) on Seerr" now searches first, selects the exact match, and calls `seerr_create_request` with the real id. User confirmed (paraphrased): "it did it successfully."
2. **RED/GREEN (compounding cause)**: fixed together with BUG-2026-09-18T032742 (same session) so the request tool is reliably present alongside search, removing the Discover-wandering fallback that occurred when `seerr_requests` was absent.
   **verify**: covered by that bug's test, `test_explicit_mcp_server_reference_keeps_search_and_request_workflow_together`.

**REFACTOR**: None needed — additive skill authored from scratch; no prior correct skill existed to refactor. The bad custom skill (`seerr-media-request-with-tmdb-id`) was flagged for the user to disable/delete rather than edited in place, since it actively taught wrong operations.

## Acceptance Criteria

- [x] A media request always searches first with a plain-text, non-URL-encoded query.
- [x] The model never invents, converts, or substitutes a placeholder `mediaId`.
- [x] The model uses `seerr_create_request`, never `seerr_post_request`.
- [x] Ambiguous or no-match search results stop the flow and ask the user, rather than guessing.
- [x] User-confirmed successful end-to-end request.

## Resolution

**Fix applied:** new skill `request-media-from-seerr` (v1.1.0) with the anti-hallucination procedure described above, combined with the tool-pairing fix from BUG-2026-09-18T032742 so `seerr_requests` is reliably present. User flagged (and was advised to disable/delete) a separate bad custom skill teaching the wrong operation name and manual URL-encoding.

**Status:** Resolved; user confirmed successful request end-to-end after the fix.

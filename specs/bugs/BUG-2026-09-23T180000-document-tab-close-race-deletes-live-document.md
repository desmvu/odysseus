# BUG-2026-09-23T180000: A stale docs.get() during tab close silently soft-deleted a real document

**Install method:** Docker

## Problem

User asked the AI (Qwen3.8-27B) to write a 400-token story ("The Last
Broadcast"), the model successfully called `create_document` (doc id
`59f602dc-361c-4750-a892-abd9bfc14a94`) and the tool's own follow-up
`manage_documents action=list` confirmed it existed. Several minutes and
serve-profile switches later, the user reported: "i don't see the document
it created."

Confirmed via `data/app.db`: the row existed intact (1849 chars, owner
`desmondvu`, `archived=0`) but `is_active=0` — soft-deleted. Confirmed via
`docker logs odysseus-odysseus-1`: a real
`DELETE /api/document/59f602dc-... 200 OK` request was sent by the user's
browser (10.1.1.53). Ruled out (by code read) as the trigger: session
deletion (`core/session_manager.py:587` correctly only detaches
`session_id`, never touches `is_active`), the scheduled document-tidy task
(`src/document_actions.py:run_document_tidy`, hard-deletes rows via
`db.delete()` — the row still physically existed, so this never ran on it),
and every explicit-delete UI path in `static/js/documentLibrary.js` (all
three gated behind `styledConfirm('Delete this document?')`, which the user
never triggered).

Root cause: `_detachDocFromSession(docId, ...)` in `static/js/document.js`
(called by ordinary tab-close, `closeTab(docId)`, with **no confirmation
dialog**) reads `const doc = docs.get(docId);` then decides whether to save
or delete based on `hasContent`/`hasTitle` derived from `doc`. If `docs` had
already lost that entry by the time this ran (a duplicate close call, or a
race with another handler that removed it first), `doc` is `undefined`, and
`hasContent`/`hasTitle` both silently evaluate to `undefined` (falsy) —
sliding straight past the very safety check the existing code comment
describes into the `else` branch, which unconditionally fires
`DELETE /api/document/{docId}` for a document the function never actually
inspected. This is the same class of bug a prior fix (see the code comment
referencing "SETUP TOUR 2026 - Desktop") already fixed for the
doc-exists-but-stale-empty case — it just didn't cover doc-entirely-missing.

## Expected behavior

Closing a document tab never deletes a real document without an explicit,
confirmed intent to discard it.

## Actual behavior

A missing/already-removed Map entry at close time was treated as "safe to
delete" instead of "unknown, do nothing destructive."

## Fix

`static/js/document.js:_detachDocFromSession` now returns immediately
(after `docs.delete(docId)` bookkeeping) when `!doc`, before either the
`hasContent`/`hasTitle` computation or the delete branch can run — matching
the existing safety guard's stated intent, just closing the gap it left
open. `hasContent`/`hasTitle` no longer need the `doc &&` prefix since the
function has already returned by then if `doc` is falsy.

Restored the affected document immediately (`UPDATE documents SET
is_active=1 WHERE id='59f602dc-...'`) so the user's content wasn't lost.

**verify**:
- `tests/test_document_tab_switch_never_deletes_js.py` — added
  `test_missing_doc_entry_bails_out_before_the_delete_branch`, asserting the
  `if (!doc)` guard appears before the `method: 'DELETE'` branch in the
  function body and that its body contains `return;` with no `DELETE` call.
  3 tests total in this file, all passing.
- Full local suite: 13 pre-existing unrelated failures (same set reproduced
  on a clean baseline earlier this session), 6004 passed — zero
  regressions.
- Deployed via `docker compose up -d --build odysseus`, confirmed healthy.

**Status:** Resolved, deployed. The exact race that emptied the `docs` Map
before `_detachDocFromSession` ran (duplicate close event vs. some other
concurrent handler) wasn't isolated further — the fix makes the outcome
safe regardless of which race caused it, which is the correct fix shape for
a UI race condition that isn't reliably reproducible on demand.

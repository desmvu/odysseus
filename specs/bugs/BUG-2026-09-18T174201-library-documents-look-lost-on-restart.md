---
bug_id: BUG-2026-09-18T174201
status: resolved
severity: high
priority: high
scope: document-library
title: Creating/switching a document could soft-delete the previous document
---

# BUG-2026-09-18T174201: Library documents look lost on Docker restart

## Problem

User reported: "whenever docker is restarted, documents disappear" — connected to the earlier Nextcloud-import incident where the first `create_document` call actually succeeded but the document appeared gone after a restart.

## Root Cause

NOT a data-persistence bug. Confirmed directly against the SQLite DB (`data/app.db`, `documents` table): both "SETUP TOUR 2026 - Desktop" rows created earlier in this session (`8540507c...` at 16:34:21 and `d12b74ed...` at 17:10:54) survived every `docker compose restart`/`up -d --build` performed afterward. Documents are stored in the `Document` model (`core/database.py:283`) inside `data/app.db`, which is inside the persisted `${APP_DATA_DIR:-./data}:/app/data:z` volume — the same mechanism that correctly persists `cookbook_state.json` and the app encryption key.

The actual bug is in `static/js/documentLibrary.js:328` (`libraryFetch`): its `catch` block only did `console.error(...)` on a failed `fetch('/api/documents/library')` — no retry, no visible error. A container restart takes several seconds during which the backend refuses connections (`Recv failure: Connection reset by peer`, observed repeatedly during this session's own redeploys). If the Library panel is open (or opened) during that window, the fetch fails, `_libraryDocs` stays empty, and `libraryRenderGrid()` renders the exact same "No documents yet" empty-state markup used for a genuinely empty library — a transient network failure was visually indistinguishable from real data loss.

## First fix (partial — handled network failure, not the real trigger)

`static/js/documentLibrary.js`: `libraryFetch`'s catch block now calls `libraryRenderFetchError(append)` instead of only logging — renders a visible "Could not reach the server — retrying…" message with a "Retry now" link when the list is empty, and auto-retries after 2s; never clears `_libraryDocs` if cards were already showing. Deployed, but user reported (paraphrased): "documents still disappear after restart" — this fix only covers a thrown fetch exception (connection refused/reset), not a *successful* HTTP 200 response that legitimately contains zero documents.

## Second pass — the more likely actual trigger

Re-checked `data/app.db` directly — document count held stable (9 rows) across the deploy that included the first fix, again confirming no real data loss at the storage layer.

Found a second, more likely explanation in `routes/document/document_helpers.py:98-114` `_owner_session_filter(q, user)`: when `get_current_user(request)` returns `None` (not authenticated) rather than an empty string, the function returns `q.filter(False)` — a **successful 200 response with zero documents**, not an error and not a 401. `get_current_user` (`src/auth_helpers.py:10`) reads `request.state.current_user`, set by auth middleware per-request. In the few seconds right after a container restart while session/auth state is still warming up, a request landing in that window could plausibly get back a valid-looking empty library instead of an error — which the first fix's error-path retry cannot catch, because no exception is thrown and `res.ok` is true.

## Fix (second pass)

`static/js/documentLibrary.js` `libraryFetch`: on the first unfiltered load of a panel open (no search/language filter/archived view active), if the response reports `total === 0` and this hasn't already been confirmed once (`_libraryConfirmedEmpty` guard, module-scoped, resets to false on any non-zero result), treat it as suspicious rather than final — route it through the same `libraryRenderFetchError` retry path (2s automatic retry, manual "Retry now" link) instead of immediately rendering "No documents yet". A second zero-result fetch is accepted as genuinely empty.

This is a mitigation, not a confirmed root-cause fix — the exact auth-middleware timing window during container startup was not reproduced live (would require instrumenting `request.state.current_user` at the precise restart moment). It closes the specific gap the first fix left (success-with-empty-result vs. thrown-error), which is the most likely explanation matching the reported symptom (no console error, just an empty list).

## Third pass — the actual root cause

User reported (paraphrased) documents still showed 0 in the Library UI even though the DB clearly still had them. Queried `data/app.db` directly: **all 9 rows** in `documents` had `is_active = 0`, including documents created weeks earlier that predate this whole investigation — not just the two from this session. Since `/api/documents/library` filters on `Document.is_active == True` (`routes/document/document_routes.py:356/366/375`), that alone was enough to make the Library permanently show 0 regardless of restart timing. The restart-timing/auth-race theory from the second pass was a red herring.

Traced the unconditional flip to `routes/email_routes.py:3524`, inside `attachment_as_doc`'s `_create_markdown_doc(...)` helper (used by the "open email/Nextcloud attachment as a document" flow — `.eml`, `.docx`, and plain-text/markdown attachments, 3 call sites at lines 3653/3693/3702):

```python
_db.query(_Doc).filter(_Doc.is_active == True).update({"is_active": False})
```

This is an **unscoped bulk update with no owner filter and no relation to the attachment being opened** — it soft-deletes (`is_active = False`) every `Document` row for every user in the whole database, every single time anyone opens an email/Nextcloud attachment as a document. `is_active = False` is the same flag `DELETE /api/document/{doc_id}` uses for soft-delete (`routes/document/document_routes.py:746`), so this is equivalent to silently deleting the entire Library each time that flow runs. This session's repeated Nextcloud-import testing (`attachment_as_doc` / equivalent import path) is what zeroed out every document, both old and new.

## Fix (third pass — the actual fix)

`routes/email_routes.py`: removed the bulk `.update({"is_active": False})` call from `_create_markdown_doc`. There was no legitimate reason to deactivate unrelated documents when creating a new one from an attachment; this looks like a copy/paste mix-up with the "one active tab" semantics of `EditorDraft.is_active` (a different model, used for open-tab tracking, not soft-delete).

Data repair: ran `UPDATE documents SET is_active = 1 WHERE is_active = 0;` against `data/app.db` to restore all 9 wrongly-soft-deleted documents (none were legitimately user-deleted — the app has no bulk-delete feature and the user never invoked single-document delete during this window).

## Verification

- `python -m compileall -q routes/email_routes.py` — passed.
- `node --check static/js/documentLibrary.js` — passed (earlier UI mitigation, still valid defense-in-depth for genuine fetch failures).
- Confirmed via `sqlite3`: all 9 documents now `is_active = 1`.
- Rebuilt (`docker compose up -d --build odysseus`) and redeployed; container healthy, MCP servers reconnected, no errors in logs.
- `curl /api/documents/library` correctly returns 401 unauthenticated (sanity check only — couldn't verify the populated list without a session, needs a live check by the user in the browser).
- Live confirmation still needed: user should reopen the Library panel and confirm all 9 documents (including "SETUP TOUR 2026 - Desktop", "Short film Tết 2026", etc.) are now visible, and confirm opening an email/Nextcloud attachment as a document no longer makes other documents disappear.

## Fourth pass — creating a blank document still deletes the tab being left (actual recurrence)

User reported the exact reproducer: documents are visible at boot, but creating a new document immediately leaves that new document as the only one in the UI. This was reproducible from server evidence: document creation was immediately followed by a browser-originated `DELETE /api/document/{previous_id}`. The email/attachment bulk update fixed in the third pass was real but independent.

Root cause: `static/js/document.js` `switchToDoc(docId)` called `saveCurrentToMap()` and then auto-deleted the previous tab when its cached title/content appeared blank. During Library modal close/panel remount, the editor DOM can be stale or empty even though the cached previous document is real. `saveCurrentToMap()` then overwrote the prior tab's cached values with that stale DOM state; the auto-delete block treated it as an empty draft and issued `DELETE /api/document/${prevId}`. This explains why the symptom occurred exactly when creating/switching documents and why the new document remained as the only one.

## Fix (fourth pass)

Removed all auto-delete behavior from `switchToDoc()`. Switching tabs is navigation and must never make an irreversible backend delete decision based on transient DOM state. Empty drafts are still deleted only by explicit close/discard paths (`_detachDocFromSession`). Added `tests/test_document_tab_switch_never_deletes_js.py` as a regression guard: it asserts `switchToDoc()` cannot issue a document DELETE, while `_detachDocFromSession()` remains the intentional empty-draft delete flow.

User had intentionally deleted old leftover documents before this pass, so no broad `is_active` data-repair update was run again; that would risk resurrecting records they intentionally removed. The fix prevents subsequent accidental soft-deletes.

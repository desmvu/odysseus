---
bug_id: BUG-2026-09-22T190433-ATTPDF
status: resolved
severity: high
scope: documents-uploads
title: PDF opened from an email attachment permanently reports "Source PDF not found"
---

# BUG-2026-09-22T190433-ATTPDF: PDF opened from an email attachment permanently reports "Source PDF not found"

## Problem

**Actual behavior:** Opening a PDF email attachment as a Document (the
"Open in document editor" flow, `routes/email_routes.py` attachment-as-doc)
copied the attachment bytes to disk correctly, but every later read of that
PDF (including page-render requests used by the Document pane's PDF viewer)
reported "Source PDF not found" even though the file genuinely existed on
disk at the copied path.

**Expected behavior:** A PDF attachment opened as a Document should be
readable indefinitely afterward, the same as a PDF uploaded through the
normal upload flow.

**How to reproduce:** Open a PDF attachment from an email as a Document, then
reload or otherwise trigger a fresh read of that document's source PDF.

**Security impact:** NONE (denial of legitimate access, not an exposure).

## Root Cause Analysis

- `UploadHandler.resolve_upload()`/`reserve_upload()` (`src/upload_handler.py`)
  — used by every downstream PDF read, including page-render — only ever
  look up the `uploads.json` index; they never scan the upload directory on
  disk.
- The attachment-as-doc flow in `routes/email_routes.py` wrote the PDF bytes
  directly via `shutil.copyfile()` into the upload directory but never called
  anything to add a corresponding entry to `uploads.json`.
- Net effect: the file was genuinely present on disk, but permanently
  invisible to every code path that resolves an upload by ID through the
  index, since nothing ever indexed it.
- Risk level: Low blast radius (one write path, one new method with no
  existing callers to break), high user-facing severity (silently makes a
  just-created document's own source PDF unreadable).

## TDD Fix Plan

1. **RED**: Traced `resolve_upload()`/`reserve_upload()` and confirmed they
   only consult `uploads.json`, with no filesystem fallback scan.
   **GREEN**: Added `UploadHandler.register_existing_upload(file_id, path,
   owner, mime, original_name)` to `src/upload_handler.py` — indexes a file
   the server already wrote to disk by another path (mirrors the metadata
   shape `save_upload()` writes: id, path, mime, size, name, hash/checksum,
   timestamps, owner), guarded by `validate_upload_id()` and
   `_inside_upload_dir()` before touching the index.
   **verify**: `tests/test_upload_handler_register_existing_upload.py` —
   5 tests covering resolvability after registration, index-entry shape
   parity with `save_upload()`, and rejection of paths outside the upload
   dir, missing files, and invalid upload IDs. All passing.
2. **RED**: attachment-as-doc's `shutil.copyfile()` call site had no
   corresponding index write.
   **GREEN**: `routes/email_routes.py`, right after the `shutil.copyfile()`
   call, added a call to `UploadHandler.register_existing_upload()` (imported
   via `src.tool_utils.get_upload_handler()`), wrapped in a try/except that
   logs a warning on failure rather than failing the whole attachment-open
   request.
   **verify**: covered by the same `tests/test_upload_handler_register_existing_upload.py`
   suite (registration is exercised end-to-end via `register_existing_upload`
   directly; no separate route-level test was added for the
   `routes/email_routes.py` call site itself).

**REFACTOR**: None needed — `register_existing_upload()` is a small, additive
method with no interaction with existing call sites.

## Acceptance Criteria

- [x] `UploadHandler.register_existing_upload()` exists and correctly
      validates the upload ID and path before indexing.
- [x] Email attachment-as-doc's PDF copy path now indexes the file it
      writes.
- [x] Automated regression coverage: `tests/test_upload_handler_register_existing_upload.py`
      (5 tests, all passing) confirms `register_existing_upload()` makes a
      server-written file resolvable and rejects invalid inputs. No
      route-level integration test for the `routes/email_routes.py` call
      site specifically — minor residual gap.

## Resolution

**Root cause:** `shutil.copyfile()`-written attachment PDFs were never added
to `uploads.json`, and every downstream read path resolves uploads by index
lookup only, never a filesystem scan.

**Fix applied:** New `UploadHandler.register_existing_upload()` method
(`src/upload_handler.py`), called from the attachment-as-doc PDF copy path in
`routes/email_routes.py` immediately after the file is written to disk.

**Status:** Resolved. Deployed as part of the same session as
`BUG-2026-09-22T190432-email-pdf-dock-overlap.md`. Automated test coverage:
`tests/test_upload_handler_register_existing_upload.py` (5 tests, all
passing).

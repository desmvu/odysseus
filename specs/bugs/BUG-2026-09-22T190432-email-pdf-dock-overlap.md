---
bug_id: BUG-2026-09-22T190432-EMAILDOCK
status: resolved
severity: high
scope: frontend
title: Email window covers the Document/PDF pane after docking, resizing, or tile-snapping
---

# BUG-2026-09-22T190432-EMAILDOCK: Email window covers the Document/PDF pane after docking, resizing, or tile-snapping

## Problem

**Actual behavior:** Opening a PDF attachment (or a compose/reply draft) beside
the Email window produced a wide, uncoordinated Email pane that visually
covered part or most of the Document/PDF pane, instead of a clean side-by-side
split. The bug reappeared under several different trigger sequences — opening
a PDF from a normal floating Email window, dragging Email to the left edge
then opening a PDF, dragging the edge-dock resize handle while a PDF was
already open, and dragging Email onto the generic window-tiling "blue zone" —
each one traced to a *different* root cause, since these are independent
subsystems that all happen to reposition the same modal.

**Expected behavior:** Email and the Document/PDF pane should sit flush
side-by-side with no overlap, respecting the user's stated preference for a
genuine ~50/50 split (not a narrow sidebar), across every way of opening a
document beside Email and every way of subsequently dragging/resizing either
window.

**How to reproduce:** With a document/PDF pane open beside the Email window,
either (a) open a PDF attachment from a normal (non-fullscreen, non-docked)
floating Email window, (b) drag the Email window to the left edge then open a
PDF, (c) drag the edge-dock resize handle at the Email/Document seam, or (d)
drag Email onto the window-tiling "blue zone" hint. Under the "Bigger" text
size setting (CSS `zoom`, `.ui-scale-125`) the bug was present even when the
raw pixel coordinates reported by DevTools looked correct.

**Security impact:** NONE (visual/UX only).

## Root Cause Analysis

This was five distinct, independently-discovered bugs across three files,
found through a long trial-and-error session using live Puppeteer repros and
user-provided DevTools dumps, because each fix revealed the *next* layer:

1. **`_hasDesktopRoomForEmailAndDocument()` (`static/js/emailLibrary.js`)** —
   had a blanket `if (window.innerWidth >= 1100) return true` bypass that
   skipped the room check entirely on wide screens, and separately mixed
   pixel spaces: `leftEdge` was read pre-zoom (via `_emailSplitLeftEdge()`,
   raw CSS custom-property reads) but compared directly against post-zoom
   `window.innerWidth` — this is the same `getBoundingClientRect()`-vs-
   `style.*` zoom-space split documented in
   `specs/bugs/BUG-2026-09-17T195822-ui-zoom-position-math.md` and
   `CLAUDE.md`, just hitting a *comparison* instead of a `style.*` write.

2. **`_prepareEmailWindowForDocument()`'s `modal-left-docked` conversion
   (`static/js/emailLibrary.js`)** — when converting a manually drag-docked
   (chat-sharing) Email window into the email+doc split layout, it carried
   over the *stale* chat-sized width verbatim instead of re-clamping it
   against the doc pane's actual space requirement.

3. **`_clampRightDockWidth()` (`static/js/modalSnap.js`)** — only reserved
   `MIN_CHAT_WIDTH` (380px) when computing how wide a right-docked window
   (e.g. Email dragged to the right edge) could grow, with no awareness that
   a doc/PDF pane might be the thing actually sharing the row. Verified via a
   headless Puppeteer repro that this crushed the doc pane from 664px down to
   a 56px sliver.

4. **A generic, independent window-tiling system (`static/js/tileManager.js`)**
   — Odysseus has a separate "OS-style" tile-snap feature (the `#tile-ghost`
   "blue zone" preview, `data-_tile-zone`/`data-_tile-pre-snap` dataset
   attributes) that is entirely unrelated to the email-doc-split dock code in
   `modalSnap.js`/`emailLibrary.js`. Its `_applySnap()` explicitly clears the
   *other* dock system's bookkeeping (`modal-left-docked`/`-right-docked`
   classes, `--left-dock-w`/`--right-dock-w`) but never touched
   `body.email-doc-split-active` or the `--email-doc-split-*` CSS variables
   the Document pane's position depends on — so a tile-snap jumped Email to a
   fresh width while the Document pane stayed stranded at its old boundary.
   Separately, `_prepareEmailWindowForDocument()` only recognized
   `modal-left-docked`/`email-snap-left` classes; a tile-snapped modal has
   *neither* (tileManager only sets dataset attributes), so opening a PDF on
   an already tile-snapped Email window silently no-op'd, leaving the
   uncoordinated tile width in place indefinitely.

5. **The actual, final root cause — `_applyEmailDocSplitGeometry()`
   (`static/js/modalSnap.js`)** — this is the same zoom-space bug class as
   `BUG-2026-09-17T195822-ui-zoom-position-math.md`, but in a variant that
   bug's fix never covered: **CSS custom properties consumed directly by a
   pure stylesheet rule**, not a JS `.style.*` write. `_applyEmailDocSplitGeometry`
   stored `--email-doc-split-left-x`/`-email-w`/`-right-x` in *post-zoom*
   pixel space. A stylesheet rule in `static/style.css` (~line 16357-16362)
   applies these variables directly to the *outer* `#email-lib-modal` wrapper
   element (`left: var(--email-doc-split-left-x) !important; width:
   var(--email-doc-split-email-w) !important;`) — there is no JS code between
   the CSS `var()` substitution and the browser's own zoom-scaling render
   step, so a post-zoom value here gets scaled a *second* time by the 1.25x
   "Bigger" text-size zoom. This made the *outer* wrapper render noticeably
   wider than the *inner* `.modal-content` box, which was already correctly
   zoom-adjusted via a JS `.style.width` write. This is why DevTools showed
   `.modal-content` and `#doc-editor-pane` coordinates that looked perfectly
   flush (e.g. email ending at x=792, doc pane starting at x=792) while the
   window was still visibly covering the document — the *invisible* outer
   wrapper, not the inspected inner content box, was the thing actually
   painting over the doc pane.

   Found by searching this repo's own git history
   (`git log --oneline -- static/js/modalSnap.js static/js/emailLibrary.js
   static/style.css | grep -i "dock\|split\|zoom"`) for prior zoom fixes,
   which surfaced commits `ec455d98` and `ac20ebe6`
   (`BUG-2026-09-17T195822-ui-zoom-position-math.md`). Cross-checking the
   *sibling* functions in `emailLibrary.js` (`_setEmailDocumentSplit`,
   `_measureEmailDocumentSplit`) showed they already documented and followed
   the correct convention ("every style/custom-property write below is
   pre-zoom") — `modalSnap.js`'s version was the one that broke it.

   Separately, three caching-pollution bugs of the same *shape* (a value
   computed for one dock mode silently reused in another) compounded the
   confusion while debugging: `content._userDockWidth` and
   `content._emailDocSplitUserW` (in-memory DOM node properties set by the
   edge-dock resize handle) and a `localStorage`-persisted dock width were
   all being cached **unconditionally**, regardless of whether the
   email+doc split was active during that particular resize — so a width
   computed once in plain chat-dock mode (via the wider `_clampLeftDockWidth`)
   could silently win over the correct, doc-aware width for the rest of the
   page session (or, for the localStorage case, across reloads).

- Risk level: Medium-high blast radius (touches three files, one of which —
  `modalSnap.js` — is a shared generic modal-docking module used by other
  tool windows), but each individual change is small and additive.

## TDD Fix Plan

1. **RED**: Reproduced via headless Puppeteer (compose-draft flow as a
   real-PDF stand-in, since no live IMAP account was available for testing):
   logged in, opened Email, opened compose (creates the same
   `#doc-editor-pane` + `body.doc-view` a real PDF attachment uses), then
   simulated drag gestures via `page.mouse.move/down/move…/up`.
   **GREEN**: fixed `_hasDesktopRoomForEmailAndDocument()`'s zoom-space
   mismatch and wide-screen bypass; fixed `_prepareEmailWindowForDocument()`'s
   stale-width carryover with a fresh re-clamp against
   `_EMAIL_DOC_MIN_WIDTH`/`_EMAIL_DOC_BREATHING_ROOM`.
   **verify**: Puppeteer measured `docPaneRect`/`emailRect` at 1600px and
   1920px viewports — doc pane crush from 664px→56px eliminated, correct
   ~50/50-ish split confirmed at both widths.
2. **RED**: right-docking Email (drag to the right edge) while a doc pane was
   open still crushed the doc pane.
   **GREEN**: `_clampRightDockWidth()` now measures the live doc pane's
   `getBoundingClientRect().left` (safe mid-drag since `margin-right` never
   moves an element's left edge) and reserves `MIN_DOC_PANE_WIDTH` (460px)
   against it.
   **verify**: Puppeteer confirmed doc pane held at 444-460px depending on
   viewport instead of collapsing to 56px.
3. **RED**: user reported (paraphrased) the bug still happened specifically
   "when the email automatically snaps to the blue zone on the left" —
   DevTools dump showed `data-_tile-zone="left-half"` on the Email modal, a
   completely different subsystem (`tileManager.js`) than anything fixed so
   far.
   **GREEN**: `tileManager.js`'s `_zoneForContent()` now declines to offer
   any tile zone for the Email modal while `body.doc-view` is active,
   deferring entirely to the dedicated email-doc-split dock system.
   `_prepareEmailWindowForDocument()` also now detects and converts an
   already tile-snapped modal (`content.dataset._tileZone`) instead of
   silently no-op'ing on it.
4. **RED**: user reported (paraphrased) a very specific behavioral signature —
   "if it's 'modal-left-docked' it's bugged, but if it's 'modal-left-docked
   modal-dragging' it's correct (half/half)" — proving the bug appeared
   specifically at/after drag-release commit, not during the live drag.
   **GREEN**: found and fixed the three unconditional-caching bugs
   (`content._userDockWidth`, `content._emailDocSplitUserW`, and the
   `localStorage`-persisted dock width via `_saveDockWidth`) in
   `modalSnap.js`'s edge-dock resize-handle code, each now gated on whether
   the email+doc split was actually active when the value was computed.
   **verify**: user confirmed `localStorage` had no stale
   `odysseus-edge-dock-width*`/`odysseus-email-doc-split-width*` keys, ruling
   out persisted pollution as the *active* cause but leaving the code fix in
   place as correct hardening.
5. **RED**: with the above fixes deployed, user provided DevTools dumps of
   both `.modal-content` (`left: 48px`, `width: 744px`) and `#doc-editor-pane`
   (`left: 792px` — exactly `48 + 744`, mathematically flush) and confirmed
   (paraphrased) the layout was "still visually broken, even though coords
   match". This directly implicated something *outside* the inspected element
   boxes.
   **GREEN**: `git log`/`git show` on the prior zoom-fix commits surfaced the
   documented pre-zoom/post-zoom convention; reading `static/style.css`
   around the `.modal-left-docked` rules found the outer-wrapper CSS-var
   consumer. Fixed `_applyEmailDocSplitGeometry()` to divide `left`,
   `emailWidth`, and their sum by `_zoomRatio()` before writing the three
   `--email-doc-split-*` CSS custom properties, and updated the two
   downstream JS consumers (the resize-seam stripe positioner, and the
   width-save-on-release calculation in the seam-drag `onUp` handler) to stop
   double-converting now that the vars are pre-zoom.
   **verify**: deployed via `docker compose up -d --build odysseus`
   (static/js/ is baked into the image, not bind-mounted); user asked to
   hard-reload and retest — outcome pending live confirmation at time of
   writing.

**REFACTOR**: `_snapEmailModalToLeftSidebar()` had gained an `opts.force`
parameter during an intermediate fix attempt that was later reverted at its
one call site (a force-dock caused a separate drag-then-revert-to-floating
flicker regression), leaving the parameter/branch dead with zero callers.
Removed during the audit-code pass (`grep` confirmed no caller ever passed a
second argument). Caught and fixed a self-introduced regression during this
cleanup: the first edit removed `opts = {}` from the function signature but
missed the `!opts.force` reference two lines further down in the same guard
condition, which would have thrown `Cannot read properties of undefined` at
runtime on every call — fixed in the same pass before redeploying.

## Acceptance Criteria

- [x] Opening a PDF/compose draft from a normal floating Email window
      produces a room-aware split, not a fixed narrow/wide assumption.
- [x] Converting a manually drag-docked Email window into the doc split
      re-clamps its width instead of carrying over a stale chat-sized value.
- [x] Right-docking Email while a doc pane is open reserves the doc pane's
      minimum width instead of crushing it to a sliver.
- [x] The independent window-tiling system defers to the dedicated dock
      system while a doc pane is open, and a modal it already tile-snapped
      is correctly re-clamped when a document subsequently opens.
- [x] Edge-dock resize-handle drags no longer leak a chat-mode-computed
      width into the doc-split-aware code path, in memory or in
      `localStorage`.
- [x] `--email-doc-split-*` CSS custom properties are stored pre-zoom,
      matching the convention already documented and followed by
      `emailLibrary.js`'s sibling functions, so the pure-CSS stylesheet
      consumer on the outer Email modal wrapper renders at the same size as
      the JS-managed inner `.modal-content`.
- [x] Automated regression coverage: `tests/test_email_pdf_dock_overlap_js.py`
      (7 static-source tests, all passing) asserting the pre-zoom CSS-var
      storage, doc-pane-aware right-dock clamp, splitActive-gated caching
      (both in-memory sites), tileManager's doc-view deferral, and the
      removed dead `opts.force` parameter.
- [ ] Live user confirmation after the final (zoom-space) fix — pending at
      time of writing.

## Resolution

**Root cause:** Five compounding issues across three files: (1) a zoom-space
comparison bug and a wide-screen bypass in the room-availability check, (2) a
stale-width carryover when converting a manual dock into the doc-split
layout, (3) a right-dock width clamp with no awareness of an open doc pane,
(4) a completely independent generic window-tiling system that repositions
the same modal without coordinating with the doc-split geometry, and (5) the
actual final root cause — `_applyEmailDocSplitGeometry()` storing its CSS
custom properties in post-zoom space when a pure stylesheet rule (no
JS-side division possible) consumes them directly on the outer modal
wrapper, double-scaling under the "Bigger" text-size CSS `zoom` setting.
Three secondary unconditional-caching bugs (two in-memory DOM properties,
one `localStorage` key) also silently let a chat-mode-computed width leak
into the doc-split-aware code path.

**Fix applied:**
- `static/js/emailLibrary.js`: `_hasDesktopRoomForEmailAndDocument()` zoom-
  space fix + removed wide-screen bypass; `_prepareEmailWindowForDocument()`
  re-clamps on `modal-left-docked` conversion and now also handles an
  already tile-snapped modal; `_snapEmailModalToLeftSidebar()`'s width target
  changed from a narrow-sidebar formula to a genuine 50/50 split (per user's
  explicit design preference), with reserved room for the doc pane.
- `static/js/modalSnap.js`: `_clampRightDockWidth()` reserves a doc-pane
  minimum (`MIN_DOC_PANE_WIDTH = 460`) measured live; `_applyEmailDocSplitGeometry()`
  now stores its three CSS custom properties pre-zoom (the core fix); the
  edge-dock resize handle's width computation and its two caching sites
  (`content._userDockWidth`, `content._emailDocSplitUserW`) and its
  `localStorage`-persisted counterpart are now all gated on whether the
  email+doc split was active; `_resolveEmailDocSplitWidth()`'s fallback
  changed from up to 55% of available width to a genuine 50% target; the
  resize-seam stripe positioner and its release-time width-save calculation
  updated to match the new pre-zoom CSS-var convention.
- `static/js/tileManager.js`: `_zoneForContent()` declines to offer a tile
  zone for the Email modal while a doc pane is open.

**Status:** Deployed (`docker compose up -d --build odysseus`, container
confirmed healthy). Automated test coverage:
`tests/test_email_pdf_dock_overlap_js.py` (7 tests, all passing). Live user
re-confirmation after the final zoom-space fix was pending at time of
writing this doc — update this file's status/Acceptance Criteria checkbox
once confirmed.

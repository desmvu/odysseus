---
bug_id: BUG-2026-09-17T195822-ZOOM
status: resolved
severity: medium
scope: frontend
title: Popups, dropdowns, docked windows, and drag/resize mispositioned under "Larger" text size
---

# BUG-2026-09-17T195822-ZOOM: Popups, dropdowns, docked windows, and drag/resize mispositioned under "Larger" text size

## Problem

**Actual behavior:** With the "Larger" text-size setting enabled (`.ui-scale-125` on `<html>`), popups, dropdown menus, the minimized-window dock, and drag/resize handles across many tool windows rendered roughly 1.25x too large or positioned in the wrong place — often overshooting the intended anchor.

**Expected behavior:** All floating/positioned UI should render at the correct size and position regardless of the text-size setting.

**How to reproduce:** Enable Settings → "Larger" text size, then open any dropdown/popup/draggable tool window and observe its position/size drift from the anchor element.

**Security impact:** NONE.

## Root Cause Analysis

- The "Larger" text-size setting applies CSS `zoom` to `<html>`, which splits pixel measurement into two incompatible spaces in Chromium:
  - `getBoundingClientRect()` and mouse/pointer events report **post-zoom** (rendered) pixels — the same space as `window.innerWidth`/`window.innerHeight`.
  - `offsetWidth`/`offsetHeight`, `scrollHeight`, and any `element.style.*` assignment are interpreted in **pre-zoom** (layout) pixels.
  - At zoom `1` (Default text size) the two spaces coincide, so the bug is invisible unless "Larger" is active.
- Any code that measured a position/size via `getBoundingClientRect()` and then wrote it straight back through `element.style.*` (a common pattern for positioning dropdowns/popups relative to their anchor button) silently mixed the two spaces, producing values ~1.25x too large/far under the "Larger" setting.
- This pattern was scattered across many independently-written UI modules (Cookbook serve dropdowns, the modal/dock manager, drag/resize handles, calendar, editor, email, gallery, settings, skills, tour hints, compare panes), so it needed to be found and fixed module-by-module rather than in one shared function.
- Risk level: Low (visual/UX only, no data loss), but broad in surface area.

## TDD Fix Plan

1. **RED**: With "Larger" text size active, measure a dropdown's rendered position/size against its anchor button in `static/js/cookbookServe.js` and confirm drift of ~1.25x.
   **GREEN**: Added a local `_zoomRatio()` helper (`window.innerWidth / document.documentElement.offsetWidth`) to `static/js/cookbookServe.js`, and divided every post-zoom `getBoundingClientRect()`-derived value by that ratio immediately before writing it into `element.style.*` (dropdown top/right positioning, viewport-clamp height math, list/item max-height calculations).
   **verify**: manual visual check with "Larger" text size on/off — dropdowns align with their anchor in both modes.
2. **RED**: Repeat for the minimized-window dock, generic popups/modals, and drag/resize handles.
   **GREEN**: commit `ec455d98` — added the same `_zoomRatio()` pattern to `static/js/modalManager.js` (dock centering), `static/js/windowResize.js`, `static/js/windowDrag.js`, and related popup/dock/modal position math.
   **verify**: manual visual check across minimize/restore, drag, and resize interactions under "Larger" text size.
3. **RED**: Audit remaining modules not yet covered (calendar drag/resize, editor popovers/panels, email inbox/library, gallery, section management, settings sidebar, skills, theme zone highlight, tour hints, compare panes) for the same `getBoundingClientRect()` → `style.*` pattern.
   **GREEN**: commit `ac20ebe6` — extended the same `_zoomRatio()` conversion to `static/js/calendar.js`, `static/js/compare/panes.js`, `static/js/compare/vote.js`, `static/js/document.js`, `static/js/editor/build/right-panel.js`, `static/js/editor/canvas-events.js`, and others (see commit for full file list).
   **verify**: manual visual check of each affected module under "Larger" text size.

**REFACTOR**: None performed — the `_zoomRatio()` helper is duplicated per-module rather than extracted into a shared utility. This is documented in `CLAUDE.md` as a known pattern (search for `_zoomRatio` before assuming a similar popup/dropdown/drag bug elsewhere is new) rather than refactored, since each module already imports independently and a shared import would touch every affected file for a non-functional change.

## Acceptance Criteria

- [x] Cookbook serve dropdowns position correctly under "Larger" text size.
- [x] Modal/dock manager, drag, and resize handles position correctly under "Larger" text size.
- [x] Remaining flagged modules (calendar, editor, email, gallery, settings, skills, theme, tour, compare) position correctly under "Larger" text size.
- [x] `CLAUDE.md` documents the `_zoomRatio()` pattern so future modules check for this bug class before treating a similar symptom as novel.

## Resolution

**Root cause:** CSS `zoom` (applied by the "Larger" text-size setting) splits `getBoundingClientRect()`/pointer-event pixels (post-zoom) from `offsetWidth`/`offsetHeight`/`scrollHeight`/`style.*` pixels (pre-zoom); any code measuring in one space and writing in the other renders ~1.25x too big or too far off.

**Fix applied:** a per-module `_zoomRatio()` helper (`window.innerWidth / document.documentElement.offsetWidth`) dividing post-zoom measurements before every affected `style.*` write, rolled out across three commits as more affected modules were found:
- `e6069c48` — initial fix in `static/js/cookbookServe.js`.
- `ec455d98` — `static/js/modalManager.js`, `static/js/windowResize.js`, `static/js/windowDrag.js`, and general popup/dock/modal position math.
- `ac20ebe6` — remaining modules: `static/js/calendar.js`, `static/js/compare/panes.js`, `static/js/compare/vote.js`, `static/js/document.js`, `static/js/editor/build/right-panel.js`, `static/js/editor/canvas-events.js`, plus email/gallery/settings/skills/theme/tour modules.

**Status:** Resolved and merged across commits `e6069c48481c94eba939ab8369ea38a27e2a99f9`, `ec455d98d486125a3e24f30302c317ff2d4466ec`, `ac20ebe6d4bd6515e8c33571ba5c107c1d2bdf11`. Documented in `CLAUDE.md` as a recurring bug-class check for any future popup/dropdown/drag module.

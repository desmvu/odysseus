"""Regression test: Email window must not cover the Document/PDF pane.

BUG-2026-09-22T190432-EMAILDOCK: five compounding bugs let the Email window
render wider than (or uncoordinated with) the Document/PDF pane it's docked
beside. This asserts the source-level invariants of each fix so a future
edit can't silently regress one of them without a test failing first.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODAL_SNAP_JS = (ROOT / "static/js/modalSnap.js").read_text()
TILE_MANAGER_JS = (ROOT / "static/js/tileManager.js").read_text()
STYLE_CSS = (ROOT / "static/style.css").read_text()


def _function_body(src: str, signature: str) -> str:
    start = src.index(signature)
    depth = 0
    cursor = src.index(") {", start) + 2
    while cursor < len(src):
        if src[cursor] == "{":
            depth += 1
        elif src[cursor] == "}":
            depth -= 1
            if depth == 0:
                return src[start : cursor + 1]
        cursor += 1
    raise AssertionError(f"unbalanced braces after {signature!r}")


def test_email_doc_split_geometry_stores_css_vars_pre_zoom():
    """The root-cause fix: style.css consumes --email-doc-split-* directly
    via var() with no JS division point, so the JS writer must divide by
    the zoom ratio itself or the browser's CSS zoom double-scales it."""
    body = _function_body(MODAL_SNAP_JS, "function _applyEmailDocSplitGeometry(left, emailWidth)")
    assert "--email-doc-split-left-x', `${left / zr}px`" in body
    assert "--email-doc-split-email-w', `${emailWidth / zr}px`" in body
    assert "--email-doc-split-right-x', `${x / zr}px`" in body


def test_style_css_still_consumes_the_vars_directly_on_the_outer_wrapper():
    """Guards the assumption behind the above fix: if this stylesheet rule
    ever stops reading the vars directly (e.g. moves to a JS-driven inline
    style), the pre-zoom storage convention may no longer be needed."""
    assert "left: var(--email-doc-split-left-x, 0px) !important" in STYLE_CSS
    assert "width: var(--email-doc-split-email-w, 420px) !important" in STYLE_CSS


def test_right_dock_width_reserves_doc_pane_minimum():
    body = _function_body(MODAL_SNAP_JS, "function _clampRightDockWidth(width)")
    assert "MIN_DOC_PANE_WIDTH" in body
    assert "doc-editor-pane" in body


def test_edge_dock_resize_only_caches_split_width_when_split_is_active():
    """content._userDockWidth / _emailDocSplitUserW must be gated on
    splitActive, or a width computed in one dock mode silently overrides
    the correct width in the other for the rest of the page session."""
    assert "if (!splitActive) content._userDockWidth = w;" in MODAL_SNAP_JS
    assert "if (splitActive) content._emailDocSplitUserW = w;" in MODAL_SNAP_JS


def test_edge_dock_resize_only_persists_width_when_split_is_not_active():
    assert (
        "const _skipSave = side === 'left' && document.body.classList.contains('email-doc-split-active');"
        in MODAL_SNAP_JS
    )


def test_tile_manager_defers_to_dock_system_while_doc_pane_is_open():
    body = _function_body(TILE_MANAGER_JS, "function _zoneForContent(content, x, y)")
    assert "isEmailModal" in body
    assert "document.body.classList.contains('doc-view')" in body


def test_snap_email_modal_to_left_sidebar_has_no_dead_force_parameter():
    """Boy Scout Rule cleanup: opts.force was added then abandoned with
    zero callers. Guards against it silently coming back half-wired."""
    assert "function _snapEmailModalToLeftSidebar(modal) {" in (
        ROOT / "static/js/emailLibrary.js"
    ).read_text()

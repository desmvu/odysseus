"""Pin Notes' virtual-panel minimize order.

``notes.js`` has a browser-only import graph, while this regression depends on
CSS transition timing between the right dock and the composer. A source contract
is therefore the practical narrow guard: the dock must be released before
modalManager creates/measures the minimized chip, and the manager must center an
unpositioned dock on the composer in active-chat layouts too.
"""
from pathlib import Path


NOTES_JS = Path("static/js/notes.js").read_text(encoding="utf-8")
MODALS_JS = Path("static/js/modalManager.js").read_text(encoding="utf-8")
SNAP_JS = Path("static/js/modalSnap.js").read_text(encoding="utf-8")


def _close_panel_body() -> str:
    start = NOTES_JS.index("export function closePanel(direction)")
    end = NOTES_JS.index("export function togglePanel()", start)
    return NOTES_JS[start:end]


def test_notes_releases_right_dock_before_creating_minimized_chip():
    body = _close_panel_body()
    release = body.index("suspendDock(pane)")
    minimize = body.index("Modals.minimize('notes-panel')")
    assert release < minimize
    assert "Modals.refreshDockPosition()" in body


def test_default_minimized_dock_tracks_active_chat_composer():
    start = MODALS_JS.index("function _applyDockPos(dock)")
    end = MODALS_JS.index("// True when `chipRect`", start)
    body = MODALS_JS[start:end]
    assert "const composer = chatContainer?.querySelector('.chat-input-bar');" in body
    assert "if (window.innerWidth > 768 && rect && rect.width > 0)" in body
    assert "welcome-active" not in body


def test_hidden_docked_window_does_not_block_dock_release():
    # A modal that was docked, then closed through a path that never called
    # suspendDock/clearRightDock, can be left carrying the dock class while
    # hidden or disconnected. _hasOtherDockedWindow must ignore it, or every
    # future dock release (e.g. minimizing Notes) bails forever and the
    # composer stays pushed off-center.
    start = SNAP_JS.index("function _hasOtherDockedWindow(side, owner)")
    end = SNAP_JS.index("function _hasAnyOtherDockedWindow", start)
    body = SNAP_JS[start:end]
    assert "el.isConnected" in body
    assert "el.classList.contains('hidden')" in body
    assert "el.style.display === 'none'" in body

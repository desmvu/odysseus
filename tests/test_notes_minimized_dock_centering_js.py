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
    assert "if (!_dockPos && rect && rect.width > 0)" in body
    assert "welcome-active" not in body

"""Regression guard: a manual resize after minimize/restore must actually shrink the window.

modalManager.js's _applyRestoreHeight() sets content.style.minHeight when
restoring a window from the dock chip, to preserve its prior size across the
minimize/restore cycle. That min-height was never cleared afterward, so a
subsequent user-driven resize to something SMALLER set style.height to the
new value but the box kept rendering at the old (larger) min-height -- CSS
min-height always wins over a smaller height. The resize looked like it
worked (the stored/reported size changed) while the window didn't visibly
shrink, leaving almost no vertical room -- so a following drag (move) looked
"stuck near the top" since there was nowhere to move it down into.

Reproduced live with Puppeteer against a running container: restore -> resize
smaller -> getBoundingClientRect().height still matched the old (pre-resize)
size while style.height matched the new one, confirming min-height was the
active constraint. After the fix, height matches style.height and dragging
afterward moves the full requested distance instead of clamping near the top.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "static/js/windowResize.js"


def test_manual_resize_begin_clears_stale_min_height():
    text = SRC.read_text(encoding="utf-8")
    begin_start = text.index("function begin(cx, cy, edges) {")
    begin_end = text.index("\n  function move(cx, cy) {")
    begin_body = text[begin_start:begin_end]
    assert "content.style.minHeight = '';" in begin_body, (
        "begin() must clear a leftover min-height from modalManager's "
        "restore-from-minimize nudge, or a smaller resize silently fails "
        "to actually shrink the window"
    )


def test_min_height_clear_happens_after_dimensions_are_pinned():
    text = SRC.read_text(encoding="utf-8")
    begin_start = text.index("function begin(cx, cy, edges) {")
    begin_end = text.index("\n  function move(cx, cy) {")
    begin_body = text[begin_start:begin_end]
    height_idx = begin_body.index("content.style.height = ")
    minheight_idx = begin_body.index("content.style.minHeight = '';")
    assert height_idx < minheight_idx

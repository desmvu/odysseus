"""Regression guard: the GGUF quant <select> must not render clipped on first open.

_scanGgufRepo() replaces #cookbook-dl-gguf-quant's <option> list via one
.innerHTML assignment once a repo scan resolves. Without an explicit reflow
right after that mutation, Chromium can still be holding a stale popup-height
measurement from before the mutation (taken while the select still showed the
single "Scanning..." placeholder, or before the row was even display:flex) --
so the first time a user opens the native dropdown after a scan, its popup
renders clipped to that stale, smaller height, and only shows every option
correctly on a second open once layout has been recomputed in between.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "static/js/cookbook.js"


def test_gguf_option_replacement_forces_a_reflow_before_first_open():
    text = SRC.read_text(encoding="utf-8")
    innerhtml_idx = text.index("dlGgufQuant.innerHTML = quants.map(q => {")
    first_opt_idx = text.index("const first = dlGgufQuant.options[0];")
    assert innerhtml_idx < first_opt_idx
    between = text[innerhtml_idx:first_opt_idx]
    assert "void dlGgufQuant.offsetHeight;" in between, (
        "expected a forced reflow (reading a layout property) between "
        "replacing the <option> list and the next interaction, so Chromium "
        "can't hand the user a popup sized from stale pre-mutation layout"
    )

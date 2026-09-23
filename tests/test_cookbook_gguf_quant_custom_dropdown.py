"""Regression guard: the GGUF quant picker must not use a native <select> popup.

Follow-up to the reflow attempt in an earlier revision of this bug (see
specs/bugs/BUG-2026-09-24T193000-vision-fallback-and-gguf-dropdown-zoom.md),
which was live-reproduced as wrong: under the "Larger" text-size setting
(CSS `zoom: 1.25` on <html>), a native <select> popup mispositions and
clips itself -- a documented Chromium engine bug where zoom on an ancestor
doesn't propagate to native form-control popups, with no JS/CSS hook
available to fix it from page code.

The real fix replaces the native popup with a custom (JS-positioned)
dropdown, following the same zoom-safe pattern already used by
_showDepMenu() elsewhere in this file: read window.innerWidth /
document.documentElement.offsetWidth as the zoom ratio, and divide any
post-zoom (getBoundingClientRect) value by it before writing to .style.

Live-verified with Puppeteer at localStorage['odysseus-ui-scale']='125'
against the running container: the custom menu opened at the correct size
(8 full items, not clipped) and position (top = trigger.bottom + 4px,
left = trigger.left, exactly), and picking an item correctly updated the
underlying <select>'s value/selectedIndex, the trigger label, and the note
text -- confirming the hidden <select> remains the single source of truth
for every existing consumer (.value reads in the download-trigger logic,
the 'change' listener, .dataset.repo).
"""
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "static/js/cookbook.js"


def test_gguf_quant_select_is_hidden_not_removed():
    text = SRC.read_text(encoding="utf-8")
    assert '<select id="cookbook-dl-gguf-quant" style="display:none;"></select>' in text


def test_gguf_quant_trigger_button_exists():
    text = SRC.read_text(encoding="utf-8")
    assert 'id="cookbook-dl-gguf-quant-trigger"' in text
    assert "cookbook-dl-gguf-quant-trigger-label" in text


def test_custom_menu_uses_the_zoom_ratio_convention():
    text = SRC.read_text(encoding="utf-8")
    fn_start = text.index("function _showGgufQuantMenu()")
    fn_end = text.index("\n    dlGgufTrigger?.addEventListener", fn_start)
    body = text[fn_start:fn_end]
    assert "window.innerWidth / document.documentElement.offsetWidth" in body
    assert "/ zr" in body


def test_picking_an_item_drives_the_hidden_select_and_dispatches_change():
    text = SRC.read_text(encoding="utf-8")
    fn_start = text.index("function _showGgufQuantMenu()")
    fn_end = text.index("\n    dlGgufTrigger?.addEventListener", fn_start)
    body = text[fn_start:fn_end]
    assert "dlGgufQuant.selectedIndex = idx;" in body
    assert "_syncGgufTriggerLabel();" in body
    assert "dlGgufQuant.dispatchEvent(new Event('change', { bubbles: true }));" in body


def test_trigger_label_syncs_after_a_scan_completes():
    text = SRC.read_text(encoding="utf-8")
    scan_start = text.index("async function _scanGgufRepo(rawValue)")
    scan_end = text.index("\n    // Split `org/repo:tag`", scan_start)
    body = text[scan_start:scan_end]
    assert body.count("_syncGgufTriggerLabel();") >= 2, (
        "expected the trigger label to be resynced both when the "
        "'Scanning...' placeholder is set and once real options land"
    )


def test_scan_skips_redundant_rescan_of_an_already_scanned_repo():
    """Clicking the trigger blurs #cookbook-dl-repo, whose 'blur' listener
    unconditionally calls _scanGgufRepo as a safety-net rescan. Without a
    dedup guard that rescan resets the select to a single 'Scanning...'
    placeholder right as the trigger's click handler reads .options, so the
    dropdown wouldn't open on the same click that caused the blur -- only
    on a second click, after the redundant rescan finished. Live-reproduced
    and fixed by returning early when the repo already has real (non-
    placeholder) options for the current dataset.repo.
    """
    text = SRC.read_text(encoding="utf-8")
    scan_start = text.index("async function _scanGgufRepo(rawValue)")
    placeholder_idx = text.index('dlGgufQuant.innerHTML = \'<option value="">Scanning...</option>\';', scan_start)
    body = text[scan_start:placeholder_idx]
    assert "dlGgufQuant.dataset.repo === repo" in body
    assert "dlGgufQuant.options.length > 0" in body
    assert "dlGgufQuant.options[0].value !== ''" in body
    assert "return true;" in body

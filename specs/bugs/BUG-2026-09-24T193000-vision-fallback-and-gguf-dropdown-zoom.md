# BUG-2026-09-24T193000: Vision fallback chain unreachable, GGUF quant dropdown broken under UI zoom, chat defaults not auto-set

**Install method:** Docker

Follow-up to BUG-2026-09-24T120000. The user reported two of that bug's four
fixes still broken/incomplete after retest.

## 1. Vision still not working even with a fallback model configured

**Problem:** With `Settings -> AI Defaults -> Vision` "Model" left unset
(that picker only lists reachable models with an `item.offline` filter,
which at the time excluded the user's locally-served model) and a local
model (`ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`, served via Cookbook) added
under "Fallbacks" instead, chat still replied "no vision model is
configured for this session."

**Root cause:** `analyze_image_with_vl_result()` (`src/document_processor.py`)
resolved the primary `vision_model` setting first and returned the
`"[No vision model configured...]"` error **immediately** on a `ValueError`
from `_resolve_vl_model()` — before the `vision_model_fallbacks` chain
(`resolve_vision_fallback_candidates()`, populated from `Settings -> Vision ->
Fallbacks`) was ever consulted. The fallback chain was only appended *after*
a successful primary resolution, making it structurally unreachable
whenever the primary was empty or failed to resolve — exactly the case for
a user who can only add a local Cookbook-served model via Fallbacks (the
primary picker excludes offline/unreachable entries).

Live-reproduced: confirmed via `curl` against the running container that
`vision_model` in `data/settings.json` was `""` and a llama-server process
was actively serving `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF` on port 8000
(`-a ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`, confirming the alias fix from
BUG-2026-09-24T120000 item 1 is in effect); `/api/models` correctly listed
it as an online local entry, so the model *was* available to resolve, it
just was never tried.

**Fix:** `analyze_image_with_vl_result()` now resolves the primary model
(catching failure into `primary = None` instead of returning early) and
`resolve_vision_fallback_candidates()` *before* deciding whether to fail;
only returns `"[No vision model configured...]"` if the combined
`[primary] + fallbacks` list is empty after filtering. The per-candidate
try/fallback loop below is unchanged.

**verify:** `tests/test_vision_fallback_used_when_primary_unresolved.py`
(2 tests): a fallback-only configuration reaches and uses the fallback
model; an empty primary + empty fallback list still returns the
"no vision model configured" message. Full targeted suite
(`-k "cookbook or vision or document_processor"`) passes: 336 passed, 1
skipped.

**Not fixed / lower confidence:** the user's separate observation that
`Settings -> AI Defaults -> Vision`'s "Model" (primary) dropdown "only
includes online model[s]" could not be reproduced live — a fresh
`/api/models` call while the local server was running correctly listed it
as `category: "local"`, `offline` absent, and it passes `settings.js`'s
`_isVisionModel()` filter (only excludes audio/tts/embedding-style model
ids). Most likely explanation: the user opened/loaded the Vision settings
tab before the local model started serving, and the dropdown is only
populated once, on tab load, with no live refresh. If this recurs after a
full page reload while the model is actively serving, that would need a
separate fix (e.g. re-populating the primary Model select on the same
`_registerAiEndpointRefresh` hook the fallback widget already uses).

## 2. GGUF quant dropdown (Direct Download) — Chromium zoom bug, not stale layout

**Problem:** Screenshot from the user shows the `#cookbook-dl-gguf-quant`
native `<select>` popup still rendering broken after BUG-2026-09-24T120000
item 3's fix (opening on repo `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`): a
tiny, mispositioned popup with clipped/cut-off option text.

**Root cause, confirmed live:** the prior fix's theory (a stale
pre-mutation popup-height measurement, fixed by forcing a reflow via `void
dlGgufQuant.offsetHeight`) was wrong, and the fix itself was **never
visually verified** — its own bug doc says so explicitly ("native-select
popup rendering ... doesn't reliably show through headless Chrome
screenshots"). Reproduced live with Puppeteer (logged in as a real test
account against the running container, headless Brave) with the exact
model repo from the user's screenshot:
  - With `localStorage['odysseus-ui-scale'] = '125'` (the "Larger" text-size
    setting, which applies `zoom: 1.25` to `<html>` per `static/style.css:169`)
    set and the page reloaded: opening the select's native popup renders it
    detached from the control — positioned near the top of the viewport,
    clipped to a sliver, showing cut-off text (matches the user's
    screenshot exactly).
  - With ui-scale reset to 100% (no CSS `zoom`), the identical dropdown
    (same 8 options, same repo) opens correctly: full-size, correctly
    positioned directly under the control, all options readable.

This is a documented class of Chromium engine bug: CSS `zoom` on an
ancestor does not correctly propagate to native form-control popups
(`<select>`, and likely `<input type="color">`/`<input type="date">`),
so the popup's on-screen position/size is computed from the wrong zoom
factor. Unlike the zoom bugs already fixed elsewhere in this codebase
(`init.js`, `modalManager.js`, `windowResize.js`, `windowDrag.js`,
`cookbookServe.js`, `modalSnap.js` — see CLAUDE.md's "Chromium zoom
gotcha"), there is **no JS/CSS hook available**: a native `<select>`
popup is drawn by the browser/OS chrome, not by page code, so the usual
"divide by `window.innerWidth / document.documentElement.offsetWidth`"
fix pattern used for JS-positioned popups does not apply here.

**First pass this session:** removed the ineffective "last attempt" code
that didn't address the real bug — the `void dlGgufQuant.offsetHeight;`
forced-reflow line and its explanatory comment in `_scanGgufRepo()`
(`static/js/cookbook.js`), and its dedicated regression test
`tests/test_cookbook_gguf_quant_dropdown_reflow.py` (which only asserted
that line's presence, not any actual visual behavior).

**Real fix (user asked to continue rather than defer):** replaced the
native `<select>` with a custom (JS-positioned) dropdown, following the
same zoom-safe pattern already established elsewhere in this file
(`_showDepMenu()`) and codebase-wide (`modalManager.js`'s `_zoomRatio()`
convention — see CLAUDE.md's "Chromium zoom gotcha"). The `<select id=
"cookbook-dl-gguf-quant">` stays in the DOM, hidden (`display:none`), as
the sole state holder — every existing consumer of `.value`/`.options`/
`.dataset.repo` and its `'change'` listener is untouched. A new
`<button id="cookbook-dl-gguf-quant-trigger">` shows the current
selection and, on click, opens a `position:fixed` `<div class="dropdown">`
built from `dlGgufQuant.options`, positioned via
`window.innerWidth / document.documentElement.offsetWidth` (the same zoom
ratio helper used by `_showDepMenu`). Picking an item sets
`dlGgufQuant.selectedIndex`, calls `_syncGgufTriggerLabel()`, and
dispatches a real `'change'` event on the hidden select so downstream
logic (the download-trigger's `dlGgufQuant.value` reads, the note-text
listener) fires exactly as before.

**Live-verified with Puppeteer** (headless Brave, logged in as the test
account) with `localStorage['odysseus-ui-scale'] = '125'` set and the page
reloaded — the exact condition that broke the native select: menu opened
at the correct size (all 8 quant options, not clipped) and position
(`top: trigger.bottom + 4px`, `left: trigger.left`, matching exactly);
picking the 3rd item correctly set `select.value`/`selectedIndex`, synced
the trigger label, updated the note text, and closed the menu.

**verify:** `tests/test_cookbook_gguf_quant_custom_dropdown.py` (5 tests):
the select stays hidden rather than removed, the trigger button exists,
the menu-positioning function uses the established zoom-ratio convention,
picking an item drives the hidden select and dispatches `change`, and the
trigger label resyncs both when the "Scanning..." placeholder is set and
once real options land.

Only this one control was replaced — no other native `<select>`s in
Cookbook were confirmed broken under `ui-scale-125` this session, so none
were touched speculatively.

**Follow-up bug in the custom dropdown itself (found on user retest):**
clicking the trigger required two clicks — the first click re-triggered
"Scanning..." instead of opening the menu, the second click (after the
rescan finished) opened it correctly. Root cause: `#cookbook-dl-repo`
already had a `blur` listener (`dlInput.addEventListener('blur', () =>
_scanGgufRepo(dlInput.value))`) predating this fix, added as a safety-net
rescan for whenever focus left the repo field. Clicking the new trigger
button blurs that input as a side effect, so the SAME click that should
open the menu also fired this listener — and `_scanGgufRepo()` had no dedup
guard, so it unconditionally reset `dlGgufQuant.innerHTML` to a single
"Scanning..." placeholder synchronously (before the click handler even ran)
regardless of whether the repo had already been scanned. Fixed by adding an
early-return guard at the top of `_scanGgufRepo()`: if
`dlGgufQuant.dataset.repo === repo` and the select already holds real
(non-placeholder) options, skip the rescan entirely. Live-reproduced with
Puppeteer (single real click, checked 50ms later): the menu now opens
immediately with all 8 real options intact on the first click.

**verify:** `test_scan_skips_redundant_rescan_of_an_already_scanned_repo`
added to `tests/test_cookbook_gguf_quant_custom_dropdown.py` (6 tests
total for this control).

## 3. Follow-up: auto-set Settings > AI Defaults from every Cookbook serve

Requested by the user in the same follow-up: "Default Chat Model" should
always pick up whatever was just served via Cookbook, and "Vision Model"
should pick it up too whenever that serve loaded a multimodal projector.
Both were previously manual-only settings.

`_auto_register_llm_endpoint()` (`routes/cookbook_routes.py`) — the
function that registers every Cookbook-launched LLM as a `ModelEndpoint`,
already the hook point for probing `/v1/models` immediately after a serve —
now also calls a new `_auto_set_chat_defaults(endpoint_id)` helper on both
its update-existing-endpoint and create-new-endpoint return paths. It
unconditionally writes `default_endpoint_id`/`default_model = req.repo_id`
(an overwrite, not fill-only-if-empty, since serving a different model is
the more common case than wanting to keep an older default pinned), and
additionally writes `vision_model = req.repo_id` + `vision_enabled = True`
when the launch command shows `--mmproj`/`--clip_model_path` (llama.cpp's
vision-projector flags, added by Cookbook's Vision toggle).

This depends on the alias fix from BUG-2026-09-24T120000 item 1: without a
stable `-a`/`--model_alias`, the value this writes (`req.repo_id`) would
never match what the live-serving endpoint reports via `/v1/models`, and
`_resolve_model()`'s matching (used by both chat and vision resolution)
would silently fail regardless of this auto-set.

**verify:** `tests/test_cookbook_auto_set_chat_defaults.py` (3 tests,
source-level — `_auto_register_llm_endpoint`/`_auto_set_chat_defaults` are
closures nested inside `setup_cookbook_routes()`, not module-level
attributes, so a full functional test would need to mock tmux/SSH/process
launch through the whole `/api/model/serve` endpoint just to reach this one
side effect): the vision-detection regex matches Cookbook's actual launch
flags; the helper writes all four settings keys; it's called from both the
update-existing and create-new endpoint paths.

---

**Common verification:** Full local suite: 13 pre-existing unrelated
failures (same set reproduced on a clean baseline earlier this session),
6022 passed (+9 new tests across this doc's fixes), 3 skipped — zero
regressions. Deployed via `docker compose up -d --build odysseus`;
container started cleanly, all MCP servers reconnected.

**Status:** All three resolved and deployed — vision fallback chain, GGUF
quant dropdown (custom widget, live-verified under CSS zoom), and
auto-set chat/vision defaults on every Cookbook serve.

# BUG-2026-09-24T120000: Four Cookbook/document bugs from a user todo list

**Install method:** Docker

User reported four issues in one batch. Each is a separate root cause; grouped
here since they were investigated and fixed together in one session.

## 1. Vision breaks after re-serving a non-MTP build

**Problem:** Chat reported "[No vision model configured — set one in
Settings → Vision]" even with a vision-capable model actively serving and
selected in Settings.

**Root cause:** `_resolve_model()` (`src/ai_interaction.py`) matches a
saved `vision_model` setting against the live `id` field from the serving
endpoint's `/v1/models`. Cookbook's llama.cpp launch command
(`static/js/cookbook.js:_buildServeCmd`) never passed `-a/--alias` to
`llama-server`, so llama.cpp reports the raw `--model` file path as that
`id` — confirmed via llama.cpp's own docs/discussions
(github.com/ggml-org/llama.cpp/discussions/8547: without `-a`, the API
reports the full model path, not a stable name). Since Cookbook picks a
different GGUF file depending on quant/MTP/Vision toggle, that reported id
changes on nearly every re-serve, so a `vision_model` saved once against one
serve config silently stops matching after the next.

**Fix:** `static/js/cookbook.js:_buildServeCmd` now passes `-a "$repo_id"`
to native `llama-server` and `--model_alias "$repo_id"` to
`llama_cpp.server`, keyed off `modelName` (the repo id parameter), which is
constant across quant/MTP/vision selection — unlike the GGUF file path.

**verify:** `tests/test_cookbook_llama_alias_stable_model_id.py` (3 tests,
source-level regex checks against the generated command template literals,
following the existing `test_cookbook_cpu_only_serve.py` pattern since
`cookbook.js` pulls in browser globals and can't run under node).

## 2. Cookbook window sticks to the top after minimize → restore → resize → move

**Problem:** Minimizing Cookbook, restoring via its dock chip, and resizing
it worked, but a subsequent drag-to-reposition always snapped back near the
top of the viewport.

**Root cause:** Reproduced live with Puppeteer against the running
container (headless Brave at `/opt/brave-origin-bin/brave`, logged in as a
test account, driving real mouse events). `modalManager.js`'s
`_applyRestoreHeight()` sets `content.style.minHeight` on every
restore-from-minimize, to preserve the window's prior size. That min-height
was never cleared afterward. A subsequent user resize to something SMALLER
correctly set `content.style.height` to the new value, but the box kept
rendering at the old (larger) min-height — CSS `min-height` always wins over
a smaller `height`. The resize looked like it worked (both the DOM state
and any persisted size matched the new value) while the window didn't
visibly shrink, leaving almost no vertical room — so a following drag looked
"stuck near the top" since there was nowhere left to move it down into.
Confirmed with instrumented rect dumps at each step:
`after restore {height:940, styleMinHeight:"940px"}` →
`after bottom-edge resize {height:940 (unchanged!), styleHeight:"543px",
styleMinHeight:"940px"}` → drag afterward clamped to `top:60` regardless of
a 300px drag delta.

**Fix:** `static/js/windowResize.js`'s `begin()` now clears
`content.style.minHeight = ''` once a manual resize starts, since the user's
explicit resize is a stronger, more authoritative signal than the earlier
restore-height floor.

**verify:** `tests/test_window_resize_clears_stale_restore_minheight.py` (2
tests). Live Puppeteer re-run after the fix and rebuild confirmed: resize
now correctly shrinks (`height` matches `styleHeight`, `styleMinHeight`
cleared), and the following drag moved the full requested distance
(`top: 30 → 330` for a 300px drag, vs. clamping at `top: 60` before).

## 3. GGUF quant dropdown (Direct Download) shows half its options on first open

**Problem:** Opening the quant `<select>` right after a repo scan completes
shows only part of the option list; closing and reopening shows all of them
correctly.

**Root cause:** `_scanGgufRepo()` (`static/js/cookbook.js`) replaces the
`<select>`'s entire `<option>` list via one `.innerHTML` assignment once an
async HF scan resolves. This is a known Chromium quirk for native
`<select>` popups: without a forced reflow immediately after a DOM
mutation, the browser can still be holding a stale popup-height measurement
from before the mutation (taken while the select showed a single
"Scanning..." placeholder, or before the row was even `display:flex`) — so
the first native popup open after the mutation renders clipped to that
stale, smaller height, and only shows every option correctly once layout
has been recomputed in between (which the next open triggers).

**Fix:** Added `void dlGgufQuant.offsetHeight;` immediately after the
`.innerHTML` replacement, forcing a synchronous reflow before the user can
possibly open the popup.

**verify:** `tests/test_cookbook_gguf_quant_dropdown_reflow.py` (1 test,
source-level check that the reflow line sits between the innerHTML
replacement and the next interaction). Native-select popup rendering is
OS-level and doesn't reliably show through headless Chrome screenshots, so
this fix targets the documented Chromium quirk directly rather than a
visual repro.

## 4. MTP spec (and vLLM speculative token count) always reverts to 3

**Problem:** "MTP spec keeps changing itself to 3, even when saved as a
preset. When using the Vision On preset with no MTP spec, changing to
Vision Off makes MTP spec 3."

**Root cause:** `_redactServeStateForStorage()`
(`static/js/cookbookServe.js`), which strips credential-shaped keys
(`hf_token`, `api_key`, `password`, ...) before persisting a named preset or
the auto-saved per-repo serve state, used the regex
`/token|password|passwd|secret|api[_-]?key/i`. The bare `/token/i` clause
also matched the two speculative-decoding *count* field names in this
codebase — `spec_tokens` (vLLM) and `llama_spec_tokens` (llama.cpp MTP) —
since both literally contain the substring "token". Confirmed via a repo
grep: those are the *only* two `data-field` names anywhere in the serve
panel matching `/token/i`, and both are plural counts, not credentials.
Every persistence path (`_saveCurrentConfig`, the favorite-toggle re-save,
and the auto-persisted per-repo `SERVE_STATE_KEY`) routes through this same
redaction function, so whatever value the user set for either field was
silently deleted before it ever reached storage — it always came back as
the form's hardcoded `'3'` render-time default on the next load, regardless
of what was actually saved.

**Fix:** Regex changed to `/token(?!s)|password|passwd|secret|api[_-]?key/i`
— a negative lookahead so "token" still matches but "tokens" doesn't. Safe
because every real secret field in this codebase is singular (`hf_token`,
`api_token`, `access_token`), confirmed by grep, and both false-positive
fields are plural.

**verify:** `tests/test_cookbook_spec_tokens_redaction_false_positive.py`
(3 tests): the source uses the negative-lookahead pattern; the pattern
itself (mirrored in Python) does not match `llama_spec_tokens`/
`spec_tokens`; real credential-shaped keys are still matched.

---

**Common verification across all four:** Full local suite after all four
fixes: 13 pre-existing unrelated failures (same set reproduced on a clean
baseline earlier in this session), 6013 passed (+9 new tests), 3 skipped —
zero regressions. Deployed via `docker compose up -d --build odysseus`
after each fix, confirmed healthy.

**Status:** Resolved, deployed.

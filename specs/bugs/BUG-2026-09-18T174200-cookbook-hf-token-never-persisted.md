---
bug_id: BUG-2026-09-18T174200
status: resolved
severity: medium
priority: high
scope: cookbook-settings
title: Cookbook HuggingFace token is never actually sent to the backend, only held in page memory
---

# BUG-2026-09-18T174200: Cookbook HuggingFace token never persisted

## Problem

User reported: "in Cookbook > Settings tab, whenever Docker is restarted, huggingface token disappears."

## Root Cause

Not a Docker-restart-specific bug — the token was never actually saved server-side at all. In `static/js/cookbook.js`, the HF token input's `change` handler called `_persistEnvState()`, which (via `_saveTasks` → `_syncToServer()` in `static/js/cookbookRunning.js:1326`) always ran the payload through `_stripStateSecrets()` (`static/js/cookbookRunning.js:898-907`), which unconditionally deletes `env.hfToken` before every POST to `/api/cookbook/state`. That stripping is correct for the periodic debounced background sync (a legitimate reason to never echo secrets in that channel), but it meant the ONE path meant to actually save a newly typed token used the exact same stripped pipe — the token only ever lived in the in-memory `_envState.hfToken` for that page load and was never written to `data/cookbook_state.json`. Confirmed empirically: `data/cookbook_state.json`'s `env` object had no `hfToken` key at all despite the backend save/load/encrypt logic (`routes/cookbook_routes.py` `_state_for_storage`/`load_stored_hf_token`, `src/secret_storage.py`) being correct and `APP_KEY_FILE`/`COOKBOOK_STATE_FILE` both correctly persisted under `DATA_DIR` (`src/constants.py:30,32`).

## Fix

- Added `_syncHfTokenToServer(token)` in `static/js/cookbookRunning.js` (exported): builds the same full state shape `_syncToServer()` uses (so the backend's anti-wipe merge guard for `env.servers`/tasks behaves identically), runs it through `_stripStateSecrets()` for hygiene, then explicitly re-sets `payload.env.hfToken = token` and POSTs immediately (not debounced).
- Wired it into the HF token input's `change` handler in `static/js/cookbook.js`: calls `_syncHfTokenToServer(val)` first, then still calls `_persistEnvState()` for the rest of the local-state bookkeeping; sets an inline tooltip if the save failed so a network failure isn't silently invisible.

## Verification

- `node --check static/js/cookbookRunning.js static/js/cookbook.js` — passed.
- Manual review: the new function is the only path that includes `hfToken` in a POST to `/api/cookbook/state`; the generic debounced sync still never includes it, so background syncs still can't leak it.
- Live confirmation still needed: user should re-enter the HF token, confirm the green checkmark, then restart the container and reopen Cookbook Settings — `hfTokenConfigured` should read true and the masked value should show without re-entry.

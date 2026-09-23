# BUG-2026-09-23T160000: Cookbook treats a base GGUF and its -mtp sibling as one quant, breaking per-file delete and download

**Install method:** Docker

## Problem

Found while debugging why deleting a single GGUF quant (`IQ3_S`) through the
Cookbook UI left the file on disk. Two compounding bugs, both rooted in the
same quant-name extraction not accounting for the `-mtp` (speculative-decoding
draft head) filename suffix used by GGUF releases like
`ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`:

1. **Quant-label collision.** Both `gguf_quant()` in
   `routes/cookbook_helpers.py` (backend cached-model scan) and
   `_ggufQuantFromPath()` in `static/js/cookbook.js` (download-picker scan)
   stopped matching at the `IQ[0-9]_[A-Z0-9_]+` underscore run and never
   captured a trailing `-mtp`. `Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf` and
   `Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf` both resolved to the same quant
   string `IQ3_S`. Effects: the delete dialog
   (`_ggufDeleteChoice` in `static/js/cookbookServe.js`) showed two
   checkboxes both labeled `IQ3_S ...`, easy to miss there were two files;
   the download picker's `_ggufIncludeForQuant()` built one glob
   (`*IQ3_S*.gguf`) for both files, so selecting "IQ3_S" silently downloaded
   both.
2. **Missing `/snapshots` segment on per-file delete.** Independent of (1):
   even after selecting the correct file(s) in the delete dialog,
   `_deleteCachedModel()` built the on-disk target as
   `<cache>/models--org--repo/<rel_path>`. But `rel_path` for HF-cache
   models (from `collect_ggufs()` in `routes/cookbook_helpers.py`, called as
   `for f in collect_ggufs(sf): f['rel_path'] = sd + '/' + f['rel_path']`)
   is relative to the *snapshot* dir, i.e. the real path is
   `<cache>/models--org--repo/snapshots/<hash>/<rel_path>`. The per-file
   `rm -f`/`Remove-Item` command was missing the `/snapshots` segment, so it
   silently targeted a path that never existed and the file stayed on disk
   with no error surfaced to the user. This is why "delete IQ3_S" appeared
   to succeed in the UI but the file (and, compounded with bug 1, its `-mtp`
   sibling) both persisted.

## Expected behavior

Selecting one GGUF quant in the delete dialog or the download picker acts on
exactly that file; a base quant and its `-mtp` variant are addressable and
deletable independently.

## Actual behavior

A base/`-mtp` pair collapsed into one ambiguous quant label everywhere, and
even a correctly-targeted single-file delete silently no-op'd due to the
missing snapshot-dir segment.

## Fix

- `routes/cookbook_helpers.py:426` — `gguf_quant()` regex extended with an
  optional `(-mtp)?` capture, included in the uppercased return value
  (display-only field, no downstream glob dependency, safe to uppercase in
  full).
- `static/js/cookbook.js` — `_ggufQuantFromPath()` given the same capture,
  but the `-mtp` suffix is kept lowercase (not uppercased) since this value
  feeds directly into `_ggufIncludeForQuant()`'s literal download glob and
  must match the real (lowercase) filename on HuggingFace.
  `_ggufIncludeForQuant()` itself was changed from a blanket
  `*${quant}*.gguf` (which still substring-matched a sibling `-mtp` file
  even after distinct quant keys existed) to anchor against each matched
  file's actual trailing shape: `*${quant}.gguf` when no match needs a
  wildcard tail, `*${quant}*.gguf` only when a genuine split/multi-part file
  (`-00001-of-00002.gguf`) is present in that quant's matches.
- `static/js/cookbookServe.js` — `_deleteCachedModel()` now derives a
  separate `filesTarget = (m && !m.is_local_dir) ? \`${target}/snapshots\` :
  target` and uses it (not the bare `target`) for every per-file delete
  path, on both the Windows (`winFilesTarget`) and Unix
  (`unixFilesTarget`) command-building branches. Whole-repo deletes
  (`rm -rf`/`Remove-Item -Recurse`) are unaffected since they never append
  `rel_path` and already target the correct `models--org--repo` dir
  directly.

Model grouping in the Launch tab is unaffected by either fix: `gguf_quant()`
only changes a per-file label inside one model card's `gguf_files` array;
the model card itself is still keyed by `repo_id`, so a base quant and its
`-mtp` sibling remain grouped under one Launch-tab entry with a GGUF File
dropdown, as intended.

**verify**:
- `tests/test_cookbook_gguf_quant_mtp_suffix.py` — 2 tests, execute the real
  generated scan script (`_cached_model_scan_script`) against a fixture
  HF-cache directory, confirming distinct quant labels and that a plain
  (non-`-mtp`) quant is unaffected. All passing.
- `tests/test_cookbook_gguf_delete_snapshots_path.py` — 4 source-level
  regression tests confirming the `/snapshots` segment is present on both
  delete command branches and absent from the (correctly unaffected)
  whole-repo delete path. All passing.
- Node-level manual verification (this session, not persisted as a test):
  regex output for 6 filename cases, and glob-match simulation confirming
  each quant's include pattern matches only its own file(s) while a
  multi-part split file still gets its wildcard tail.
- Full local suite: 13 pre-existing unrelated failures (same set reproduced
  on the clean baseline earlier this session), 6003 passed, 3 skipped —
  zero regressions.
- Live confirmation from the user (paraphrased): "deleting separate
  versions of model works now."

**Status:** Resolved, deployed, verified by the user in production.

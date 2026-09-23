"""Regression: Cookbook's per-file GGUF delete built its rm/Remove-Item target
from `<models--org--repo>/<rel_path>`, but for HF-cache models `rel_path`
(from collect_ggufs in routes/cookbook_helpers.py: `f['rel_path'] = sd + '/'
+ f['rel_path']`) is relative to the snapshot dir, i.e.
`<models--org--repo>/snapshots/<hash>/<file>` -- the delete command was
missing the `/snapshots` segment, so single-file deletes silently targeted a
path that didn't exist and left the file on disk (the whole-repo `rm -rf`
path was unaffected since it never appends rel_path).

Fix: static/js/cookbookServe.js's _deleteCachedModel now derives a separate
`filesTarget` (= `${target}/snapshots` for HF-cache models, unchanged for
local-dir models where collect_ggufs is called directly on the model dir
with no snapshot indirection) and uses it for every per-file delete target,
on both the Windows and Unix command-building branches.
"""

from pathlib import Path

SERVE = (Path(__file__).resolve().parent.parent / "static/js/cookbookServe.js").read_text(encoding="utf-8")


def test_files_target_adds_snapshots_segment_only_for_hf_cache_models():
    assert "const filesTarget = (m && !m.is_local_dir) ? `${target}/snapshots` : target;" in SERVE


def test_windows_per_file_delete_uses_files_target_not_bare_target():
    assert "const winFilesTarget = filesTarget.startsWith('~')" in SERVE
    assert ".map(rel => `${winFilesTarget}\\\\${rel.replace(/\\//g, '\\\\')}`);" in SERVE
    # The old bug: building the per-file Windows path from winTarget (missing
    # /snapshots) instead of winFilesTarget.
    assert ".map(rel => `${winTarget}\\\\${rel.replace(/\\//g, '\\\\')}`);" not in SERVE


def test_unix_per_file_delete_uses_files_target_not_bare_target():
    assert "const unixFilesTarget = filesTarget.startsWith('~') ? filesTarget.replace(/^~/, '$HOME') : filesTarget;" in SERVE
    assert ".map(rel => `${filesTarget.replace(/\\/+$/, '')}/${rel}`);" in SERVE
    assert "find ${_shellPathExpr(unixFilesTarget)} -type d -empty -delete" in SERVE
    # The old bug: building the per-file rm target from target (missing
    # /snapshots) instead of filesTarget.
    assert ".map(rel => `${target.replace(/\\/+$/, '')}/${rel}`);" not in SERVE


def test_whole_repo_delete_still_uses_bare_target_unaffected():
    """Whole-repo rm -rf targets the models--org--repo dir directly, not a
    per-file rel_path, so it must keep using target/unixTarget/winTarget,
    not the snapshots-suffixed filesTarget."""
    assert 'cmd = `rm -rf "${unixTarget}"`;' in SERVE
    assert "Remove-Item -Recurse -Force ${_psSingleQuote(winTarget)}" in SERVE

"""Regression: gguf_quant() in the generated cached-model scan script
(routes/cookbook_helpers.py:_cached_model_scan_script) collapsed a base GGUF
and its -mtp speculative-decoding sibling into the same quant string, since
its regex stopped at the underscore run and never captured the trailing
"-mtp". That made Cookbook's delete-selection dialog show both files under
an identical-looking "IQ3_S" label (easy to miss there were two), and made
static/js/cookbook.js's download-picker silently pull both files when the
user selected one quant, since its glob (*IQ3_S*.gguf) matches "IQ3_S-mtp"
as a substring too.

Fix: both gguf_quant() here and static/js/cookbook.js's
_ggufQuantFromPath()/_ggufIncludeForQuant() now treat "-mtp" as part of the
quant identity, so the two files get distinct quant keys and distinct,
non-overlapping download globs.
"""

import json
import subprocess
import sys
from pathlib import Path

from routes.cookbook_helpers import _cached_model_scan_script


def _run_scan(hf_cache_dir: Path) -> list[dict]:
    script = _cached_model_scan_script(add_hf_cache=str(hf_cache_dir))
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _make_gguf_repo(base: Path, repo_id: str, filenames: list[str]) -> None:
    snap = base / f"models--{repo_id.replace('/', '--')}" / "snapshots" / "abc123"
    snap.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (snap / name).write_bytes(b"\x00" * 16)


def test_base_and_mtp_gguf_get_distinct_quant_labels(tmp_path):
    _make_gguf_repo(
        tmp_path, "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF",
        ["Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf", "Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf"],
    )
    models = _run_scan(tmp_path)
    model = next(m for m in models if m["repo_id"] == "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF")
    quants = {f["name"]: f["quant"] for f in model["gguf_files"]}

    assert quants["Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf"] == "IQ3_S"
    assert quants["Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf"] == "IQ3_S-MTP"
    assert quants["Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf"] != quants["Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf"]


def test_plain_quant_without_mtp_sibling_is_unaffected(tmp_path):
    _make_gguf_repo(tmp_path, "org/model", ["model-Q4_K_M.gguf"])
    models = _run_scan(tmp_path)
    model = next(m for m in models if m["repo_id"] == "org/model")
    assert model["gguf_files"][0]["quant"] == "Q4_K_M"

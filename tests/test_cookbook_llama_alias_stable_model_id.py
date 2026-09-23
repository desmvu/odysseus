"""Regression guard: llama-server's /v1/models id must stay stable across re-serves.

Without ``-a/--alias``, llama-server reports the raw ``--model`` path as the
OAI-compatible model "id". Cookbook re-serves the same repo picking a
different GGUF file (different quant, MTP on/off, Vision on/off all select a
different file), so that path changes on nearly every re-serve. A setting
like Settings -> Vision's saved model name then silently stops resolving,
since ``_resolve_model`` matches against the live /v1/models id — this
surfaced as "no vision model configured" even with a vision model running.

The fix pins a stable alias (the repo id, independent of which specific GGUF
file/quant/MTP/vision config is active) via ``-a`` (native llama-server) and
``--model_alias`` (llama-cpp-python), so the reported id no longer moves
under a saved setting.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "static/js/cookbook.js"


def test_native_llama_server_command_sets_a_stable_alias():
    text = SRC.read_text(encoding="utf-8")
    assert "const _llamaAlias = _shellQuote(modelName);" in text
    lc_server_match = re.search(r"const _lcServer = `([^`]+)`;", text)
    assert lc_server_match, "expected a _lcServer template literal"
    assert "-a ${_llamaAlias}" in lc_server_match.group(1)


def test_llama_cpp_python_server_command_sets_a_stable_alias():
    text = SRC.read_text(encoding="utf-8")
    lcp_server_match = re.search(r"const _lcpServer = `([^`]+)`;", text)
    assert lcp_server_match, "expected a _lcpServer template literal"
    assert "--model_alias ${_llamaAlias}" in lcp_server_match.group(1)


def test_alias_is_derived_from_the_repo_id_not_the_gguf_file_path():
    text = SRC.read_text(encoding="utf-8")
    # modelName is the function's repo-id parameter, distinct from
    # ggufPath/_gguf_path (the specific quant file, which changes per
    # quant/MTP/vision selection) — the alias must track the former.
    assert "export function _buildServeCmd(f, modelName, backend)" in text
    assert "const _llamaAlias = _shellQuote(modelName);" in text

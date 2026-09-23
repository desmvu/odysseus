import base64
from pathlib import Path

from src import document_processor as dp


def _tiny_png(path):
    # 1x1 transparent PNG
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    Path(path).write_bytes(data)


def test_fallback_model_used_when_primary_vision_model_unresolved(monkeypatch, tmp_path):
    """A vision_model_fallbacks entry must still work when the primary
    `vision_model` setting is empty/unresolvable — previously the function
    returned the "no vision model configured" error before ever consulting
    the fallback chain (see src/document_processor.py analyze_image_with_vl_result)."""
    monkeypatch.setattr(
        dp, "_load_vl_settings",
        lambda: {"vision_enabled": True, "vision_model": ""},
    )
    monkeypatch.setattr(
        dp, "_resolve_vl_model",
        lambda configured, owner=None: (_ for _ in ()).throw(ValueError("no primary")),
    )

    calls = {}

    def fake_resolve_vision_fallback_candidates(owner=None):
        return [("http://localhost:8000/v1/chat/completions", "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF", {})]

    monkeypatch.setattr(
        "src.endpoint_resolver.resolve_vision_fallback_candidates",
        fake_resolve_vision_fallback_candidates,
    )

    def fake_llm_call(url, model, messages, headers=None, timeout=None):
        calls["url"] = url
        calls["model"] = model
        return "a tiny transparent pixel"

    monkeypatch.setattr(dp, "llm_call", fake_llm_call)

    img_path = tmp_path / "test.png"
    _tiny_png(img_path)

    result = dp.analyze_image_with_vl_result(str(img_path), owner="alice")

    assert result["text"] == "a tiny transparent pixel"
    assert result["model"] == "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF"
    assert calls["model"] == "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF"


def test_no_vision_model_error_when_primary_and_fallbacks_both_unresolved(monkeypatch, tmp_path):
    monkeypatch.setattr(
        dp, "_load_vl_settings",
        lambda: {"vision_enabled": True, "vision_model": ""},
    )
    monkeypatch.setattr(
        dp, "_resolve_vl_model",
        lambda configured, owner=None: (_ for _ in ()).throw(ValueError("no primary")),
    )
    monkeypatch.setattr(
        "src.endpoint_resolver.resolve_vision_fallback_candidates",
        lambda owner=None: [],
    )

    img_path = tmp_path / "test.png"
    _tiny_png(img_path)

    result = dp.analyze_image_with_vl_result(str(img_path), owner="alice")

    assert result["text"] == "[No vision model configured — set one in Settings → Vision]"

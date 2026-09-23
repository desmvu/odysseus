"""Regression guard: every Cookbook LLM serve should auto-set chat defaults.

Requested by the user: Settings > AI Defaults' "Default Chat Model" should
always pick up whatever model was just served via Cookbook, and "Vision
Model" should pick it up too whenever that serve loaded a multimodal
projector (--mmproj / --clip_model_path). Previously these were manual-only
settings the user had to go set themselves after every serve.

_auto_register_llm_endpoint / _auto_set_chat_defaults are closures nested
inside setup_cookbook_routes() (not module-level attributes), and a full
functional test would need to mock tmux/SSH/process launch through the
whole /api/model/serve endpoint just to reach this one side effect. Source-
level checks confirm the wiring directly, matching the pattern already used
for other cookbook.js logic that can't run outside a browser.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "routes/cookbook_routes.py"


def _auto_register_fn_body(text: str) -> str:
    start = text.index("def _auto_register_llm_endpoint(")
    end = text.index("\n    @router.post(\"/api/model/serve\")")
    assert start < end
    return text[start:end]


def test_vision_detection_matches_the_actual_cookbook_launch_flags():
    text = SRC.read_text(encoding="utf-8")
    body = _auto_register_fn_body(text)
    assert 'r"--mmproj\\b|--clip_model_path\\b"' in body


def test_auto_set_chat_defaults_helper_writes_default_and_vision_settings():
    text = SRC.read_text(encoding="utf-8")
    body = _auto_register_fn_body(text)
    helper_start = body.index("def _auto_set_chat_defaults(endpoint_id: str)")
    helper = body[helper_start:]
    assert 'settings["default_endpoint_id"] = endpoint_id' in helper
    assert 'settings["default_model"] = req.repo_id or ""' in helper
    assert "if is_vision_endpoint:" in helper
    assert 'settings["vision_model"] = req.repo_id or ""' in helper
    assert 'settings["vision_enabled"] = True' in helper
    assert "save_settings(settings)" in helper


def test_auto_set_chat_defaults_is_called_from_both_register_paths():
    text = SRC.read_text(encoding="utf-8")
    body = _auto_register_fn_body(text)
    calls = list(re.finditer(r"_auto_set_chat_defaults\((existing\.id|ep_id)\)", body))
    called_args = {m.group(1) for m in calls}
    assert called_args == {"existing.id", "ep_id"}, (
        "expected _auto_set_chat_defaults to be called with existing.id on "
        "the update-existing-endpoint path AND ep_id on the "
        "create-new-endpoint path"
    )

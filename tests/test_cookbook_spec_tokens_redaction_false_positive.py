"""Regression guard: saving MTP/speculative token counts must survive a save/reload.

_redactServeStateForStorage() (static/js/cookbookServe.js) strips any field
whose *name* matches /token|password|passwd|secret|api[_-]?key/i before
persisting a named preset or the auto-saved per-repo serve state -- meant to
keep credentials (hf_token, api_key, ...) out of localStorage. The bare
/token/i match also caught the two speculative-decoding field names,
spec_tokens (vLLM) and llama_spec_tokens (llama.cpp MTP) -- a count of draft
tokens, not a credential -- and silently deleted them on every save. Since
every persistence path (named presets AND the auto-persisted per-repo state)
goes through this same function, whatever the user set there could never
survive a save/reload: it always came back as the form's hardcoded '3'
default on next render, which is what surfaced as "MTP spec keeps changing
itself to 3, even when saved as a preset."

Fixed with a negative lookahead: /token(?!s)/i matches "token" but not
"tokens", which is sufficient since every real secret field in this codebase
is singular (hf_token, api_token, access_token) and both false-positive
fields are plural (spec_tokens, llama_spec_tokens).
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "static/js/cookbookServe.js"

REDACT_PATTERN = re.compile(r"token(?!s)|password|passwd|secret|api[_-]?key", re.IGNORECASE)


def test_redaction_regex_source_uses_the_negative_lookahead():
    text = SRC.read_text(encoding="utf-8")
    assert "/token(?!s)|password|passwd|secret|api[_-]?key/i" in text


def test_spec_token_count_fields_are_not_redacted():
    assert REDACT_PATTERN.search("llama_spec_tokens") is None
    assert REDACT_PATTERN.search("spec_tokens") is None


def test_real_credential_fields_are_still_redacted():
    for key in ["hf_token", "api_token", "access_token", "password", "api_key", "secret"]:
        assert REDACT_PATTERN.search(key) is not None, f"{key} should still be redacted"

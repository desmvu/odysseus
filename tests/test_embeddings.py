"""Tests for embeddings.py"""
import sys
import types
from unittest.mock import MagicMock, patch

import src.embeddings as embeddings
from src.embeddings import EmbeddingClient


def test_local_fastembed_explicitly_uses_cpu_provider(tmp_path, monkeypatch):
    calls = []
    fastembed = types.ModuleType("fastembed")

    class TextEmbedding:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fastembed.TextEmbedding = TextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", fastembed)
    monkeypatch.setattr(embeddings, "FASTEMBED_CACHE_DIR", str(tmp_path))

    embeddings.FastEmbedClient(model="test-model")

    assert calls == [{
        "model_name": "test-model",
        "cache_dir": str(tmp_path),
        "cuda": False,
    }]


class TestEmbeddingClient:
    _MOCK_RESPONSE = {
        "data": [{"embedding": [0.1], "index": 0}],
    }

    def _make_mock_resp(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = self._MOCK_RESPONSE
        resp.raise_for_status = MagicMock()
        return resp

    @patch("src.embeddings.httpx.Client")
    def test_bearer_header_sent_when_api_key_set(self, mock_httpx):
        """
        Test that the EmbeddingClient sends the Authorization header with the correct value when api_key is set.
        """
        mock_httpx.return_value.post.return_value = self._make_mock_resp()

        client = EmbeddingClient(
            url="http://test:11434/v1/embeddings",
            model="all-minilm:l6-v2",
            api_key="secret-key",
        )
        client.encode(["x"])

        headers = mock_httpx.return_value.post.call_args.kwargs["headers"]
        assert headers.get("Authorization") == "Bearer secret-key"

    @patch("src.embeddings.httpx.Client")
    def test_no_bearer_header_when_api_key_none(self, mock_httpx):
        """
        Test that the EmbeddingClient does not send the Authorization header when api_key is None.
        """
        mock_httpx.return_value.post.return_value = self._make_mock_resp()

        client = EmbeddingClient(url="http://test:11434/v1/embeddings")
        client.encode(["x"])

        headers = mock_httpx.return_value.post.call_args.kwargs["headers"]
        assert "Authorization" not in headers

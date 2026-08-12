"""Regression tests for the reranker fallback not mutating the caller's documents.

When a rerank call fails and the reranker falls back to the original order, it
must NOT write ``doc["rerank_score"] = 0.0`` into the caller's document dicts
(polluting the original data). The returned result docs carry the score; the
input docs must be left untouched.

Covers: SiliconFlow, HuggingFace, SentenceTransformer, Cohere, ZeroEntropy.
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mem0.configs.rerankers.cohere import CohereRerankerConfig
from mem0.configs.rerankers.zero_entropy import ZeroEntropyRerankerConfig


def _docs(n):
    return [{"memory": f"doc{i}"} for i in range(n)]


def _assert_no_pollution(original_docs, result):
    """The caller's dicts keep no rerank_score; result docs carry 0.0."""
    assert all("rerank_score" not in doc for doc in original_docs), "input documents were mutated"
    assert all(doc.get("rerank_score") == 0.0 for doc in result)
    # Result docs must be distinct objects from the inputs.
    assert all(result[i] is not original_docs[i] for i in range(len(result)))


@pytest.fixture
def mock_cohere(monkeypatch):
    fake_cohere = ModuleType("cohere")
    fake_client = MagicMock()
    fake_cohere.Client = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "cohere", fake_cohere)

    import mem0.reranker.cohere_reranker as module

    monkeypatch.setattr(module, "cohere", fake_cohere, raising=False)
    monkeypatch.setattr(module, "COHERE_AVAILABLE", True, raising=False)
    return module, fake_client


@pytest.fixture
def mock_zero_entropy(monkeypatch):
    fake_module = ModuleType("zeroentropy")
    fake_client = MagicMock()
    fake_module.ZeroEntropy = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "zeroentropy", fake_module)

    import mem0.reranker.zero_entropy_reranker as module

    monkeypatch.setattr(module, "ZeroEntropy", fake_module.ZeroEntropy, raising=False)
    monkeypatch.setattr(module, "ZERO_ENTROPY_AVAILABLE", True, raising=False)
    return module, fake_client


class TestCohereFallbackNoMutation:
    def test_fallback_does_not_pollute_input(self, mock_cohere):
        module, fake_client = mock_cohere
        fake_client.rerank.side_effect = RuntimeError("API error")

        reranker = module.CohereReranker(CohereRerankerConfig(api_key="test-key"))
        original = _docs(5)
        result = reranker.rerank("query", original)

        _assert_no_pollution(original, result)

    def test_fallback_pollutes_all_returned_docs(self, mock_cohere):
        module, fake_client = mock_cohere
        fake_client.rerank.side_effect = RuntimeError("API error")

        reranker = module.CohereReranker(CohereRerankerConfig(api_key="test-key", top_k=3))
        original = _docs(5)
        result = reranker.rerank("query", original)

        _assert_no_pollution(original, result)
        assert len(result) == 3


class TestZeroEntropyFallbackNoMutation:
    def test_fallback_does_not_pollute_input(self, mock_zero_entropy):
        module, fake_client = mock_zero_entropy
        fake_client.models.rerank.side_effect = RuntimeError("API error")

        reranker = module.ZeroEntropyReranker(ZeroEntropyRerankerConfig(api_key="test-key"))
        original = _docs(5)
        result = reranker.rerank("query", original)

        _assert_no_pollution(original, result)


class TestHuggingFaceFallbackNoMutation:
    def _make_reranker(self):
        import mem0.reranker.huggingface_reranker as module

        reranker = module.HuggingFaceReranker.__new__(module.HuggingFaceReranker)
        reranker.config = SimpleNamespace(batch_size=32, max_length=512, normalize=True, top_k=None)
        reranker.device = "cpu"
        reranker.tokenizer = MagicMock(side_effect=RuntimeError("model error"))
        reranker.model = MagicMock()
        return reranker

    def test_fallback_does_not_pollute_input(self):
        reranker = self._make_reranker()
        original = _docs(5)
        result = reranker.rerank("query", original)

        _assert_no_pollution(original, result)

    def test_fallback_respects_top_k(self):
        reranker = self._make_reranker()
        original = _docs(5)
        result = reranker.rerank("query", original, top_k=2)

        _assert_no_pollution(original, result)
        assert len(result) == 2


class TestSentenceTransformerFallbackNoMutation:
    def _make_reranker(self):
        import mem0.reranker.sentence_transformer_reranker as module

        reranker = module.SentenceTransformerReranker.__new__(module.SentenceTransformerReranker)
        reranker.config = SimpleNamespace(batch_size=32, show_progress_bar=False, top_k=None)
        reranker.model = MagicMock()
        reranker.model.predict.side_effect = RuntimeError("model error")
        return reranker

    def test_fallback_does_not_pollute_input(self):
        reranker = self._make_reranker()
        original = _docs(5)
        result = reranker.rerank("query", original)

        _assert_no_pollution(original, result)


class TestSiliconFlowFallbackNoMutation:
    def _make_reranker(self, monkeypatch):
        import mem0.reranker.siliconflow_reranker as module

        reranker = module.SiliconFlowReranker.__new__(module.SiliconFlowReranker)
        reranker.config = SimpleNamespace(
            api_key="test-key", model="test-model", top_k=None,
            return_documents=False, max_chunks_per_doc=None,
        )
        reranker.model = "test-model"
        reranker._client = MagicMock()
        reranker._request_delay = 0.0
        reranker._max_retries = 3
        reranker._query_max_chars = 6000
        reranker._docs_max_chars = 6000
        monkeypatch.setattr(module, "logger", MagicMock())
        return reranker

    def test_fallback_does_not_pollute_input(self, monkeypatch):
        reranker = self._make_reranker(monkeypatch)

        def boom(payload):
            raise RuntimeError("network error")

        monkeypatch.setattr(reranker, "_post_rerank", boom)
        original = _docs(5)
        result = reranker.rerank("query", original)

        assert all("rerank_score" not in doc for doc in original), "input documents were mutated"
        assert all(doc.get("rerank_score") == 0.0 for doc in result)

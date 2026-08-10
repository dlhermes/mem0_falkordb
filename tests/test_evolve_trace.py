"""Tests for the RECALL funnel trace (T6a): trace_stats collection in
score_and_rank and the search(trace=True) "trace" key.

Scoring tests exercise score_and_rank directly with a trace_stats dict and
verify the threshold/decay/topk transition counts land in it. Search tests
build a real Memory (mocked embedder/vector store/llm, mirroring
tests/memory/test_main.py) and pin the vector-only "standard" depth so the
funnel counts are deterministic. Both the sync and async paths are covered.
"""

import inspect
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")
os.environ["MEM0_SEARCH_DEPTH_AUTO"] = "false"

from mem0.memory.main import AsyncMemory, Memory  # noqa: E402

_RESULTS = [
    SimpleNamespace(id="m1", score=0.9, payload={"data": "like hiking"}),
    SimpleNamespace(id="m2", score=0.6, payload={"data": "prefers tea"}),
    SimpleNamespace(id="m3", score=0.05, payload={"data": "below threshold"}),
]


def _build_memory(mocker, cls):
    mock_embedder = mocker.MagicMock()
    mock_embedder.return_value.embed.return_value = [0.1, 0.2, 0.3]
    mocker.patch("mem0.utils.factory.EmbedderFactory.create", mock_embedder)

    mock_vector_store = mocker.MagicMock()
    mock_vector_store.return_value.search.return_value = _RESULTS
    mock_vector_store.return_value.keyword_search.return_value = []

    def _create(*args, **kwargs):
        if not hasattr(_create, "first"):
            _create.first = mock_vector_store.return_value
            return _create.first
        return mocker.MagicMock()

    mocker.patch("mem0.utils.factory.VectorStoreFactory.create", side_effect=_create)
    mocker.patch("mem0.utils.factory.LlmFactory.create", mocker.MagicMock())
    mocker.patch("mem0.memory.storage.SQLiteManager", mocker.MagicMock())

    return cls()


@pytest.fixture
def memory(mocker):
    return _build_memory(mocker, Memory)


@pytest.fixture
def async_memory(mocker):
    return _build_memory(mocker, AsyncMemory)


class TestScoreAndRankTraceStats:
    def test_trace_stats_records_threshold_decay_topk_counts(self):
        from mem0.utils.scoring import score_and_rank

        trace_stats = {}
        results = [
            {"id": "a", "score": 0.9, "payload": {"data": "mem a"}},
            {"id": "b", "score": 0.6, "payload": {"data": "mem b"}},
            {"id": "c", "score": 0.02, "payload": {"data": "mem c"}},
        ]
        ranked = score_and_rank(
            results, {}, {}, threshold=0.1, top_k=1, decay_fn=lambda payload: 0.5, trace_stats=trace_stats
        )

        assert trace_stats["before_threshold"] == 3
        assert trace_stats["after_threshold"] == 2
        assert trace_stats["after_decay"] == 2
        assert trace_stats["before_topk"] == 2
        assert trace_stats["after_topk"] == 1
        assert [r["id"] for r in ranked] == ["a"]

    def test_trace_stats_includes_latencies(self):
        from mem0.utils.scoring import score_and_rank

        trace_stats = {}
        results = [
            {"id": "a", "score": 0.9, "payload": {"data": "mem a"}},
            {"id": "b", "score": 0.6, "payload": {"data": "mem b"}},
        ]
        score_and_rank(results, {}, {}, threshold=0.1, top_k=10, decay_fn=lambda payload: 0.5, trace_stats=trace_stats)

        assert trace_stats["threshold_latency_ms"] >= 0
        assert trace_stats["decay_latency_ms"] >= 0
        assert trace_stats["scoring_latency_ms"] >= 0

    def test_no_trace_stats_returns_identical_results(self):
        from mem0.utils.scoring import score_and_rank

        results = [
            {"id": "a", "score": 0.9, "payload": {"data": "mem a"}},
            {"id": "b", "score": 0.6, "payload": {"data": "mem b"}},
        ]
        base = score_and_rank(results, {}, {}, threshold=0.1, top_k=10)
        assert [r["id"] for r in base] == ["a", "b"]


class TestSearchTrace:
    def test_default_search_has_no_trace_field(self, memory):
        result = memory.search("hiking", filters={"user_id": "u1"}, depth="standard")
        assert "trace" not in result
        assert set(result.keys()) == {"results"}
        assert len(result["results"]) == 2
        assert set(result["results"][0].keys()) >= {"id", "memory", "score"}

    def test_trace_true_shape_and_counts(self, memory):
        result = memory.search("hiking", filters={"user_id": "u1"}, depth="standard", trace=True)

        assert "trace" in result
        trace = result["trace"]
        assert trace["depth"] == "standard"

        stages = {s["stage"]: s for s in trace["stages"]}
        assert set(stages.keys()) == {"candidates", "threshold", "decay", "graph", "rerank", "final"}
        for stage in trace["stages"]:
            assert set(stage.keys()) == {"stage", "count", "latency_ms"}
            assert stage["latency_ms"] >= 0

        assert stages["candidates"]["count"] == 3
        assert stages["threshold"]["count"] == 2
        assert stages["decay"]["count"] == 2
        assert stages["graph"]["count"] == 2
        assert stages["rerank"]["count"] == 2
        assert stages["final"]["count"] == 2

    def test_minimal_depth_trace(self, memory):
        with_trace = memory.search("x", filters={"user_id": "u1"}, depth="minimal", trace=True)
        assert with_trace == {
            "results": [],
            "trace": {
                "depth": "minimal",
                "stages": [
                    {"stage": "candidates", "count": 0, "latency_ms": 0.0},
                    {"stage": "threshold", "count": 0, "latency_ms": 0.0},
                    {"stage": "decay", "count": 0, "latency_ms": 0.0},
                    {"stage": "graph", "count": 0, "latency_ms": 0.0},
                    {"stage": "rerank", "count": 0, "latency_ms": 0.0},
                    {"stage": "final", "count": 0, "latency_ms": 0.0},
                ],
            },
        }
        without_trace = memory.search("x", filters={"user_id": "u1"}, depth="minimal")
        assert without_trace == {"results": []}


class TestAsyncSearchTrace:
    @pytest.mark.asyncio
    async def test_async_search_trace(self, async_memory):
        result = await async_memory.search("hiking", filters={"user_id": "u1"}, depth="standard", trace=True)

        assert "trace" in result
        stages = {s["stage"]: s for s in result["trace"]["stages"]}
        assert result["trace"]["depth"] == "standard"
        assert stages["candidates"]["count"] == 3
        assert stages["threshold"]["count"] == 2
        assert stages["final"]["count"] == 2

    @pytest.mark.asyncio
    async def test_async_search_default_no_trace(self, async_memory):
        result = await async_memory.search("hiking", filters={"user_id": "u1"}, depth="standard")
        assert "trace" not in result

    def test_both_search_signatures_expose_trace_param(self):
        assert inspect.signature(Memory.search).parameters["trace"].default is False
        assert inspect.signature(AsyncMemory.search).parameters["trace"].default is False

"""Type-filtered searches must skip the graph-recall synthetic entries.

Graph recall synthesizes "src 关系 dst" fragments with random uuids that carry
no payload/metadata/memory_type. When the user filters by memory_type, those
synthetic entries must not appear. Plain searches (no memory_type filter) keep
graph recall unchanged (zero behavior change).

Mock style mirrors tests/memory/test_temporal_voice.py.
"""

import concurrent.futures
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from mem0.memory import main as memory_main
from mem0.memory.main import AsyncMemory, Memory

_GRAPH_ROW = {
    "source": "发哥",
    "relationship": "偏好",
    "destination": "龙井茶",
    "relation_cn": "偏好",
}


def _sync_memory():
    memory = Memory.__new__(Memory)
    memory.config = SimpleNamespace(
        llm=SimpleNamespace(config={}), enable_search_depth=False, enable_lane=False
    )
    memory.api_version = "v1.1"
    memory.reranker = None
    memory._search_depth_cache = OrderedDict()
    memory.vector_store = MagicMock()
    memory.graph = MagicMock()
    memory.graph.search.return_value = [_GRAPH_ROW]
    memory._graph_search_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    memory._search_vector_store = MagicMock(return_value=[])
    return memory


def _async_memory():
    memory = AsyncMemory.__new__(AsyncMemory)
    memory.config = SimpleNamespace(
        llm=SimpleNamespace(config={}), enable_search_depth=False, enable_lane=False
    )
    memory.api_version = "v1.1"
    memory.reranker = None
    memory._search_depth_cache = OrderedDict()
    memory.vector_store = MagicMock()
    memory.graph = MagicMock()
    memory.graph.search.return_value = [_GRAPH_ROW]
    memory._graph_search_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    memory._search_vector_store = AsyncMock(return_value=[])
    return memory


def _patch_harness(monkeypatch):
    monkeypatch.setattr(memory_main, "capture_event", MagicMock())
    monkeypatch.setattr(memory_main, "display_first_run_notice", MagicMock())
    monkeypatch.setattr(memory_main, "display_temporal_usage_notice", MagicMock())
    monkeypatch.setattr(memory_main, "display_scale_threshold_notice", MagicMock())
    monkeypatch.setattr(memory_main, "display_first_run_notice_async", AsyncMock())
    monkeypatch.setattr(memory_main, "display_temporal_usage_notice_async", AsyncMock())
    monkeypatch.setattr(memory_main, "display_scale_threshold_notice_async", AsyncMock())


class TestSyncGraphTypeFilter:
    def test_memory_type_filter_skips_graph_recall(self, monkeypatch):
        _patch_harness(monkeypatch)
        memory = _sync_memory()

        Memory.search(memory, "部署了什么", filters={"memory_type": "FACTS", "user_id": "u1"})

        memory.graph.search.assert_not_called()

    def test_plain_search_keeps_graph_recall(self, monkeypatch):
        _patch_harness(monkeypatch)
        memory = _sync_memory()

        Memory.search(memory, "部署了什么", filters={"user_id": "u1"})

        memory.graph.search.assert_called_once()

    def test_type_alias_filter_skips_graph_recall(self, monkeypatch):
        _patch_harness(monkeypatch)
        memory = _sync_memory()

        Memory.search(
            memory, "部署了什么", filters={"type": "PREFERENCES", "user_id": "u1"}
        )

        memory.graph.search.assert_not_called()


class TestAsyncGraphTypeFilter:
    @pytest.mark.asyncio
    async def test_async_memory_type_filter_skips_graph_recall(self, monkeypatch):
        _patch_harness(monkeypatch)
        memory = _async_memory()

        await AsyncMemory.search(
            memory, "部署了什么", filters={"memory_type": "FACTS", "user_id": "u1"}
        )

        memory.graph.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_plain_search_keeps_graph_recall(self, monkeypatch):
        _patch_harness(monkeypatch)
        memory = _async_memory()

        await AsyncMemory.search(memory, "部署了什么", filters={"user_id": "u1"})

        memory.graph.search.assert_called_once()

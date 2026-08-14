"""on_memory_added hook: fired per newly-added memory id on the add() path.

Best-effort (a failing callback never breaks add). No-op when unregistered —
SDK-direct use (no server wiring) is zero-behavior-change.
"""

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from mem0.memory.main import AsyncMemory, Memory


def _notices(mocker, async_=False):
    mocker.patch("mem0.memory.main.detect_temporal_usage_from_metadata", return_value=None)
    mocker.patch("mem0.memory.main.detect_scale_threshold_from_add_result", return_value=None)
    if async_:
        mocker.patch("mem0.memory.main.display_first_run_notice_async")
        mocker.patch("mem0.memory.main.display_temporal_usage_notice_async")
        mocker.patch("mem0.memory.main.display_scale_threshold_notice_async")
    else:
        mocker.patch("mem0.memory.main.display_first_run_notice")
        mocker.patch("mem0.memory.main.display_temporal_usage_notice")
        mocker.patch("mem0.memory.main.display_scale_threshold_notice")


def _sync_memory(mocker):
    memory = Memory.__new__(Memory)
    memory.config = SimpleNamespace(
        llm=SimpleNamespace(config={}),
        enable_search_depth=False,
        enable_lane=False,
        custom_instructions=None,
        custom_update_memory_prompt=None,
        version="v1.1",
    )
    memory.api_version = "v1.1"
    memory.custom_instructions = None
    memory.db = MagicMock()
    memory.graph = None
    memory._search_depth_cache = OrderedDict()
    memory.on_memory_added = MagicMock()
    _notices(mocker)
    return memory


def _async_memory(mocker):
    memory = AsyncMemory.__new__(AsyncMemory)
    memory.config = SimpleNamespace(
        llm=SimpleNamespace(config={}),
        enable_search_depth=False,
        enable_lane=False,
        custom_instructions=None,
        custom_update_memory_prompt=None,
        version="v1.1",
    )
    memory.api_version = "v1.1"
    memory.custom_instructions = None
    memory.db = MagicMock()
    memory.graph = None
    memory._search_depth_cache = OrderedDict()
    memory.on_memory_added = MagicMock()
    _notices(mocker, async_=True)
    return memory


class TestSyncAddHook:
    def test_sync_add_notifies_new_memory_id(self, mocker):
        memory = _sync_memory(mocker)
        memory._add_to_vector_store = MagicMock(
            return_value=[{"id": "mem-1", "memory": "x", "event": "ADD"}]
        )

        memory.add("发哥喜欢咖啡", user_id="u1")

        memory.on_memory_added.assert_called_once_with("mem-1")

    def test_sync_add_no_results_does_not_notify(self, mocker):
        memory = _sync_memory(mocker)
        memory._add_to_vector_store = MagicMock(return_value=[])

        memory.add("发哥喜欢咖啡", user_id="u1")

        memory.on_memory_added.assert_not_called()

    def test_sync_add_skips_non_add_events(self, mocker):
        memory = _sync_memory(mocker)
        memory._add_to_vector_store = MagicMock(
            return_value=[
                {"id": "mem-1", "memory": "x", "event": "ADD"},
                {"id": "old-9", "memory": "y", "event": "UPDATE"},
            ]
        )

        memory.add("发哥喜欢咖啡", user_id="u1")

        memory.on_memory_added.assert_called_once_with("mem-1")

    def test_callback_exception_does_not_break_add(self, mocker):
        memory = _sync_memory(mocker)
        memory._add_to_vector_store = MagicMock(
            return_value=[{"id": "mem-1", "memory": "x", "event": "ADD"}]
        )
        memory.on_memory_added.side_effect = RuntimeError("boom")

        result = memory.add("发哥喜欢咖啡", user_id="u1")

        assert len(result["results"]) == 1

    def test_no_hook_add_normal(self, mocker):
        memory = _sync_memory(mocker)
        memory.on_memory_added = None
        memory._add_to_vector_store = MagicMock(
            return_value=[{"id": "mem-1", "memory": "x", "event": "ADD"}]
        )

        result = memory.add("发哥喜欢咖啡", user_id="u1")

        assert len(result["results"]) == 1


class TestAsyncAddHook:
    @pytest.mark.asyncio
    async def test_async_add_notifies_new_memory_id(self, mocker):
        memory = _async_memory(mocker)
        memory._add_to_vector_store = AsyncMock(
            return_value=[{"id": "mem-1", "memory": "x", "event": "ADD"}]
        )

        await memory.add("发哥喜欢咖啡", user_id="u1")

        memory.on_memory_added.assert_called_once_with("mem-1")

    @pytest.mark.asyncio
    async def test_async_add_no_results_does_not_notify(self, mocker):
        memory = _async_memory(mocker)
        memory._add_to_vector_store = AsyncMock(return_value=[])

        await memory.add("发哥喜欢咖啡", user_id="u1")

        memory.on_memory_added.assert_not_called()

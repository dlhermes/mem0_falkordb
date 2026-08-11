"""Core-library delete hook: Memory.on_memory_deleted fires on successful
delete (sync + async) and never breaks the delete flow when the callback fails.

This is the mechanism the server and maintenance scripts use to cascade-clean
the evolve_* heat tables whenever a memory is deleted.
"""

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from mem0.memory import main as memory_main
from mem0.memory.main import AsyncMemory, Memory


def _make_sync_memory():
    memory = Memory.__new__(Memory)
    memory._search_depth_cache = OrderedDict()
    memory.vector_store = MagicMock()
    memory.db = MagicMock()
    memory._entity_store = None
    memory.on_memory_deleted = None
    return memory


def _make_async_memory():
    memory = AsyncMemory.__new__(AsyncMemory)
    memory._search_depth_cache = OrderedDict()
    memory.vector_store = MagicMock()
    memory.db = MagicMock()
    memory._entity_store = None
    memory.on_memory_deleted = None
    return memory


def _stub_notices(monkeypatch):
    monkeypatch.setattr(memory_main, "capture_event", MagicMock())
    monkeypatch.setattr(memory_main, "detect_decay_usage_from_delete", MagicMock(return_value=None))
    monkeypatch.setattr(memory_main, "display_decay_usage_notice", MagicMock())
    monkeypatch.setattr(memory_main, "display_first_run_notice", MagicMock())
    monkeypatch.setattr(memory_main, "detect_decay_usage_from_delete_all", MagicMock(return_value=None))
    monkeypatch.setattr(memory_main, "display_decay_usage_notice_async", AsyncMock())
    monkeypatch.setattr(memory_main, "display_first_run_notice_async", AsyncMock())


def test_sync_delete_fires_on_memory_deleted(monkeypatch):
    memory = _make_sync_memory()
    memory.vector_store.get.return_value = SimpleNamespace(payload={"data": "like hiking"})
    _stub_notices(monkeypatch)

    deleted = []
    memory.on_memory_deleted = deleted.append

    result = Memory.delete(memory, "mem-1")

    assert result["message"] == "Memory deleted successfully!"
    assert deleted == ["mem-1"]


@pytest.mark.asyncio
async def test_async_delete_fires_on_memory_deleted(monkeypatch):
    memory = _make_async_memory()
    memory.vector_store.get.return_value = SimpleNamespace(payload={"data": "like hiking"})
    _stub_notices(monkeypatch)

    deleted = []
    memory.on_memory_deleted = deleted.append

    result = await AsyncMemory.delete(memory, "mem-1")

    assert result["message"] == "Memory deleted successfully!"
    assert deleted == ["mem-1"]


def test_sync_delete_survives_hook_exception(monkeypatch):
    memory = _make_sync_memory()
    memory.vector_store.get.return_value = SimpleNamespace(payload={"data": "like hiking"})
    _stub_notices(monkeypatch)

    def _boom(memory_id):
        raise RuntimeError("cleanup failed")

    memory.on_memory_deleted = _boom

    result = Memory.delete(memory, "mem-1")

    assert result["message"] == "Memory deleted successfully!"


@pytest.mark.asyncio
async def test_async_delete_survives_hook_exception(monkeypatch):
    memory = _make_async_memory()
    memory.vector_store.get.return_value = SimpleNamespace(payload={"data": "like hiking"})
    _stub_notices(monkeypatch)

    def _boom(memory_id):
        raise RuntimeError("cleanup failed")

    memory.on_memory_deleted = _boom

    result = await AsyncMemory.delete(memory, "mem-1")

    assert result["message"] == "Memory deleted successfully!"

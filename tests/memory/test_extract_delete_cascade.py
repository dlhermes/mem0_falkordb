"""Extraction-path DELETE events must go through _delete_memory (cascade).

Regression guard: LLM extraction may emit event=DELETE. That path used to do a
bare vector_store.delete, skipping entity-store cleanup, the on_memory_deleted
hook, and writing a wrong history row (old_memory=LLM new fact instead of the
deleted memory's original text). DELETE must now route through _delete_memory.
"""

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mem0.memory.main import AsyncMemory, Memory


def _setup_mocks(mocker):
    """Common mock wiring for the extraction pipeline (mirrors test_main.py)."""
    mock_embedder = mocker.MagicMock()
    mock_embedder.return_value.embed.return_value = [0.1, 0.2, 0.3]
    mocker.patch("mem0.utils.factory.EmbedderFactory.create", mock_embedder)

    mock_vector_store = mocker.MagicMock()
    mock_vector_store.return_value.search.return_value = []
    mocker.patch(
        "mem0.utils.factory.VectorStoreFactory.create", side_effect=[mock_vector_store.return_value, mocker.MagicMock()]
    )

    mock_llm = mocker.MagicMock()
    mocker.patch("mem0.utils.factory.LlmFactory.create", mock_llm)

    mocker.patch("mem0.memory.main.SQLiteManager", mocker.MagicMock())

    return mock_llm, mock_vector_store


def _memory_with_existing(mocker, existing_payload, memory_cls=Memory):
    """Build a Memory/AsyncMemory with one existing memory returned by search."""
    _setup_mocks(mocker)
    embedder_mock = mocker.patch("mem0.utils.factory.EmbedderFactory.create")
    embedder_mock.return_value.embed.return_value = [0.1, 0.2, 0.3]
    embedder_mock.return_value.embed_batch.return_value = [[0.1, 0.2, 0.3]]
    mocker.patch("mem0.memory.main.capture_event")
    memory = memory_cls()
    memory.config = mocker.MagicMock()
    memory.config.custom_instructions = None
    memory.config.custom_update_memory_prompt = None
    memory.custom_instructions = None
    memory.api_version = "v1.1"
    memory.db.get_last_messages = MagicMock(return_value=[])
    memory.db.save_messages = MagicMock()
    memory.vector_store.search.return_value = [
        SimpleNamespace(id="uuid-1", payload=dict(existing_payload))
    ]
    memory.vector_store.get.return_value = SimpleNamespace(payload=dict(existing_payload))
    return memory


_DELETE_EXTRACTION = json.dumps(
    {"memory": [{"id": "0", "text": "新事实", "event": "DELETE", "metadata": {}}]}
)
_ORIGINAL_TEXT = "我出生于北京，毕业于清华大学"


class TestSyncExtractDeleteCascade:
    def test_delete_event_routes_through_delete_memory(self, mocker):
        memory = _memory_with_existing(
            mocker, {"data": _ORIGINAL_TEXT, "created_at": "2025-01-01T00:00:00+00:00"}
        )
        memory.llm.generate_response.return_value = _DELETE_EXTRACTION
        memory._remove_memory_from_entity_store = MagicMock()
        deleted = []
        memory.on_memory_deleted = deleted.append

        result = memory._add_to_vector_store(
            messages=[{"role": "user", "content": "test"}], metadata={}, filters={}, infer=True
        )

        assert result == []
        # a) _delete_memory semantics: original text as old_memory + is_deleted flag
        memory.vector_store.delete.assert_called_once_with(vector_id="uuid-1")
        hist_args = memory.db.add_history.call_args
        assert hist_args.args[0] == "uuid-1"
        assert hist_args.args[1] == _ORIGINAL_TEXT
        assert hist_args.args[2] is None
        assert hist_args.args[3] == "DELETE"
        assert hist_args.kwargs["is_deleted"] == 1
        # b) entity cleanup triggered
        memory._remove_memory_from_entity_store.assert_called_once()
        # c) on_memory_deleted hook fired
        assert deleted == ["uuid-1"]
        # d) no wrong history row with the LLM new fact as old_memory
        for call in memory.db.add_history.call_args_list:
            assert call.args[1] != "新事实"

    def test_delete_missing_memory_does_not_break_add(self, mocker, caplog):
        memory = _memory_with_existing(
            mocker, {"data": _ORIGINAL_TEXT, "created_at": "2025-01-01T00:00:00+00:00"}
        )
        memory.llm.generate_response.return_value = _DELETE_EXTRACTION
        memory.vector_store.get.return_value = None
        memory._remove_memory_from_entity_store = MagicMock()

        with caplog.at_level(logging.WARNING):
            result = memory._add_to_vector_store(
                messages=[{"role": "user", "content": "test"}], metadata={}, filters={}, infer=True
            )

        assert result == []


class TestAsyncExtractDeleteCascade:
    @pytest.mark.asyncio
    async def test_async_delete_event_routes_through_delete_memory(self, mocker):
        memory = _memory_with_existing(
            mocker,
            {"data": _ORIGINAL_TEXT, "created_at": "2025-01-01T00:00:00+00:00"},
            AsyncMemory,
        )
        memory.llm.generate_response.return_value = _DELETE_EXTRACTION
        memory._remove_memory_from_entity_store = mocker.AsyncMock()
        deleted = []
        memory.on_memory_deleted = deleted.append

        result = await memory._add_to_vector_store(
            messages=[{"role": "user", "content": "test"}], metadata={}, effective_filters={}, infer=True
        )

        assert result == []
        memory.vector_store.delete.assert_called_once_with(vector_id="uuid-1")
        hist_args = memory.db.add_history.call_args
        assert hist_args.args[0] == "uuid-1"
        assert hist_args.args[1] == _ORIGINAL_TEXT
        assert hist_args.args[2] is None
        assert hist_args.args[3] == "DELETE"
        assert hist_args.kwargs["is_deleted"] == 1
        memory._remove_memory_from_entity_store.assert_awaited_once()
        assert deleted == ["uuid-1"]
        for call in memory.db.add_history.call_args_list:
            assert call.args[1] != "新事实"

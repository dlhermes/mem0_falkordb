"""Candidate discovery + refine engine tests (fully mocked).

- cluster_candidates / refine_group are pure functions (embed_batch / LLM mocked).
- API tests build a TestClient over the refine router with get_db + get_memory_instance
  overridden; auth overridden except for the 401 tests.
"""

import json
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from auth import require_auth  # noqa: E402
from db import get_db  # noqa: E402
from models import MemoryRefineCandidate  # noqa: E402
from routers import refine as refine_router  # noqa: E402
import refine_memory  # noqa: E402

_ADMIN = SimpleNamespace(role="admin", id="admin-1")


def _memory_with_embeddings(vectors, llm_return=None, llm_raises=None):
    memory = MagicMock()
    memory.embedding_model.embed_batch = MagicMock(return_value=vectors)
    if llm_raises is not None:
        memory.llm.generate_response.side_effect = llm_raises
    else:
        memory.llm.generate_response = MagicMock(return_value=llm_return)
    return memory


def _items(data_list):
    return [{"id": f"m{i}", "data": d} for i, d in enumerate(data_list)]


def _make_app(db, override_auth=True):
    app = FastAPI()
    app.include_router(refine_router.router)
    if override_auth:
        app.dependency_overrides[require_auth] = lambda: _ADMIN
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


class TestClusterCandidates:
    def test_three_similar_texts_cluster_into_one_candidate(self):
        memory = _memory_with_embeddings([[1, 0, 0], [0.9, 0.43589, 0], [0.95, 0.31225, 0]])

        candidates = refine_memory.cluster_candidates(
            memory, _items(["碎记忆A1", "碎记忆A2", "碎记忆A3"])
        )

        assert len(candidates) == 1
        assert len(candidates[0]["memory_ids"]) == 3
        assert len(candidates[0]["topic"]) <= 20

    def test_three_distinct_topics_produce_three_candidates(self):
        memory = _memory_with_embeddings(
            [
                [1, 0, 0], [0.9, 0.43589, 0], [0.95, 0.31225, 0],  # topic A
                [0, 1, 0], [0.43589, 0.9, 0], [0.31225, 0.95, 0],  # topic B
                [0, 0, 1], [0, 0.43589, 0.9], [0, 0.31225, 0.95],  # topic C
            ]
        )

        candidates = refine_memory.cluster_candidates(
            memory, _items(["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"])
        )

        assert len(candidates) == 3

    def test_group_below_min_size_is_filtered(self):
        memory = _memory_with_embeddings([[1, 0, 0], [0.9, 0.43589, 0]])

        candidates = refine_memory.cluster_candidates(
            memory, _items(["碎记忆X", "碎记忆Y"])
        )

        assert candidates == []

    def test_mixed_near_and_far_splits_groups(self):
        memory = _memory_with_embeddings(
            [[1, 0, 0], [0.9, 0.43589, 0], [0, 1, 0]]
        )

        candidates = refine_memory.cluster_candidates(
            memory, _items(["近邻A", "近邻B", "远处C"])
        )

        assert candidates == []  # 2-member near group + 1-member far group both < 3


class TestRefineGroup:
    def test_valid_llm_json_saves_proposal_without_writing_vector_store(self):
        memory = _memory_with_embeddings(
            [],
            llm_return=json.dumps({"summary": ["高层抽象1", "高层抽象2"]}, ensure_ascii=False),
        )
        memory.vector_store.get.return_value = SimpleNamespace(payload={"data": "碎记忆"})

        out = refine_memory.refine_group(memory, {"memory_ids": ["m1", "m2", "m3"]})

        assert out["status"] == "proposed"
        assert out["suggested_text"] == ["高层抽象1", "高层抽象2"]
        memory.vector_store.insert.assert_not_called()
        memory.vector_store.update.assert_not_called()

    def test_invalid_json_fails_gracefully(self):
        memory = _memory_with_embeddings([], llm_return="这不是JSON")
        memory.vector_store.get.return_value = SimpleNamespace(payload={"data": "碎记忆"})

        out = refine_memory.refine_group(memory, {"memory_ids": ["m1", "m2", "m3"]})

        assert out["status"] == "failed"
        assert out["suggested_text"] == []

    def test_llm_exception_fails_gracefully(self):
        memory = _memory_with_embeddings([], llm_raises=TimeoutError("timeout"))
        memory.vector_store.get.return_value = SimpleNamespace(payload={"data": "碎记忆"})

        out = refine_memory.refine_group(memory, {"memory_ids": ["m1", "m2", "m3"]})

        assert out["status"] == "failed"
        assert out["suggested_text"] == []

    def test_no_texts_found_fails_gracefully(self):
        memory = _memory_with_embeddings([], llm_return=json.dumps({"summary": ["x"]}))
        memory.vector_store.get.return_value = None

        out = refine_memory.refine_group(memory, {"memory_ids": ["m1"]})

        assert out["status"] == "failed"
        assert out["suggested_text"] == []


class TestRefineApi:
    def _stale_memory_ids(self):
        return [("m1",), ("m2",), ("m3",)]

    def test_post_generates_and_get_lists_proposed_candidates(self, mocker):
        db = MagicMock()
        db.execute.return_value.all.return_value = self._stale_memory_ids()

        memory = MagicMock()
        memory.vector_store.get.side_effect = lambda mid: SimpleNamespace(
            payload={"data": f"碎记忆 {mid}", "user_id": "u1"}
        )
        memory.embedding_model.embed_batch.return_value = [
            [1, 0, 0], [0.9, 0.43589, 0], [0.95, 0.31225, 0]
        ]
        memory.llm.generate_response.return_value = json.dumps(
            {"summary": ["高层抽象"]}, ensure_ascii=False
        )
        mocker.patch.object(refine_router, "get_memory_instance", return_value=memory)

        client = _make_app(db)

        post = client.post("/memory/refine/candidates", params={"user_id": "u1"})

        assert post.status_code == 200
        cands = post.json()["candidates"]
        assert len(cands) == 1
        assert cands[0]["status"] == "proposed"
        assert cands[0]["suggested_text"] == ["高层抽象"]
        assert len(cands[0]["memory_ids"]) == 3
        db.add.assert_called()
        db.commit.assert_called_once()

        row = MemoryRefineCandidate(
            user_id="u1",
            memory_ids=cands[0]["memory_ids"],
            topic=cands[0]["topic"],
            status="proposed",
            suggested_text=cands[0]["suggested_text"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        row.id = 7
        db.execute.return_value.scalars.return_value.all.return_value = [row]

        get = client.get("/memory/refine/candidates", params={"user_id": "u1"})

        assert get.status_code == 200
        listed = get.json()["candidates"]
        assert len(listed) == 1
        assert listed[0]["id"] == 7
        assert listed[0]["status"] == "proposed"
        assert listed[0]["suggested_text"] == ["高层抽象"]
        assert listed[0]["memory_ids"] == cands[0]["memory_ids"]

    def test_endpoints_require_auth(self, mocker):
        import auth as auth_mod

        mocker.patch.object(auth_mod, "AUTH_DISABLED", False)
        db = MagicMock()
        client = _make_app(db, override_auth=False)

        assert client.post("/memory/refine/candidates").status_code == 401
        assert client.get("/memory/refine/candidates").status_code == 401

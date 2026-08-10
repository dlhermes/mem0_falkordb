"""Tests for the evolve feedback router."""

import os
import sys

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-for-evolve")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# server/ modules use bare imports (from db import ...), so the server
# directory itself must be importable, mirroring how it runs in Docker.
_SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from auth import verify_auth  # noqa: E402
from db import Base, get_db  # noqa: E402
from models import EvolveFeedback, EvolveSalience, EvolveSalienceAdjustment  # noqa: E402
from routers import evolve as evolve_router  # noqa: E402


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    app = FastAPI()
    app.include_router(evolve_router.router)
    app.dependency_overrides[verify_auth] = lambda: None

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    return TestClient(app), TestingSessionLocal


def _post(client, **body):
    return client[0].post("/evolve/feedback", json=body)


def test_useful_on_new_memory_starts_from_ceiling(client):
    # new memories start at 1.0; useful is clamped to the 1.0 ceiling
    resp = _post(client, memory_id="m1", feedback_type="useful")
    assert resp.status_code == 200
    assert resp.json() == {"memory_id": "m1", "salience_score": 1.0}

    with client[1]() as db:
        row = db.get(EvolveSalience, "m1")
        assert row.salience_score == 1.0


def test_useful_raises_a_demoted_memory(client):
    _post(client, memory_id="m2", feedback_type="useless")
    resp = _post(client, memory_id="m2", feedback_type="useful")
    assert resp.json()["salience_score"] == 0.95


def test_useless_lowers_score(client):
    _post(client, memory_id="m3", feedback_type="useless")
    resp = _post(client, memory_id="m3", feedback_type="useless")
    assert resp.json()["salience_score"] == 0.7


def test_score_clamps_to_floor(client):
    for _ in range(10):
        _post(client, memory_id="m4", feedback_type="useless")
    resp = _post(client, memory_id="m4", feedback_type="useless")
    assert resp.json()["salience_score"] == 0.05


def test_correction_writes_audit_and_feedback_rows(client):
    _post(client, memory_id="m5", feedback_type="useless")
    resp = _post(client, memory_id="m5", feedback_type="correction", source="auto", note="wrong")
    assert resp.json()["salience_score"] == 0.8

    with client[1]() as db:
        feedback = db.scalar(
            select(EvolveFeedback).where(
                EvolveFeedback.memory_id == "m5", EvolveFeedback.feedback_type == "correction"
            )
        )
        assert feedback is not None
        assert feedback.feedback_type == "correction"
        assert feedback.source == "auto"
        assert feedback.note == "wrong"

        adjustment = db.scalar(
            select(EvolveSalienceAdjustment).where(
                EvolveSalienceAdjustment.memory_id == "m5", EvolveSalienceAdjustment.reason == "correction"
            )
        )
        assert adjustment is not None
        assert adjustment.delta == -0.05
        assert adjustment.reason == "correction"
        assert adjustment.feedback_id == feedback.id


def test_invalid_feedback_type_rejected(client):
    resp = _post(client, memory_id="m6", feedback_type="nope")
    assert resp.status_code == 422

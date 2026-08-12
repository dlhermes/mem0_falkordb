"""Tests for the /requests router response shape: {items, total}.

The dashboard "total requests" card previously showed the length of the
limit-bounded window (always 200 once enough logs exist). The endpoint now
returns {"items": [...], "total": N} where items is the bounded window and
total is the full count under the same auth_type filter.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

_SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from auth import require_admin  # noqa: E402
from db import Base, get_db  # noqa: E402
from models import RequestLog  # noqa: E402
from routers import requests as requests_router  # noqa: E402


def _add_log(db, n, auth_type="api_key", method="GET", status=200, base_time=None):
    base_time = base_time or datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        db.add(
            RequestLog(
                id=uuid.uuid4(),
                method=method,
                path=f"/m{i}",
                status_code=status,
                latency_ms=float(i),
                auth_type=auth_type,
                created_at=base_time + timedelta(minutes=i),
            )
        )


def _make_client():
    # Single shared in-memory SQLite connection (StaticPool) so the
    # per-request sessions see the tables created by the fixture.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    app = FastAPI()
    app.include_router(requests_router.router)
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[get_db] = lambda: TestingSession()

    return engine, TestingSession, TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client():
    engine, TestingSession, client = _make_client()
    with TestingSession() as db:
        _add_log(db, 5, auth_type="api_key")
        _add_log(db, 1, auth_type="bearer")  # excluded by the auth_type filter
        db.commit()
    return client


class TestRequestsResponseShape:
    def test_response_is_object_with_items_and_total(self, client):
        resp = client.get("/requests")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        assert set(body) == {"items", "total"}
        assert isinstance(body["items"], list)
        assert body["total"] == 5

    def test_items_are_serialized_logs(self, client):
        resp = client.get("/requests")
        item = resp.json()["items"][0]
        assert {
            "id",
            "method",
            "path",
            "status_code",
            "latency_ms",
            "auth_type",
            "created_at",
        } <= set(item)

    def test_total_excludes_non_api_key_auth_types(self, client):
        resp = client.get("/requests")
        assert resp.json()["total"] == 5  # the bearer log is excluded


class TestTotalNotLimitedByLimit:
    @pytest.fixture
    def big_client(self):
        engine, TestingSession, client = _make_client()
        with TestingSession() as db:
            _add_log(db, 250, auth_type="api_key")
            db.commit()
        return client

    def test_total_is_full_count_with_small_limit(self, big_client):
        resp = big_client.get("/requests", params={"limit": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["total"] == 250

    def test_total_is_full_count_with_default_limit(self, big_client):
        body = big_client.get("/requests").json()
        assert len(body["items"]) == 50
        assert body["total"] == 250

    def test_items_ordered_desc(self, big_client):
        items = big_client.get("/requests", params={"limit": 2}).json()["items"]
        assert items[0]["path"] == "/m249"
        assert items[1]["path"] == "/m248"

"""Server configure endpoint: LLM fallbacks provider validation + secret redaction.

POST /configure must reject llm.fallbacks entries whose provider is not in
BUNDLED_LLM_PROVIDERS (same 400 contract as the top-level llm/embedder
providers), and GET /configure must redact api_key inside fallback configs.
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-for-fallbacks")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

# server/ modules use bare imports (from auth import ...), so the server
# directory itself must be importable, mirroring how it runs in Docker.
_SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)


def _mock_session():
    """DB session whose reads return None so bootstrap auth paths behave empty."""
    session = MagicMock()
    session.scalar.return_value = None
    session.query.return_value.first.return_value = None
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    return session


@pytest.fixture
def _mock_memory():
    """Patch Memory.from_config so the server imports without a real backend."""
    mock_instance = MagicMock()
    with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}):
        with patch("mem0.Memory.from_config", return_value=mock_instance):
            with patch("server_state._load_overrides", return_value={}):
                with patch("server_state._save_overrides", return_value=None):
                    with patch("db.SessionLocal", return_value=_mock_session()):
                        with patch("auth.SessionLocal", return_value=_mock_session()):
                            yield mock_instance


def _load_app(env_overrides: dict):
    """Reload server/main.py with the given environment and return the module."""
    import server.main as server_main

    with patch.dict(os.environ, env_overrides, clear=False):
        importlib.reload(server_main)
    return server_main


class TestValidateBundledFallbacks:
    """POST /configure rejects non-bundled LLM fallback providers."""

    @pytest.fixture(autouse=True)
    def _setup(self, _mock_memory):
        self.server_main = _load_app({"ADMIN_API_KEY": ""})
        self.client = TestClient(self.server_main.app)

    def test_valid_fallback_provider_accepted(self):
        resp = self.client.post(
            "/configure",
            json={"llm": {"fallbacks": [{"provider": "openai", "config": {"api_key": "sk-x"}}]}},
        )
        assert resp.status_code == 200

    def test_invalid_fallback_provider_rejected(self):
        resp = self.client.post(
            "/configure",
            json={"llm": {"fallbacks": [{"provider": "notexist", "config": {"api_key": "sk-x"}}]}},
        )
        assert resp.status_code == 400
        assert "notexist" in resp.json()["detail"]

    def test_invalid_fallback_provider_names_index(self):
        resp = self.client.post(
            "/configure",
            json={
                "llm": {
                    "fallbacks": [
                        {"provider": "openai", "config": {}},
                        {"provider": "notexist", "config": {}},
                    ]
                }
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "fallbacks" in detail
        assert "notexist" in detail

    def test_no_fallbacks_behavior_unchanged(self):
        resp = self.client.post("/configure", json={"llm": {"provider": "openai"}})
        assert resp.status_code == 200

    def test_non_list_fallbacks_rejected(self):
        resp = self.client.post(
            "/configure",
            json={"llm": {"fallbacks": {"provider": "openai", "config": {}}}},
        )
        assert resp.status_code == 400


class TestRedactFallbackSecrets:
    """GET /configure redacts api_key inside fallback configs."""

    @pytest.fixture(autouse=True)
    def _setup(self, _mock_memory):
        self.server_main = _load_app({"ADMIN_API_KEY": ""})
        self.client = TestClient(self.server_main.app)

    def test_redact_config_redacts_fallback_api_key(self):
        redacted = self.server_main._redact_config(
            {"llm": {"fallbacks": [{"provider": "openai", "config": {"api_key": "sk-xxx"}}]}}
        )
        assert redacted["llm"]["fallbacks"][0]["config"]["api_key"] == "[redacted]"

    def test_get_configure_redacts_fallback_api_key(self):
        self.client.post(
            "/configure",
            json={"llm": {"fallbacks": [{"provider": "openai", "config": {"api_key": "sk-xxx"}}]}},
        )
        resp = self.client.get("/configure")
        assert resp.status_code == 200
        fb = resp.json()["llm"]["fallbacks"][0]
        assert fb["config"]["api_key"] == "[redacted]"

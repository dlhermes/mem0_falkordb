"""Lightweight test: mem0_update/mem0_delete trigger automatic feedback reports.

Does not import the full Hermes plugin module (which needs agent/tools internals).
Instead it instantiates the provider class via importlib with stubbed dependency
modules, so this runs anywhere the repo's mem0 plugin dir is importable.
"""

import importlib.util
import json
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "memory" / "mem0"


def _load_plugin_module():
    # Stub the Hermes-agent imports the plugin depends on so it can be imported
    # in isolation; only the pieces the tools path touches are needed.
    import types

    for name, stub in {
        "agent": types.ModuleType("agent"),
        "tools": types.ModuleType("tools"),
    }.items():
        sys.modules.setdefault(name, stub)

    memory_provider = types.ModuleType("agent.memory_provider")
    memory_provider.MemoryProvider = object
    sys.modules["agent.memory_provider"] = memory_provider

    secret_scope = types.ModuleType("agent.secret_scope")
    secret_scope.get_secret = lambda key, default="": default
    sys.modules["agent.secret_scope"] = secret_scope

    hermes_constants = types.ModuleType("hermes_constants")
    hermes_constants.get_hermes_home = lambda: Path("/tmp/opencode/nonexistent-hermes-home")
    sys.modules["hermes_constants"] = hermes_constants

    registry = types.ModuleType("tools.registry")
    registry.tool_error = lambda msg: json.dumps({"error": msg})
    sys.modules["tools.registry"] = registry

    spec = importlib.util.spec_from_file_location("mem0_plugin", _PLUGIN_DIR / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _MockBackend:
    """Records calls; update/delete succeed, report_feedback can be made to fail."""

    def __init__(self, fail_report=False):
        self.fail_report = fail_report
        self.updates = []
        self.deletes = []
        self.reports = []

    def update(self, memory_id, text):
        self.updates.append((memory_id, text))
        return {"result": "Memory updated.", "memory_id": memory_id}

    def delete(self, memory_id):
        self.deletes.append(memory_id)
        return {"result": "Memory deleted.", "memory_id": memory_id}

    def report_feedback(self, memory_id, feedback_type, source="auto", note=None):
        if self.fail_report:
            raise RuntimeError("server unreachable")
        self.reports.append({"memory_id": memory_id, "feedback_type": feedback_type,
                             "source": source, "note": note})


def _make_provider(plugin, backend):
    provider = plugin.Mem0MemoryProvider.__new__(plugin.Mem0MemoryProvider)
    provider._config = {"mode": "oss", "oss": {"vector_store": {"provider": "qdrant"}}}
    provider._mode = "oss"
    provider._backend = backend
    provider._agent_id = "hermes"
    provider._user_id = "hermes-user"
    provider._init_error = None
    provider._consecutive_failures = 0
    provider._breaker_open_until = 0.0
    provider._breaker_lock = __import__("threading").Lock()
    return provider


def _load():
    module = _load_plugin_module()
    if getattr(module, "_COALESCE_ENABLED", True):
        sys.modules.pop("mem0_plugin", None)
    return module


def test_update_triggers_correction_report():
    plugin = _load_plugin_module()
    backend = _MockBackend()
    provider = _make_provider(plugin, backend)

    out = provider.handle_tool_call("mem0_update", {"memory_id": "abc", "text": "loves hiking"})
    assert json.loads(out)["result"] == "Memory updated."
    assert backend.updates == [("abc", "loves hiking")]
    assert len(backend.reports) == 1
    report = backend.reports[0]
    assert report["feedback_type"] == "correction"
    assert report["source"] == "auto"
    assert report["memory_id"] == "abc"
    assert report["note"] == "loves hiking"


def test_delete_triggers_useless_report():
    plugin = _load_plugin_module()
    backend = _MockBackend()
    provider = _make_provider(plugin, backend)

    out = provider.handle_tool_call("mem0_delete", {"memory_id": "xyz"})
    assert json.loads(out)["result"] == "Memory deleted."
    assert backend.deletes == ["xyz"]
    assert backend.reports == [{"memory_id": "xyz", "feedback_type": "useless",
                                "source": "auto", "note": None}]


def test_report_failure_does_not_break_tool_call():
    plugin = _load_plugin_module()
    backend = _MockBackend(fail_report=True)
    provider = _make_provider(plugin, backend)

    out = provider.handle_tool_call("mem0_update", {"memory_id": "abc", "text": "loves hiking"})
    assert json.loads(out)["result"] == "Memory updated."
    out = provider.handle_tool_call("mem0_delete", {"memory_id": "xyz"})
    assert json.loads(out)["result"] == "Memory deleted."


def test_long_note_is_truncated():
    plugin = _load_plugin_module()
    backend = _MockBackend()
    provider = _make_provider(plugin, backend)
    long_text = "x" * (plugin._FEEDBACK_NOTE_MAX_CHARS + 100)

    provider.handle_tool_call("mem0_update", {"memory_id": "abc", "text": long_text})
    assert len(backend.reports[0]["note"]) <= plugin._FEEDBACK_NOTE_MAX_CHARS + 1


def test_update_error_returns_tool_error_without_report():
    class _FailingUpdateBackend(_MockBackend):
        def update(self, memory_id, text):
            raise ValueError("MemoryNotFoundError: not found")

    plugin = _load_plugin_module()
    backend = _FailingUpdateBackend()
    provider = _make_provider(plugin, backend)

    out = provider.handle_tool_call("mem0_update", {"memory_id": "nope", "text": "x"})
    assert "Memory not found" in out
    assert backend.reports == []


if __name__ == "__main__":
    _load()
    test_update_triggers_correction_report()
    test_delete_triggers_useless_report()
    test_report_failure_does_not_break_tool_call()
    test_long_note_is_truncated()
    test_update_error_returns_tool_error_without_report()
    print("all feedback-loop tests passed")

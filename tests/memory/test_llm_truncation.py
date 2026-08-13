from types import SimpleNamespace

import pytest

from mem0.llms.fallback import FallbackLLM
from mem0.llms.openai import OpenAILLM


class MockLLM:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.call_count = 0

    def generate_response(self, messages, response_format=None, tools=None, tool_choice="auto", **kwargs):
        self.call_count += 1
        if self.exc is not None:
            raise self.exc
        return self.result


def _resp(finish_reason, content="parsed content"):
    choice = SimpleNamespace(
        message=SimpleNamespace(content=content, tool_calls=None),
        finish_reason=finish_reason,
    )
    return SimpleNamespace(choices=[choice])


def _llm():
    return OpenAILLM(config={"api_key": "test-key"})


def test_parse_response_raises_on_truncated():
    llm = _llm()

    with pytest.raises(ValueError, match="truncated"):
        llm._parse_response(_resp(finish_reason="length"), tools=None)


def test_parse_response_returns_content_on_stop():
    llm = _llm()

    result = llm._parse_response(_resp(finish_reason="stop"), tools=None)

    assert result == "parsed content"


def test_parse_response_tools_path_untouched_on_truncated():
    llm = _llm()

    result = llm._parse_response(_resp(finish_reason="length"), tools=[{"type": "function"}])

    assert result == {"content": "parsed content", "tool_calls": []}


def test_fallback_switches_layer_on_truncation_error():
    primary = MockLLM(exc=ValueError("LLM response truncated (finish_reason=length)"))
    fb1 = MockLLM(result="fb1")
    fallback = FallbackLLM(primary, [fb1])

    result = fallback.generate_response([{"role": "user", "content": "hi"}])

    assert result == "fb1"
    assert primary.call_count == 1
    assert fb1.call_count == 1


def test_fallback_primary_success_does_not_switch():
    primary = MockLLM(result="ok")
    fb1 = MockLLM(result="fb1")
    fallback = FallbackLLM(primary, [fb1])

    result = fallback.generate_response([{"role": "user", "content": "hi"}])

    assert result == "ok"
    assert fb1.call_count == 0

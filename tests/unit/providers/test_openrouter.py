"""OpenRouter against a fake HTTP transport."""

import json

import httpx
import pytest

from swarmax import runtime
from swarmax.errors import ProviderError
from swarmax.providers import OpenRouter
from swarmax.providers.openrouter import INVALID_ARGUMENTS
from swarmax.types import Message, ToolCall

SETTINGS = {"temperature": 0, "max_tokens": 50}


def stream_of(*chunks):
    """Return a streamed response body."""
    lines = [f"data: {json.dumps(chunk)}" for chunk in chunks]
    return "\n\n".join([": OPENROUTER PROCESSING", *lines, "data: [DONE]", ""])


def transport(handler):
    """Return a fake transport around a request handler."""
    return httpx.MockTransport(handler)


def provider(handler):
    """Return a provider that never reaches the network."""
    return OpenRouter(api_key="sk-test", transport=transport(handler))


async def complete(llm, messages=(), tools=(), on_text=None):
    """Make one call."""
    return await llm.complete(
        list(messages), list(tools), model="a/b", settings=SETTINGS, on_text=on_text
    )


async def test_streams_text_and_fills_usage_with_cost():
    """Deltas stream, and usage comes from the final chunk."""
    body = stream_of(
        {"id": "x", "model": "a/b", "choices": [{"delta": {"content": "Hel"}}]},
        {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 4, "cost": 0.02}},
    )
    seen = []
    result = await complete(
        provider(lambda request: httpx.Response(200, text=body)), (), (), seen.append
    )
    assert (result.text, seen) == ("Hello", ["Hel", "lo"])
    assert (result.usage.input_tokens, result.usage.output_tokens) == (3, 4)
    assert result.usage.cost == 0.02
    assert result.raw["finish_reason"] == "stop"


async def test_tool_calls_arrive_in_pieces():
    """Argument fragments join into one call."""
    first = {"index": 0, "id": "c1", "function": {"name": "add", "arguments": '{"a"'}}
    second = {"index": 0, "function": {"arguments": ": 1}"}}
    body = stream_of(
        {"choices": [{"delta": {"tool_calls": [first]}}]},
        {"choices": [{"delta": {"tool_calls": [second]}}]},
    )
    result = await complete(provider(lambda request: httpx.Response(200, text=body)))
    assert result.tool_calls == (ToolCall(id="c1", name="add", input={"a": 1}),)


async def test_invalid_arguments_stay_visible():
    """Broken JSON from a model reaches validation instead of disappearing."""
    piece = {"index": 0, "id": "c1", "function": {"name": "add", "arguments": "{oops"}}
    body = stream_of({"choices": [{"delta": {"tool_calls": [piece]}}]})
    result = await complete(provider(lambda request: httpx.Response(200, text=body)))
    assert result.tool_calls[0].input == {INVALID_ARGUMENTS: "{oops"}


async def test_request_has_the_key_tools_and_history():
    """The wire format carries tools, tool results and the bearer key."""
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content), auth=request.headers["authorization"])
        return httpx.Response(200, text=stream_of({"choices": []}))

    call = ToolCall(id="c1", name="add", input={"a": 1})
    messages = [
        Message(role="assistant", tool_calls=(call,)),
        Message(role="tool", content="2", tool_call_id="c1"),
    ]
    tools = [{"name": "add", "description": "d", "input_schema": {"type": "object"}}]
    await complete(provider(handler), messages, tools)
    assert seen["auth"] == "Bearer sk-test"
    assert seen["max_tokens"] == 50 and seen["stream"] is True
    assert seen["tools"][0]["function"]["parameters"] == {"type": "object"}
    assert seen["messages"][0]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    assert seen["messages"][1]["tool_call_id"] == "c1"


@pytest.mark.parametrize(("status", "is_retryable"), [(429, True), (503, True), (400, False)])
async def test_http_errors_carry_status_and_message(status, is_retryable):
    """A failed response says what failed and whether to retry."""
    llm = provider(lambda request: httpx.Response(status, text="no credits"))
    with pytest.raises(ProviderError, match="no credits") as caught:
        await complete(llm)
    assert (caught.value.status, caught.value.is_retryable) == (status, is_retryable)


async def test_error_inside_the_stream():
    """The service can fail after the response started."""
    body = stream_of({"error": {"code": 502, "message": "upstream"}})
    with pytest.raises(ProviderError, match="upstream") as caught:
        await complete(provider(lambda request: httpx.Response(200, text=body)))
    assert caught.value.is_retryable


async def test_timeout_is_retryable():
    """A timeout becomes a retryable provider error."""

    def handler(request):
        raise httpx.ReadTimeout("slow")

    with runtime.settings(request_timeout=1.0), pytest.raises(ProviderError) as caught:
        await complete(provider(handler))
    assert caught.value.is_retryable


def test_key_comes_from_the_environment(monkeypatch):
    """The environment fills in a missing key, and the key is a known secret."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env")
    assert OpenRouter().secrets == ("sk-env",)


def test_missing_key_raises(monkeypatch):
    """No key at all is an error at construction."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
        OpenRouter()

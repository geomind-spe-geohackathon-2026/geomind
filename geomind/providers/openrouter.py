"""The OpenRouter service: streaming chat completions over HTTP."""

import json
import os

import httpx

from geomind import runtime
from geomind.errors import ProviderError
from geomind.types import Completion, ToolCall, Usage

BASE_URL = "https://openrouter.ai/api/v1"
INVALID_ARGUMENTS = "invalid_json_arguments"


def is_retryable_status(status):
    """Tell whether an HTTP status says to try again."""
    return status == 429 or status >= 500


def _message_json(message):
    """Return one message in the wire format."""
    wire = {"role": message.role, "content": message.content}
    if message.tool_call_id is not None:
        wire["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.input)},
            }
            for call in message.tool_calls
        ]
    return wire


def _tool_json(tool):
    """Return one tool schema in the wire format."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


def _parse_arguments(text):
    """Return tool arguments; invalid JSON stays visible, so validation sends it back."""
    try:
        return json.loads(text) if text else {}
    except json.JSONDecodeError:
        return {INVALID_ARGUMENTS: text}


class _Stream:
    """Collect the chunks of one streamed completion."""

    def __init__(self, on_text):
        """Start empty."""
        self.on_text = on_text
        self.text = []
        self.calls = {}
        self.usage = Usage()
        self.raw = {}

    def add_line(self, line):
        """Handle one line of the server-sent stream."""
        if not line.startswith("data: ") or line == "data: [DONE]":
            return
        chunk = json.loads(line.removeprefix("data: "))
        if "error" in chunk:
            _raise_api_error(chunk["error"])
        self.raw.update({key: chunk[key] for key in ("id", "model") if key in chunk})
        if chunk.get("usage"):
            self._add_usage(chunk["usage"])
        for choice in chunk.get("choices", ()):
            self._add_delta(choice.get("delta", {}))
            if choice.get("finish_reason"):
                self.raw["finish_reason"] = choice["finish_reason"]

    def _add_usage(self, usage):
        """Keep the usage the service reports, with its cost."""
        self.usage = Usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cost=usage.get("cost") or 0.0,
        )

    def _add_delta(self, delta):
        """Add streamed text and pieces of tool calls."""
        if delta.get("content"):
            self.text.append(delta["content"])
            if self.on_text is not None:
                self.on_text(delta["content"])
        for piece in delta.get("tool_calls") or ():
            call = self.calls.setdefault(piece["index"], {"id": "", "name": "", "arguments": ""})
            function = piece.get("function", {})
            call["id"] = piece.get("id") or call["id"]
            call["name"] = function.get("name") or call["name"]
            call["arguments"] += function.get("arguments") or ""

    def completion(self, model):
        """Return the finished completion."""
        calls = tuple(
            ToolCall(id=call["id"], name=call["name"], input=_parse_arguments(call["arguments"]))
            for _, call in sorted(self.calls.items())
        )
        return Completion(
            text="".join(self.text),
            tool_calls=calls,
            usage=self.usage,
            model=self.raw.get("model", model),
            raw=self.raw,
        )


def _raise_api_error(error):
    """Raise the error a stream or a response body reports."""
    status = error.get("code")
    is_status = isinstance(status, int)
    raise ProviderError(
        f"OpenRouter: status = {status}; {error.get('message', 'unknown error')}",
        status=status if is_status else None,
        is_retryable=is_status and is_retryable_status(status),
    )


class OpenRouter:
    """Streams with ``httpx.AsyncClient`` and fills usage, including cost, from the response.

    ``transport`` replaces the network, for tests.
    """

    def __init__(self, api_key=None, base_url=BASE_URL, transport=None):
        """Read ``OPENROUTER_API_KEY`` when no key is given."""
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ProviderError("OpenRouter: api_key = None; set OPENROUTER_API_KEY or pass one")
        self.base_url = base_url
        self.transport = transport

    @property
    def secrets(self):
        """Return the key, to redact from every event."""
        return (self.api_key,)

    def _body(self, messages, tools, model, settings):
        """Return the JSON of one request."""
        body = {
            "model": model,
            "messages": [_message_json(message) for message in messages],
            "stream": True,
            "usage": {"include": True},
            "temperature": settings.get("temperature", 0),
        }
        if tools:
            body["tools"] = [_tool_json(tool) for tool in tools]
        if settings.get("max_tokens") is not None:
            body["max_tokens"] = settings["max_tokens"]
        return body

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Return the completion of one streamed call."""
        stream = _Stream(on_text)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        client = httpx.AsyncClient(
            transport=self.transport, timeout=runtime.get("request_timeout"), headers=headers
        )
        try:
            async with client:
                await self._read(client, self._body(messages, tools, model, settings), stream)
        except httpx.TimeoutException as error:
            raise ProviderError(f"OpenRouter: timed out: {error!r}", is_retryable=True) from error
        except httpx.TransportError as error:
            raise ProviderError(f"OpenRouter: {error!r}", is_retryable=True) from error
        return stream.completion(model)

    async def _read(self, client, body, stream):
        """Send one request and feed its lines to ``stream``."""
        url = f"{self.base_url}/chat/completions"
        async with client.stream("POST", url, json=body) as response:
            if response.status_code != 200:
                await self._raise_status(response)
            async for line in response.aiter_lines():
                stream.add_line(line)

    async def _raise_status(self, response):
        """Raise the error of a failed response."""
        text = (await response.aread()).decode(errors="replace")
        raise ProviderError(
            f"OpenRouter: status = {response.status_code}; {text[:500]}",
            status=response.status_code,
            is_retryable=is_retryable_status(response.status_code),
        )

"""A small MCP client: ``initialize``, ``tools/list`` and ``tools/call`` over HTTP or SSE.

``http`` is the streamable HTTP transport (each JSON-RPC request a POST, the answer JSON or an
event stream); ``sse`` is the older one (a GET stream that names the URL to POST to, the answers
coming on the stream). Header values are secrets: they are sent and never logged, stored, shown
in an error or replayed.
"""

import asyncio
import json
import re
from typing import Literal
from urllib.parse import urljoin

import httpx
import pydantic
from pydantic import field_validator

from geomind import runtime
from geomind.errors import GeomindError
from geomind.types import Record

PROTOCOL = "2025-03-26"
"""The MCP protocol version geomind asks for."""
CLIENT = {"name": "geomind", "version": "0.4"}
NAME = re.compile(r"^[a-z0-9_-]{1,32}$")
ACCEPT = "application/json, text/event-stream"


class McpError(GeomindError):
    """An MCP server failed: ``code`` is ``unreachable``, ``auth_refused`` or ``bad_response``."""

    def __init__(self, message, *, code):
        """Keep the message, which names no header value, and the code."""
        super().__init__(message)
        self.code = code


class Server(Record):
    """One MCP server: ``name`` (``[a-z0-9_-]{1,32}``), ``url``, ``transport`` and ``headers``.

    The header values are secrets: ``repr`` and ``public`` leave them out.
    """

    name: str
    url: str
    transport: Literal["http", "sse"]
    headers: dict[str, str] = {}

    @field_validator("name")
    @classmethod
    def _checked_name(cls, name):
        """Refuse a name a tool name cannot carry."""
        if not NAME.match(name):
            raise ValueError(f"name = {name!r}; expected [a-z0-9_-]{{1,32}}")
        return name

    def __repr__(self):
        """Show the server without its header values."""
        return f"Server(name={self.name!r}, url={self.url!r}, transport={self.transport!r})"

    def public(self):
        """Return the server as it may be shown or stored: the header names only."""
        return {
            "name": self.name,
            "url": self.url,
            "transport": self.transport,
            "headers": sorted(self.headers),
        }


def servers_from_text(text):
    """Return the servers of ``GEOMIND_MCP_SERVERS``, a JSON list of server objects.

    Each is ``{name, url, transport, headers}``.
    """
    try:
        items = json.loads(text)
        return [Server.model_validate(item) for item in items]
    except (ValueError, TypeError, pydantic.ValidationError) as error:
        raise McpError(
            f"GEOMIND_MCP_SERVERS: {type(error).__name__}", code="bad_response"
        ) from error


def failure(server, error):
    """Return the ``McpError`` of a transport failure, naming the server, never a header."""
    if isinstance(error, McpError):
        return error
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403):
        return McpError(f"{server.name}: the server refused the credentials", code="auth_refused")
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        return McpError(f"{server.name}: HTTP {status}", code="bad_response")
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
        return McpError(f"{server.name}: unreachable ({type(error).__name__})", code="unreachable")
    return McpError(f"{server.name}: {type(error).__name__}", code="bad_response")


def answer_of(server, message, number):
    """Return the ``result`` of the JSON-RPC answer ``number``, or raise ``bad_response``."""
    if not isinstance(message, dict) or message.get("id") != number:
        raise McpError(f"{server.name}: no answer to request {number}", code="bad_response")
    if "error" in message:
        error = message["error"] or {}
        raise McpError(f"{server.name}: {error.get('message', 'error')}", code="bad_response")
    return message.get("result") or {}


def events_of(text):
    """Return the ``(event, data)`` pairs of a server-sent event stream's text."""
    found = []
    for block in re.split(r"\r?\n\r?\n", text):
        event, data = "message", []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            found.append((event, "\n".join(data)))
    return found


class McpClient:
    """Talk to one server for the life of a ``with`` block; ``timeout`` in seconds."""

    def __init__(self, server, timeout, transport=None):
        """Keep the server, the timeout and an optional httpx transport, for tests."""
        self.server = server
        self.timeout = timeout
        self.transport = transport
        self.number = 0
        self.session_id = None
        self.post_url = None
        self.client = None

    async def __aenter__(self):
        """Open the connection and ``initialize``."""
        self.client = httpx.AsyncClient(timeout=self.timeout, transport=self.transport)
        try:
            await self.request(
                "initialize",
                {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": CLIENT},
            )
            await self.notify("notifications/initialized")
        except Exception:
            await self.client.aclose()
            raise
        return self

    async def __aexit__(self, *exc):
        """Close the connection."""
        await self.client.aclose()

    def headers(self):
        """Return the headers of a request: the server's, the session's and what MCP asks."""
        found = {**self.server.headers, "Accept": ACCEPT, "Content-Type": "application/json"}
        if self.session_id:
            found["Mcp-Session-Id"] = self.session_id
        return found

    async def request(self, method, params):
        """Send one JSON-RPC request and return its ``result``."""
        self.number += 1
        body = {"jsonrpc": "2.0", "id": self.number, "method": method, "params": params}
        try:
            if self.server.transport == "sse":
                return await self._over_sse(body)
            return await self._over_http(body)
        except Exception as error:
            raise failure(self.server, error) from None

    async def notify(self, method):
        """Send one JSON-RPC notification, which has no answer."""
        body = {"jsonrpc": "2.0", "method": method}
        url = self.post_url or self.server.url
        try:
            response = await self.client.post(url, json=body, headers=self.headers())
            if response.status_code >= 400:
                response.raise_for_status()
        except Exception as error:
            raise failure(self.server, error) from None

    async def _over_http(self, body):
        """POST a request; read the answer as JSON or as an event stream."""
        response = await self.client.post(self.server.url, json=body, headers=self.headers())
        response.raise_for_status()
        self.session_id = response.headers.get("mcp-session-id", self.session_id)
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            messages = [json.loads(data) for _, data in events_of(response.text)]
            message = next((item for item in messages if item.get("id") == body["id"]), None)
        else:
            message = response.json()
        return answer_of(self.server, message, body["id"])

    async def _over_sse(self, body):
        """Open the stream, POST to the URL it names, and read the answer on the stream."""
        async with self.client.stream("GET", self.server.url, headers=self.headers()) as stream:
            stream.raise_for_status()
            lines = stream.aiter_lines()
            endpoint = await next_event(lines, "endpoint")
            self.post_url = urljoin(self.server.url, endpoint)
            posted = await self.client.post(self.post_url, json=body, headers=self.headers())
            posted.raise_for_status()
            while True:
                message = json.loads(await next_event(lines, "message"))
                if message.get("id") == body["id"]:
                    return answer_of(self.server, message, body["id"])

    async def list_tools(self):
        """Return the server's tools as ``[{name, description, read_only, input_schema}]``."""
        result = await self.request("tools/list", {})
        return [tool_row(item) for item in result.get("tools") or []]

    async def call_tool(self, name, arguments):
        """Call one tool; return its text, its structured content and whether it failed."""
        result = await self.request("tools/call", {"name": name, "arguments": arguments})
        texts = [
            part.get("text", "")
            for part in result.get("content") or []
            if part.get("type") == "text"
        ]
        return {
            "text": "\n".join(texts),
            "structured": result.get("structuredContent"),
            "is_error": bool(result.get("isError")),
        }


async def next_event(lines, wanted):
    """Return the data of the next event of kind ``wanted`` on an event stream."""
    event, data = "message", []
    async for line in lines:
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())
        elif not line.strip() and data:
            if event == wanted:
                return "\n".join(data)
            event, data = "message", []
    raise McpError("the event stream ended before an answer", code="bad_response")


def tool_row(item):
    """Return one tool of ``tools/list`` as geomind keeps it."""
    hints = item.get("annotations") or {}
    return {
        "name": item.get("name", ""),
        "description": item.get("description") or "",
        "read_only": bool(hints.get("readOnlyHint", False)),
        "input_schema": item.get("inputSchema") or {"type": "object", "properties": {}},
    }


def timeout_setting():
    """Return ``mcp_timeout``, seconds, or refuse naming ``GEOMIND_MCP_TIMEOUT``."""
    timeout = runtime.get("mcp_timeout")
    if timeout is None:
        raise McpError("mcp: GEOMIND_MCP_TIMEOUT not set; expected seconds", code="unreachable")
    return timeout


def list_tools(server, transport=None):
    """Return the tools of one server as ``[{name, description, read_only}]``; sync.

    ``read_only`` is the tool's ``readOnlyHint``, false when it gives none. A failure raises
    ``McpError`` with ``unreachable``, ``auth_refused`` or ``bad_response``.
    """

    async def listed():
        async with McpClient(server, timeout_setting(), transport) as client:
            return await client.list_tools()

    rows = asyncio.run(listed())
    return [{key: row[key] for key in ("name", "description", "read_only")} for row in rows]

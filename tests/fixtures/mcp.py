"""A fake MCP server over httpx's ``MockTransport``, for the client and the tools."""

import json
from pathlib import Path

import httpx

from geomind.mcp import Server

SECRET = "sk-secret-header-value"
TOOLS = [
    {
        "name": "price",
        "description": "Return the gas price of a market.",
        "inputSchema": {"type": "object", "properties": {"market": {"type": "string"}}},
        "annotations": {"readOnlyHint": True},
    },
    {"name": "order", "description": "Place an order.", "inputSchema": {"type": "object"}},
]


OPEN_METEO = Path(__file__).parent / "mcp_open_meteo"
"""The tools of the open-meteo server and two of its answers, recorded in the e2e runs."""


def open_meteo():
    """Return ``(tools, answers)`` of the recorded open-meteo server, in the wire shape."""
    tools = json.loads((OPEN_METEO / "tools.json").read_text())
    answers = json.loads((OPEN_METEO / "answers.json").read_text())
    return tools, answers


def recorded_answer(body, tools, answers):
    """Return the JSON-RPC answer of the recorded server: its tools and its recorded answers."""
    method, number = body.get("method"), body.get("id")
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": number, "result": {"tools": tools}}
    name = body["params"]["name"]
    if name in answers:
        found = answers[name]
        content = [{"type": "text", "text": found["text"]}]
        result = {"content": content, "structuredContent": found["structured"]}
        return {"jsonrpc": "2.0", "id": number, "result": result}
    text = [{"type": "text", "text": f"Error: Parameter 'start_date' is out of range for {name}"}]
    return {"jsonrpc": "2.0", "id": number, "result": {"content": text, "isError": True}}


def answer(body, recorded=None):
    """Return the JSON-RPC answer of one request, or ``None`` for a notification.

    ``recorded`` is ``(tools, answers)`` of a recorded server, answered in place of the market.
    """
    method, number = body.get("method"), body.get("id")
    if number is None:
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": number, "result": {"protocolVersion": "2025-03-26"}}
    if recorded is not None:
        return recorded_answer(body, *recorded)
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": number, "result": {"tools": TOOLS}}
    if method == "tools/call" and "market" not in body["params"]["arguments"]:
        error = {"code": -32602, "message": "Invalid params: market is required"}
        return {"jsonrpc": "2.0", "id": number, "error": error}
    if method == "tools/call" and body["params"]["name"] == "price":
        market = body["params"]["arguments"].get("market", "?")
        content = [{"type": "text", "text": f"{market}: 31.5 EUR/MWh"}]
        result = {"content": content, "structuredContent": {"value": 31.5, "unit": "EUR/MWh"}}
        return {"jsonrpc": "2.0", "id": number, "result": result}
    return {"jsonrpc": "2.0", "id": number, "result": {"content": [], "isError": True}}


def http_server(refuse=False, stream=False, recorded=None):
    """Return a transport of the streamable HTTP server; ``refuse`` answers 401.

    ``recorded`` is ``(tools, answers)`` of a recorded server (``open_meteo()``).
    """

    def handle(request):
        if refuse or request.headers.get("authorization") != f"Bearer {SECRET}":
            return httpx.Response(401)
        reply = answer(json.loads(request.content), recorded)
        if reply is None:
            return httpx.Response(202)
        if stream:
            text = f"event: message\ndata: {json.dumps(reply)}\n\n"
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=reply, headers={"mcp-session-id": "s1"})

    return httpx.MockTransport(handle)


def sse_server():
    """Return a transport of the older SSE server: the answer comes on the GET stream."""
    pending = []

    def handle(request):
        if request.method == "POST":
            reply = answer(json.loads(request.content))
            if reply is not None:
                pending.append(reply)
            return httpx.Response(202)
        events = "event: endpoint\ndata: /messages?session=1\n\n"
        return httpx.Response(200, stream=Replies(events, pending))

    return httpx.MockTransport(handle)


class Replies(httpx.AsyncByteStream):
    """The GET stream: the endpoint first, then each answer the POSTs left."""

    def __init__(self, first, pending):
        """Keep the first event and the answers to come."""
        self.first = first
        self.pending = pending

    async def __aiter__(self):
        """Yield the endpoint, then the next answer once a POST left one."""
        yield self.first.encode()
        import asyncio

        for _ in range(200):
            if self.pending:
                yield f"event: message\ndata: {json.dumps(self.pending.pop(0))}\n\n".encode()
                return
            await asyncio.sleep(0)


def server(transport="http", name="market"):
    """Return the server the fake answers as, with its secret header."""
    return Server(
        name=name,
        url="https://mcp.example/mcp",
        transport=transport,
        headers={"Authorization": f"Bearer {SECRET}"},
    )

"""A fake MCP server over httpx's ``MockTransport``, for the client and the tools."""

import json

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


def answer(body):
    """Return the JSON-RPC answer of one request, or ``None`` for a notification."""
    method, number = body.get("method"), body.get("id")
    if number is None:
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": number, "result": {"protocolVersion": "2025-03-26"}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": number, "result": {"tools": TOOLS}}
    if method == "tools/call" and body["params"]["name"] == "price":
        market = body["params"]["arguments"].get("market", "?")
        content = [{"type": "text", "text": f"{market}: 31.5 EUR/MWh"}]
        result = {"content": content, "structuredContent": {"value": 31.5, "unit": "EUR/MWh"}}
        return {"jsonrpc": "2.0", "id": number, "result": result}
    return {"jsonrpc": "2.0", "id": number, "result": {"content": [], "isError": True}}


def http_server(refuse=False, stream=False):
    """Return a transport of the streamable HTTP server; ``refuse`` answers 401."""

    def handle(request):
        if refuse or request.headers.get("authorization") != f"Bearer {SECRET}":
            return httpx.Response(401)
        reply = answer(json.loads(request.content))
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


def server(transport="http"):
    """Return the server the fake answers as, with its secret header."""
    return Server(
        name="market",
        url="https://mcp.example/mcp",
        transport=transport,
        headers={"Authorization": f"Bearer {SECRET}"},
    )

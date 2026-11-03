"""The MCP client: initialize, tools/list and tools/call over HTTP and SSE."""

import pytest

from geomind import runtime
from geomind.mcp import McpClient, McpError, Server, list_tools, servers_from_text
from tests.fixtures.mcp import SECRET, http_server, server, sse_server


def test_list_tools_gives_name_description_and_read_only():
    """``readOnlyHint`` makes a tool read-only; a tool without it is not."""
    with runtime.settings(mcp_timeout=5):
        rows = list_tools(server(), http_server())
    assert rows == [
        {"name": "price", "description": "Return the gas price of a market.", "read_only": True},
        {"name": "order", "description": "Place an order.", "read_only": False},
    ]


@pytest.mark.parametrize("transport", ["json", "stream", "sse"])
async def test_a_tool_is_called_over_each_transport(transport):
    """The text and the structured content come back, over JSON, an event stream or SSE."""
    kind = "sse" if transport == "sse" else "http"
    mock = sse_server() if transport == "sse" else http_server(stream=transport == "stream")
    async with McpClient(server(kind), 5, mock) as client:
        answer = await client.call_tool("price", {"market": "TTF"})
    assert answer["text"] == "TTF: 31.5 EUR/MWh" and answer["structured"]["value"] == 31.5


async def test_refused_credentials_are_auth_refused_and_name_no_header():
    """A 401 is ``auth_refused``; the error never shows the header's value."""
    with pytest.raises(McpError) as raised:
        async with McpClient(server(), 5, http_server(refuse=True)):
            pass
    assert raised.value.code == "auth_refused" and SECRET not in str(raised.value)


def test_a_server_is_named_for_a_tool_name_and_hides_its_headers():
    """A name with a dot is refused; ``repr`` and ``public`` show no header value."""
    with pytest.raises(ValueError):
        Server(name="a.b", url="https://x", transport="http")
    shown = server()
    assert SECRET not in repr(shown) and SECRET not in str(shown.public())
    assert servers_from_text("[]") == []
    with pytest.raises(McpError):
        servers_from_text("not json")


def test_list_tools_needs_the_timeout():
    """``GEOMIND_MCP_TIMEOUT`` has no default."""
    with runtime.settings(mcp_timeout=None):
        with pytest.raises(McpError, match="GEOMIND_MCP_TIMEOUT"):
            list_tools(server(), http_server())

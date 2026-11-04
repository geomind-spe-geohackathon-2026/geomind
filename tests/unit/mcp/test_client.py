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


def as_dict(item):
    """Return a server as ``Workspace.mcp``'s contract names it: a plain dict."""
    return {
        "name": item.name,
        "url": item.url,
        "transport": item.transport,
        "headers": dict(item.headers),
    }


def test_list_tools_takes_the_dict_the_workspace_contract_names():
    """B10: ``list_tools({name, url, transport, headers})`` failed with an AttributeError."""
    with runtime.settings(mcp_timeout=5):
        rows = list_tools(as_dict(server()), http_server())
    assert [row["name"] for row in rows] == ["price", "order"]


async def test_a_client_takes_a_dict_and_a_bad_one_names_the_server_never_a_header():
    """A dict works as a ``Server``; a bad one is ``bad_response`` naming the server and field."""
    async with McpClient(as_dict(server()), 5, http_server()) as client:
        answer = await client.call_tool("price", {"market": "TTF"})
    assert answer["text"].startswith("TTF")
    bad = {**as_dict(server()), "transport": "websocket"}
    with pytest.raises(McpError) as raised:
        McpClient(bad, 5, http_server())
    message = str(raised.value)
    assert raised.value.code == "bad_response" and message.startswith("market:")
    assert "transport" in message and SECRET not in message


def test_failure_keeps_the_real_error_and_names_the_server_when_it_can():
    """B10: ``failure`` read ``server.name`` blindly, and its AttributeError hid the real error."""
    from geomind.mcp.client import failure

    for given, label in ((server(), "market"), ({"name": "x"}, "x"), ({"url": "u"}, "mcp server")):
        error = failure(given, ValueError("the real cause"))
        assert str(error).startswith(f"{label}:") and "the real cause" in str(error)
        assert error.code == "bad_response" and SECRET not in str(error)
    plain = object()
    assert "the real cause" in str(failure(plain, KeyError("the real cause")))

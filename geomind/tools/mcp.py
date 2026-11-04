"""The run's MCP servers, offered as three tools: ``list_mcp``, ``read_mcp`` and ``call_mcp``.

``list_mcp`` lists the servers and their tools, each with ``read_only`` (its ``readOnlyHint``).
``read_mcp`` calls a read-only tool only; ``call_mcp`` calls any, and a call of a tool that is not
read-only has the effect ``external``, so the ``ask`` mode asks for its approval. Every answer
carries its origin (server, tool, time): a value from it enters the case or the plant only after
the user confirms it, as any value no project file gives.

NOTE: before 0.4.22.dev42 each server tool was a tool of its own, ``<server>__<tool>``; a replay
of such a log reuses the recorded answers through ``RecordedMcpTool``.
"""

import copy
import difflib
from datetime import datetime, timezone
from typing import Any

from geomind.errors import ToolError
from geomind.mcp import McpClient, McpError
from geomind.tools.base import Tool, tool
from geomind.utils.strings import join_names

SEPARATOR = "__"
"""Between a server's name and its tool's in the names of logs before 0.4.22.dev42."""
REACHING = ("list_mcp", "read_mcp", "call_mcp")
"""The tools whose ``server`` input names the server a call reaches."""


def server_of(name, tool_input=None):
    """Return the server a call reaches, or ``None`` for a call that reaches none.

    That is the ``server`` input of the three tools, or the prefix of an old
    ``<server>__<tool>`` name.
    """
    if name in REACHING:
        server = (tool_input or {}).get("server")
        return server if isinstance(server, str) else None
    return name.split(SEPARATOR, 1)[0] if SEPARATOR in name else None


class Servers:
    """The servers of a run and their tools, listed once when the run starts."""

    def __init__(self, servers, rows, timeout, transport=None):
        """Keep each server, its rows of ``tools/list`` by name, the timeout and the transport."""
        self.servers = {server.name: server for server in servers}
        self.rows = {name: {row["name"]: row for row in items} for name, items in rows.items()}
        self.timeout = timeout
        self.transport = transport

    def listing(self, tool_name, server=None):
        """Return ``[{server, name, description, read_only, input_schema}]`` of one or all."""
        names = [self._server(tool_name, server)] if server is not None else list(self.rows)
        return [{"server": name, **row} for name in names for row in self.rows[name].values()]

    def _server(self, tool_name, server):
        """Return a server's name, or raise ``unknown_name`` with the servers."""
        if server in self.servers:
            return server
        raise ToolError(
            f"{tool_name}: server = {server!r}; expected one of {join_names(self.servers)}",
            code="unknown_name",
            path="server",
            suggestions=difflib.get_close_matches(str(server), list(self.servers)),
        )

    def row(self, tool_name, server, name):
        """Return the row of one tool of one server, or raise ``unknown_name`` with its tools."""
        rows = self.rows[self._server(tool_name, server)]
        if name in rows:
            return rows[name]
        raise ToolError(
            f"{tool_name}: tool = {name!r}; expected one of {join_names(rows)} of {server}",
            code="unknown_name",
            path="tool",
            suggestions=difflib.get_close_matches(str(name), list(rows)),
        )

    async def call(self, tool_name, server, name, arguments):
        """Call one tool through a new connection; its text, structured content and origin."""
        self.row(tool_name, server, name)
        origin = {
            "server": server,
            "tool": name,
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        try:
            async with McpClient(self.servers[server], self.timeout, self.transport) as client:
                answer = await client.call_tool(name, arguments)
        except McpError as error:
            raise ToolError(f"{tool_name}: {error}", code="mcp_unavailable") from None
        if answer["is_error"]:
            raise ToolError(f"{tool_name}: {server}/{name}: {answer['text'] or 'the tool failed'}")
        return {"text": answer["text"], "structured": answer["structured"], "origin": origin}


def servers_of(context, tool_name):
    """Return the run's ``Servers``, or raise ``mcp_unavailable`` for a run without one."""
    engine = getattr(context.session, "engine", None)
    servers = getattr(engine, "mcp_servers", None)
    if not servers or not servers.servers:
        raise ToolError(
            f"{tool_name}: this run has no MCP server; work from the files, the knowledge base "
            "and the user",
            code="mcp_unavailable",
        )
    return servers


class ServerTool(Tool):
    """A tool over the run's servers: a server's answer may change, so a replay reuses it."""

    def __init__(self, made):
        """Take the definition a ``@tool`` function made."""
        self.__dict__.update(made.__dict__)

    @property
    def is_pure(self):
        """Return that a replay reuses the recorded answer and never reaches a server."""
        return False


class CallTool(ServerTool):
    """``call_mcp``: a call of a read-only tool reads; any other is ``external``."""

    def for_call(self, session, tool_input):
        """Return this tool with the effect of the one call, for the permissions to decide."""
        servers = getattr(getattr(session, "engine", None), "mcp_servers", None)
        rows = servers.rows if servers else {}
        row = rows.get(tool_input.get("server"), {}).get(tool_input.get("tool"))
        if row is None or not row["read_only"]:
            return self
        reading = copy.copy(self)
        reading.effect = "read"
        return reading


@tool(effect="read")
def list_mcp(context, server: str | None = None):
    """List the connected MCP servers and their tools, of one ``server`` or of all.

    Returns ``tools``, each ``{server, name, description, read_only, input_schema}``;
    ``input_schema`` is the ``arguments`` the tool takes. Call a read-only tool with
    ``read_mcp``, any other with ``call_mcp``.
    """
    return {"tools": servers_of(context, "list_mcp").listing("list_mcp", server)}


@tool(effect="read")
async def read_mcp(context, server: str, tool: str, arguments: dict[str, Any]):
    """Call a read-only tool of a connected MCP server, with its ``arguments``.

    Returns ``text``, ``structured`` and ``origin`` (server, tool, time): cite a value with its
    origin. A tool that is not read-only answers ``not_read_only``: call it with ``call_mcp``.
    """
    servers = servers_of(context, "read_mcp")
    if not servers.row("read_mcp", server, tool)["read_only"]:
        raise ToolError(
            f"read_mcp: {server}/{tool} is not read-only; call it with call_mcp, which asks the "
            "user's approval",
            code="not_read_only",
            path="tool",
        )
    return await servers.call("read_mcp", server, tool, arguments)


@tool(effect="external", idempotent=False)
async def call_mcp(context, server: str, tool: str, arguments: dict[str, Any]):
    """Call any tool of a connected MCP server, with its ``arguments``.

    A tool that is not read-only asks the user's approval before it runs. Returns ``text``,
    ``structured`` and ``origin`` (server, tool, time): cite a value with its origin.
    """
    return await servers_of(context, "call_mcp").call("call_mcp", server, tool, arguments)


list_mcp = ServerTool(list_mcp)
read_mcp = ServerTool(read_mcp)
call_mcp = CallTool(call_mcp)
MCP_TOOLS = {"list_mcp": list_mcp, "read_mcp": read_mcp, "call_mcp": call_mcp}
"""The tools an agent with tools is offered when the run has a server."""


class RecordedMcpTool(Tool):
    """A ``<server>__<tool>`` of a log before 0.4.22.dev42 in a replay: reused, never run."""

    def __init__(self, name):
        """Stand for ``name`` of the recorded run."""
        super().__init__(
            name,
            "a tool of an MCP server",
            {"type": "object"},
            self._call,
            effect="external",
            idempotent=False,
        )

    @property
    def is_pure(self):
        """Return that a recorded call is never run again."""
        return False

    async def _call(self, context, **arguments):
        """Refuse: a replay never reaches a server."""
        raise ToolError(f"{self.name}: a replay does not call MCP servers", code="mcp_unavailable")


async def load_servers(servers, timeout, transport=None):
    """Return ``(Servers, [(server, McpError)])``: the servers that answered, with their tools."""
    answered, rows, failures = [], {}, []
    for server in servers:
        try:
            async with McpClient(server, timeout, transport) as client:
                rows[server.name] = await client.list_tools()
        except McpError as error:
            failures.append((server, error))
            continue
        answered.append(server)
    return Servers(answered, rows, timeout, transport), failures

"""The tools of the MCP servers a run is given, offered to the agents as ``<server>__<tool>``.

A read-only tool (its ``readOnlyHint``) has the effect ``read``; any other ``external``, so the
``ask`` mode asks for its approval. Every result carries its origin (server, tool, time): a value
from it enters the case or the plant only after the user confirms it, as any value no project
file gives.
"""

from datetime import datetime, timezone

from geomind.errors import ToolError
from geomind.mcp import McpClient, McpError
from geomind.tools.base import Tool

SEPARATOR = "__"
"""Between a server's name and its tool's: OpenAI function names allow no dot."""


def server_of(name):
    """Return the server a tool name of a run belongs to, or ``None`` for a geomind tool."""
    return name.split(SEPARATOR, 1)[0] if SEPARATOR in name else None


class McpTool(Tool):
    """One tool of one MCP server, called through a new connection each time."""

    def __init__(self, server, row, timeout, transport=None):
        """Offer ``row`` of ``tools/list`` as ``<server>__<tool>``."""
        super().__init__(
            f"{server.name}{SEPARATOR}{row['name']}",
            f"[{server.name}] {row['description']}".strip(),
            row["input_schema"],
            self._call,
            effect="read" if row["read_only"] else "external",
            idempotent=row["read_only"],
        )
        self.server = server
        self.tool = row["name"]
        self.timeout = timeout
        self.transport = transport

    @property
    def is_pure(self):
        """Return that a server's answer may change: a replay reuses the recorded one."""
        return False

    async def _call(self, context, **arguments):
        """Call the server's tool; its text, structured content and origin come back."""
        origin = {
            "server": self.server.name,
            "tool": self.tool,
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        try:
            async with McpClient(self.server, self.timeout, self.transport) as client:
                answer = await client.call_tool(self.tool, arguments)
        except McpError as error:
            raise ToolError(f"{self.name}: {error}", code="mcp_unavailable") from None
        if answer["is_error"]:
            raise ToolError(f"{self.name}: {answer['text'] or 'the tool failed'}")
        return {"text": answer["text"], "structured": answer["structured"], "origin": origin}


class RecordedMcpTool(Tool):
    """A tool of a server in a replay: its recorded result is reused, it never runs."""

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


async def load_tools(servers, timeout, transport=None):
    """Return ``({name: McpTool}, [(server, McpError)])`` of every server's tools."""
    tools, failures = {}, []
    for server in servers:
        try:
            async with McpClient(server, timeout, transport) as client:
                rows = await client.list_tools()
        except McpError as error:
            failures.append((server, error))
            continue
        for row in rows:
            tool = McpTool(server, row, timeout, transport)
            tools[tool.name] = tool
    return tools, failures

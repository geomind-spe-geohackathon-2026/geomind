"""The run's MCP servers as tools: ``list_mcp``, ``read_mcp``, ``call_mcp``, ``save_mcp_table``.

``list_mcp`` lists the servers and their tools, each with ``read_only`` (its ``readOnlyHint``)
and its arguments, short enough to stay in the history; ``list_mcp(server, tool)`` gives one tool's
whole ``input_schema``. ``read_mcp`` calls a read-only tool only; ``call_mcp`` calls any, and a call
of a tool that is not read-only has the effect ``external``, so the ``ask`` mode asks for its
approval. A call whose arguments the schema or the server refuses answers with the schema. Every
answer carries its origin (server, tool, time, arguments, the tool's description, ``future``) and
its tables, and is kept as the artifact ``answer``; ``save_mcp_table`` saves one of its tables as
a case file, times in UTC. A value from a server enters the case or the plant only after the user
confirms it, as any value no project file gives.

NOTE: before 0.4.22.dev42 each server tool was a tool of its own, ``<server>__<tool>``; a replay
of such a log reuses the recorded answers through ``RecordedMcpTool``.
"""

import asyncio
import copy
import difflib
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from geomind.errors import ToolError
from geomind.mcp import McpClient, McpError
from geomind.mcp.answers import (
    TEXT_CHARACTERS,
    TIME_COLUMN,
    argument_problem,
    is_future,
    rows_of,
    safe_file_name,
    short_structured,
    summary_of,
    table_csv,
    tables_of,
    tool_outline,
    tzinfo_of,
    zone_of,
)
from geomind.mcp.client import as_server
from geomind.tools.base import Tool, tool
from geomind.tools.stored import STORE_CHARACTERS
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

    def listing(self, tool_name, server=None, name=None):
        """Return the outline of the tools of one server or all, or one tool's whole row.

        The outline is ``[{server, name, read_only, summary, arguments}]``; with ``name`` it is
        ``[{server, name, description, read_only, input_schema}]`` of that tool alone.
        """
        if name is not None:
            if server is None:
                raise ToolError(
                    f"{tool_name}: tool = {name!r} and no server; expected the server too, one of "
                    f"{join_names(self.servers)}",
                    path="server",
                    suggestions=list(self.servers),
                )
            return [{"server": server, **self.row(tool_name, server, name)}]
        names = [self._server(tool_name, server)] if server is not None else list(self.rows)
        return [tool_outline(item, row) for item in names for row in self.rows[item].values()]

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
        """Call one tool through a new connection; its text, structured content and origin.

        Arguments the tool's ``input_schema`` refuses never reach the server; a refusal, the
        schema's or the server's, carries the schema.
        """
        row = self.row(tool_name, server, name)
        problem = argument_problem(row["input_schema"], arguments)
        if problem is not None:
            path, message, suggestions = problem
            raise ToolError(
                f"{tool_name}: {server}/{name}: {message}{schema_note(row)}",
                path=path,
                suggestions=suggestions,
            )
        origin = {
            "server": server,
            "tool": name,
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "arguments": arguments,
            "tool_description": summary_of(row["description"]),
        }
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                async with McpClient(self.servers[server], self.timeout, self.transport) as client:
                    answer = await client.call_tool(name, arguments)
            except McpError as error:
                if error.code == "invalid_arguments":
                    message = f"{tool_name}: {error}{schema_note(row)}"
                    raise ToolError(message, path="arguments") from None
                raise ToolError(f"{tool_name}: {error}", code="mcp_unavailable") from None
            limited = answer["is_error"] and is_rate_limited(answer["text"])
            if not limited or not row["read_only"] or attempt == RATE_LIMIT_RETRIES:
                break
            await asyncio.sleep(RATE_LIMIT_WAIT)
        if answer["is_error"] and limited:
            raise ToolError(
                f"{tool_name}: {server}/{name}: {answer['text']}; still limited after waiting "
                f"{RATE_LIMIT_RETRIES} times {RATE_LIMIT_WAIT} s: do the rest of your work first and "
                "call it again later, once, with every value you need in one call",
                code="rate_limited",
            )
        if answer["is_error"]:
            raise ToolError(
                f"{tool_name}: {server}/{name}: {answer['text'] or 'the tool failed'}"
                f"{schema_note(row)}"
            )
        return {"text": answer["text"], "structured": answer["structured"], "origin": origin}


RATE_LIMIT_WAIT = 61
"""Seconds a read-only call waits after a server's rate limit (Open-Meteo: "try again in one minute")."""
RATE_LIMIT_RETRIES = 2
"""How often a rate-limited read-only call waits and is sent again (QA-050)."""
RATE_LIMITED = re.compile(r"rate limit|limit exceeded|too many requests|try again in", re.I)


def is_rate_limited(text):
    """Tell whether a server's error text says the call hit a rate limit."""
    return bool(text and RATE_LIMITED.search(text))


def schema_note(row):
    """Return the end of a refusal of arguments: the tool's whole ``input_schema``."""
    schema = json.dumps(row["input_schema"], ensure_ascii=False)
    return f". The tool's input_schema: {schema}"


def answer_key(server, name, arguments):
    """Return the artifact key of the answer of one call: the same call has the same key."""
    called = json.dumps([server, name, arguments], sort_keys=True, ensure_ascii=False)
    return f"mcp-{hashlib.sha256(called.encode()).hexdigest()[:16]}"


SHORT_NOTE = (
    "the answer is long: this is its short form. read_stored(reference=<answer>, path=<a table's "
    "path>) reads a part; save_mcp_table(answer, table, file) saves a table as a case file"
)


async def kept_answer(context, called):
    """Return an answer for the model, kept whole as the artifact ``answer``.

    It leads with its origin (``future`` when a date lies after the call), the artifact's key and
    its tables (path, rows, columns, units, time zone, first and last time), so the model sees
    the structured part and its units before the text. A long answer comes back short: the
    structured content without its tables and the head of the text.
    """
    origin, structured, text = called["origin"], called["structured"], called["text"]
    tables = tables_of(structured)
    origin = {**origin, "future": is_future(origin["arguments"], tables, origin["time"])}
    key = answer_key(origin["server"], origin["tool"], origin["arguments"])
    whole = {"origin": origin, "answer": key, "tables": tables, "structured": structured}
    whole["text"] = text
    await context.session.save_artifact(key, whole)
    if len(json.dumps(whole, ensure_ascii=False)) <= STORE_CHARACTERS:
        return whole
    head = text if len(text) <= TEXT_CHARACTERS else text[: TEXT_CHARACTERS - 1] + "…"
    return {**whole, "structured": short_structured(structured), "text": head, "note": SHORT_NOTE}


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


LIST_NOTE = (
    "each tool's arguments are name: type; list_mcp(server, tool) gives one tool's description "
    "and whole input_schema"
)


@tool(effect="read", keeps_result="run")
def list_mcp(context, server: str | None = None, tool: str | None = None):
    """List the connected MCP servers and their tools, of one ``server`` or of all.

    Skill `connectors`.
    """
    listing = servers_of(context, "list_mcp").listing("list_mcp", server, tool)
    return {"tools": listing} if tool is not None else {"tools": listing, "note": LIST_NOTE}


@tool(effect="read", keeps_result="run")
async def read_mcp(context, server: str, tool: str, arguments: dict[str, Any]):
    """Call a read-only tool of a connected MCP server, with its ``arguments``.

    Skill `connectors`.
    """
    servers = servers_of(context, "read_mcp")
    if not servers.row("read_mcp", server, tool)["read_only"]:
        raise ToolError(
            f"read_mcp: {server}/{tool} is not read-only; call it with call_mcp, which asks the "
            "user's approval",
            code="not_read_only",
            path="tool",
        )
    return await kept_answer(context, await servers.call("read_mcp", server, tool, arguments))


@tool(effect="external", idempotent=False, keeps_result="run")
async def call_mcp(context, server: str, tool: str, arguments: dict[str, Any]):
    """Call any tool of a connected MCP server, with its ``arguments``. Skill `connectors`."""
    called = await servers_of(context, "call_mcp").call("call_mcp", server, tool, arguments)
    return await kept_answer(context, called)


def stored_answer(context, answer):
    """Return the whole answer an ``answer`` key names, or raise ``unknown_name``."""
    found = context.session.load_artifact(answer) if answer.startswith("mcp-") else None
    if not isinstance(found, dict) or "origin" not in found:
        raise ToolError(
            f"save_mcp_table: answer = {answer!r}; expected the `answer` of a read_mcp or "
            "call_mcp result, mcp-...",
            code="unknown_name",
            path="answer",
        )
    return found


def table_rows(whole, table):
    """Return the rows of the table at ``table`` of an answer, or raise naming its tables."""
    paths = [item["path"] for item in whole.get("tables") or ()]
    rows = None
    if table in paths:
        rows = rows_of((whole.get("structured") or {}).get(table.removeprefix("structured.")))
    if rows is None:
        raise ToolError(
            f"save_mcp_table: table = {table!r}; expected the path of a table of the answer, one "
            f"of {join_names(paths) if paths else 'none: the answer has no table'}",
            code="unknown_name",
            path="table",
            suggestions=paths,
        )
    if any(TIME_COLUMN not in row for row in rows):
        raise ToolError(
            f"save_mcp_table: table = {table!r} has rows without a {TIME_COLUMN!r} column; "
            "expected a time series, one time per row",
            path="table",
        )
    return rows


def table_zone(whole, time_zone):
    """Return ``(zone name, tzinfo)`` of an answer's times: the answer's, else ``time_zone``."""
    named = zone_of(whole.get("structured"))
    if named is not None and time_zone is not None and time_zone != named:
        raise ToolError(
            f"save_mcp_table: time_zone = {time_zone!r}, but the answer names its times in "
            f"{named!r}; expected no time_zone, or {named!r}",
            path="time_zone",
            suggestions=[named],
        )
    zone = named or time_zone
    if zone is None:
        raise ToolError(
            "save_mcp_table: time_zone = None, and the answer names no time zone; expected the "
            "IANA zone its times are in, as the server's text or the call's arguments give it",
            path="time_zone",
        )
    return zone, tzinfo_of(zone, "save_mcp_table")


@tool(effect="write", reruns_in_replay=True)
async def save_mcp_table(context, answer: str, table: str, file: str, time_zone: str | None = None):
    """Save a table of an MCP answer as a case file, its times in UTC, with its origin beside it.

    Skill `connectors`.
    """
    from geomind.tools.gemini.case import CASE_FILE

    whole = stored_answer(context, answer)
    rows = table_rows(whole, table)
    given, file = file, safe_file_name(file)
    if file is None:
        raise ToolError(
            f"save_mcp_table: file = {given!r}; expected a file name such as 'data/air.csv'",
            path="file",
        )
    zone, tzinfo = table_zone(whole, time_zone)
    try:
        content, columns = table_csv(rows, tzinfo)
    except ValueError as error:
        raise ToolError(
            f"save_mcp_table: table = {table!r}: a time is no ISO date or time ({error})",
            path="table",
        ) from None
    origin_file = f"{file.removesuffix('.csv')}.origin.json"
    origin = {**whole["origin"], "answer": answer, "table": table}
    await context.session.save_artifact(f"{CASE_FILE}{file}", content)
    origin_text = json.dumps(origin, indent=2, ensure_ascii=False).encode()
    await context.session.save_artifact(f"{CASE_FILE}{origin_file}", origin_text)
    [described] = [item for item in whole["tables"] if item["path"] == table]
    units = described["units"] or {}
    lines = content.decode().splitlines()
    return {
        "file": file,
        "origin_file": origin_file,
        "columns": columns,
        "units": {column: units[column] for column in columns if column in units},
        "rows": len(rows),
        "time_zone": {"from": zone, "to": "UTC"},
        "first": lines[1].split(",", 1)[0],
        "last": lines[-1].split(",", 1)[0],
        "origin": whole["origin"],
    }


list_mcp = ServerTool(list_mcp)
read_mcp = ServerTool(read_mcp)
call_mcp = CallTool(call_mcp)
MCP_TOOLS = {
    "list_mcp": list_mcp,
    "read_mcp": read_mcp,
    "call_mcp": call_mcp,
    "save_mcp_table": save_mcp_table,
}
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
    """Return ``(Servers, [(server, McpError)])``: the servers that answered, with their tools.

    Each server is a ``Server`` or the dict ``{name, url, transport, headers}`` of
    ``Workspace.mcp``; a bad one fails alone, as a server that does not answer.
    """
    answered, rows, failures = [], {}, []
    for given in servers:
        try:
            server = as_server(given)
            async with McpClient(server, timeout, transport) as client:
                rows[server.name] = await client.list_tools()
        except McpError as error:
            failures.append((given, error))
            continue
        answered.append(server)
    return Servers(answered, rows, timeout, transport), failures

# MCP

`gd.mcp` is a small client of geomind's own over httpx (`geomind/mcp/client.py`): JSON-RPC
`initialize`, `tools/list` and `tools/call` over the `http` transport (streamable HTTP: a POST,
the answer JSON or an event stream) and the older `sse` transport (a GET stream that names the URL
to POST to). `list_tools(server)` lists one server's tools, `[{name, description, read_only}]`;
a failure is `McpError` with `code` `unreachable`, `auth_refused` or `bad_response`, naming the
server (`mcp server` when it has no name) and never a header value, and keeping the real error's
class and text. A server is a `gd.mcp.Server` or the plain dict `{name, url, transport, headers}`
`Workspace.mcp` names, everywhere one comes in (`list_tools`, `McpClient`, `load_servers`, the
run's `Workspace.mcp`); a bad dict is `bad_response` naming the server and the fields at fault
(`as_server`), and in a run it is left out as a server that does not answer.

A run's servers come from the optional `Workspace.mcp(project_id)` (the command line:
`GEOMIND_MCP_SERVERS`, a JSON list, and `GEOMIND_MCP_TIMEOUT`, seconds, required when a server is
given). `RunSession.ensure_mcp` lists their tools once per engine, at the first step, into
`Engine.mcp_servers` (`Servers`, `geomind/tools/mcp.py`). Every agent that has tools is then
offered three fixed tools (since 0.4.22.dev42; before, one tool per server tool, named
`<server>__<tool>`):

- `list_mcp(server?)`: the servers and their tools, `[{server, name, description, read_only,
  input_schema}]`;
- `read_mcp(server, tool, arguments)`: calls a tool only if it is read-only (`readOnlyHint`);
  another answers `not_read_only` and points to `call_mcp`;
- `call_mcp(server, tool, arguments)`: calls any tool; its effect is that of the tool it calls
  (`Tool.for_call`), `read` for a read-only one and `external` for another, so `ask` asks for
  approval.

A run without a server that answered offers none of them, and a call answers `mcp_unavailable`.
Every call opens its own connection and returns `{text, structured, origin: {server, tool,
time}}`; a failing server is the tool error `mcp_unavailable`, and an unknown server or tool
`unknown_name`. `tool.started` and `tool.finished` carry `mcp`, the server's name (the `server`
input). Header values join the log's secrets: never logged, stored, echoed or replayed. A replay
reuses each recorded answer and reaches no server; a log with the old `<server>__<tool>` names
replays through a stand-in (`RecordedMcpTool`).

A value from a server is cited with its origin and enters the case or the plant only after the
user confirms it (the shared prompt section `MCP`).

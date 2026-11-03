# MCP

`gd.mcp` is a small client of geomind's own over httpx (`geomind/mcp/client.py`): JSON-RPC
`initialize`, `tools/list` and `tools/call` over the `http` transport (streamable HTTP: a POST,
the answer JSON or an event stream) and the older `sse` transport (a GET stream that names the URL
to POST to). `list_tools(server)` lists one server's tools, `[{name, description, read_only}]`;
a failure is `McpError` with `code` `unreachable`, `auth_refused` or `bad_response`, naming the
server and never a header value.

A run's servers come from the optional `Workspace.mcp(project_id)` (the command line:
`GEOMIND_MCP_SERVERS`, a JSON list, and `GEOMIND_MCP_TIMEOUT`, seconds). `RunSession.ensure_mcp`
lists their tools once per engine, at the first step; each becomes an `McpTool` named
`<server>__<tool>` (`geomind/tools/mcp.py`), offered to every agent that has tools. A read-only
tool (`readOnlyHint`) has the effect `read`; any other `external`, so `ask` asks for approval.
Every call opens its own connection and returns `{text, structured, origin: {server, tool,
time}}`; a failure is the tool error `mcp_unavailable`. `tool.started` and `tool.finished` carry
`mcp`, the server's name. Header values join the log's secrets. A replay builds a stand-in
(`RecordedMcpTool`) for each recorded call and reuses its result: no server is reached.

A value from a server is cited with its origin and enters the case or the plant only after the
user confirms it (the shared prompt section `MCP`).

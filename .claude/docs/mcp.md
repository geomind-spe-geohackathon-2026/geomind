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
offered four fixed tools (three since 0.4.22.dev42, `save_mcp_table` since 0.4.24; before, one
tool per server tool, named `<server>__<tool>`):

- `list_mcp(server?, tool?)`: the servers and their tools, an outline short enough to stay in
  the history (the result is kept for the run): `{tools: [{server, name, read_only, summary,
  arguments}], note}`, `summary` the description's first sentence and `arguments` `{name: type}`
  with `required` marked (`geomind/mcp/answers.py`). With `server` and `tool` it is that tool
  alone, `{tools: [{server, name, description, read_only, input_schema}]}` (E2E-4, 0.4.24);
- `read_mcp(server, tool, arguments)`: calls a tool only if it is read-only (`readOnlyHint`);
  another answers `not_read_only` and points to `call_mcp`;
- `call_mcp(server, tool, arguments)`: calls any tool; its effect is that of the tool it calls
  (`Tool.for_call`), `read` for a read-only one and `external` for another, so `ask` asks for
  approval;
- `save_mcp_table(answer, table, file, time_zone?)`: saves a table of an answer as the case file
  `case/<file>` (CSV, `time` in UTC as `YYYY-MM-DDTHH:MM:SSZ`, one column per value) and its
  origin beside it as `case/<stem>.origin.json`; `file` is made safe (each part
  `[A-Za-z0-9._-]`, `.csv` added). The times are local times of the answer's `timezone` (or
  `utc_offset_seconds`), else of `time_zone`; neither is `invalid_input`, never a zone of
  geomind's. `set_case` then names the file and a column as a series (E2E-12, 0.4.24).

A run without a server that answered offers none of them, and a call answers `mcp_unavailable`.
Every call opens its own connection. Arguments that miss a `required` one, or name one the schema
does not when it has `additionalProperties: false`, are refused before the call
(`invalid_input`, `path` `arguments.<name>`, close names in `suggestions`); that refusal, the
server's own (`isError`) and JSON-RPC -32602 (`McpError` code `invalid_arguments`, then
`invalid_input`) end with the tool's whole `input_schema`. A failing server is `mcp_unavailable`,
and an unknown server or tool `unknown_name`.

An answer is `{origin, answer, tables, structured, text}` (kept for the run in the history):
`origin` is `{server, tool, time, arguments, tool_description, future}`, `future` true when a
date of the arguments or of a table lies after the day of the call (a forecast or a projection);
`answer` the key `mcp-<16 hex>` of the whole answer, the same for the same call, saved in the
chat's space and read by `read_stored` and `save_mcp_table`; `tables` `[{path, rows, columns,
units, time_zone, first, last}]` of each table of `structured` (a list of objects, or an object
of equal lists), `units` the server's `<name>_units` beside it. An answer longer than
`STORE_CHARACTERS` comes back short: `structured` without its long values, the head of `text`,
and `note` (E2E-5, E2E-6, 0.4.24). `tool.started` and `tool.finished` carry `mcp`, the server's
name (the `server` input). Header values join the log's secrets: never logged, stored, echoed or
replayed. A replay reuses each recorded answer and reaches no server; `save_mcp_table` runs again
from the recorded `answer`; a log with the old `<server>__<tool>` names replays through a
stand-in (`RecordedMcpTool`).

A value from a server is cited with its origin and enters the case or the plant only after the
user confirms it (the shared prompt section `MCP`).

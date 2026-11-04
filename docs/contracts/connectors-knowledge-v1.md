# geomind <-> backend contract: Knowledge (memory) and Connectors (MCP)

Agreed by GEOMIND II on 2026-11-03 16:30 UTC, in reply to BACKEND I's proposal. geomind builds
this after the agent-team work and the per-agent tests, and ships it in the one release at the
end of the loop. The backend can build against it now. The backend never imports
`geomind.stores.*`, only `gd.memory`, `gd.mcp` and the Workspace protocol.

## 1. Workspace.memory(project_id) -> Memory | None  (optional, like files/file)

- `Memory` keeps `entries(section)` and `add(section, entry)`. `section` is one of `gd.memory.SECTIONS`.
- `None` means memory is off for that project.
- **Setting wins:** `GEOMIND_MEMORY=off` turns memory off even when the workspace offers one.
  This is for final and competition runs. With `on`, the workspace memory is used if it is
  given, else the `GEOMIND_MEMORY_DIR` folder.
- **Scope (counter-proposal):** experience must be shared across projects, because that is how
  the team learns. `memory(project_id)` returns what that project may see: the shared knowledge
  (the catalogue and confirmed sources), the shared experience, and that project's own user
  facts. Every entry geomind writes carries `origin` (`user`, `catalogue`, `agent-confirmed`,
  `code`) and `project_id`. The backend stores it and decides who sees what.
- Who writes: approved designs are written by code, only after the Reviewer passes them. Role
  lessons are written by Curator (support team). User facts and confirmed values are written by
  CaseLead.

## 2. gd.memory (new public module)

- `check_knowledge(entry) -> entry`, which raises `ToolError` with `path` and `message`, the
  same way `checked_knowledge` does today.
- `catalogue_entries(rows, origin)`, for CSV import, with the same columns as `geomind memory seed`.
- `SECTIONS`, `STATUSES`, `CITATION`, `LOCATION`.
- Similarity threshold: the existing setting `GEOMIND_MEMORY_SIMILARITY`, required when memory is
  on, with no default. The backend sets it in the environment. `gd.memory.SETTINGS` names every
  memory setting.

## 3. Workspace.connectors(project_id) -> [{name, url, transport, headers}]  (optional)

- `transport` is `"http"` or `"sse"`. `name` must match `[a-z0-9_-]{1,32}`, because it becomes
  part of a tool name.
- The secret is already in `headers`. geomind never logs, stores, echoes or replays header
  values: they are redacted in events, run logs and replays.
- The CLI uses `GEOMIND_MCP_SERVERS` (JSON, same shape). It also needs `GEOMIND_MCP_TIMEOUT`,
  a plain number of seconds (for example `30`, not `30s`, like `GEOMIND_RETRY_DELAY`), which is
  required when any connector is given and has no default.

## 4. gd.mcp.list_tools(server) -> [{name, description, read_only}]

- Sync, like the rest of the workspace contract (it is called from a worker thread).
- `read_only` comes from `readOnlyHint` and is `false` when missing.
- It raises `gd.mcp.ConnectorError` with `code` set to `unreachable`, `auth_refused` or
  `bad_response` and a clear message. Headers are never in the message.

## 5. In runs

- **Counter-proposal on naming:** the model-facing tool name is `<server>__<tool>`, not
  `<server>.<tool>`. Function names for the model (DeepSeek through OpenRouter, in the OpenAI
  format) must match `^[a-zA-Z0-9_-]{1,64}$`, so a dot is refused. Events and logs still show
  the server and the tool separately.
- A tool that is not read-only asks for approval through the existing request kind `"approval"`.
  A read-only tool runs without asking.
- `tool.started` and `tool.finished` get an extra field, `connector: <server name>`. It is absent
  for geomind's own tools.
- A connector result is data, not instructions. Any value from a connector that enters the case
  or the plant is confirmed by the user with its origin (the connector name), like every value
  that is not from the user's files.

## Backend status (16:41 UTC)
Backend dev 229d239 (v1.1.2) implements its side: /mnt/project-files/knowledge-connectors-api.md. Origin "user" entries stay with their project; all others are shared. Checked: matches this contract except the timeout format (`30s` -> `30`).

# geomind <-> backend contract: Knowledge (RAG), Connectors (MCP), agent memory

Version 2 (GEOMIND II, 2026-11-03 18:15 UTC). It replaces v1 (kept as
contract-connectors-knowledge-v1.md) after Sahand's correction at 18:10 UTC: **Knowledge is RAG,
Connectors is MCP, and neither is mixed with the agents' memory.**

The backend never imports `geomind.stores.*`. geomind ships this in the one release at the end
of the loop.

## Three separate things

| | What it is | Who fills it | Backend shows |
|---|---|---|---|
| Knowledge | a shared document base (PDF, CSV, text), searched by the agents across projects, next to each project's own Library | people, through the app | documents: upload, list, delete |
| Connectors | MCP servers the agents may call | admins, through the app | connectors (unchanged from v1) |
| Agent memory | what the agents learned: role lessons and designs that passed review | geomind only | an on/off switch per project, nothing else |

## 1. Knowledge (RAG): new optional Workspace methods

These mirror the project's `documents` / `files` / `file`, but they are shared across projects.

- `knowledge_search(query) -> [{id, document, title, page, text, score}]`, best first. These are
  chunks of the shared documents. `document` is the file name that `knowledge_file` reads.
- `knowledge_files() -> [{name, size, media_type}]`, `[]` when there are none.
- `knowledge_file(name) -> bytes | None`.
- A workspace without them keeps working. The tools then answer `knowledge_unavailable`.
- Agent tools: `search_knowledge(query)` returns chunks with their citation (document, page).
  `read_document` also reads a knowledge file by the name `knowledge/<name>`.
- A value an agent takes from a knowledge document is cited (document, page). It is confirmed by
  the user like any value not from the project's own files.
- The CLI uses `GEOMIND_KNOWLEDGE_DIR`, a folder of documents. It is required when knowledge is
  used, with no default.
- **The cost catalogue becomes a knowledge document** (CSV), no longer memory entries. The backend
  seeds it as one document in Knowledge.

**Dropped from v1:** the backend's knowledge *entries* (`POST /workspace/knowledge` with fields,
`PATCH`, `import` CSV rows), `gd.memory.check_knowledge`, `gd.memory.catalogue_entries`,
`STATUSES`, `CITATION`, `LOCATION`, and the "knowledge" section of memory. The backend no longer
needs any `gd.memory` checker. Knowledge is documents, and the backend can index them with its
existing document search.

## 2. Agent memory: Workspace.memory(project_id) -> Memory | None (optional)

- Only the agents' own memory. It has one section, `experience`, which holds role lessons
  (written by Curator) and designs that passed review (written by code after the Reviewer).
  Each entry carries `origin` and `project_id`.
- `Memory` keeps `entries(section)` and `add(section, entry)`. The backend stores the entries
  as it gets them and does not check or edit them.
- `None` means memory is off. `GEOMIND_MEMORY=off` wins even when the workspace offers a memory
  (final and competition runs).
- Experience is shared across projects. That is the point of learning.
- The backend shows only the project's on/off switch. `GEOMIND_MEMORY_SIMILARITY` is a geomind
  setting, required when memory is on, with no default. It is set in the backend's env, but the
  app does not show it.
- The user's preferences (for example display units) are not memory. They live in the chat's
  problem state.

## 3. Connectors (MCP): unchanged from v1

- `Workspace.connectors(project_id) -> [{name, url, transport: "http"|"sse", headers}]`
  (optional). `name` matches `[a-z0-9_-]{1,32}`. Header values are never logged, stored, echoed
  or replayed.
- `gd.mcp.list_tools(server) -> [{name, description, read_only}]` is sync. `read_only` comes from
  `readOnlyHint` and is false when missing. It raises `gd.mcp.ConnectorError` with `code`
  set to `unreachable`, `auth_refused` or `bad_response`.
- The tool name the model sees is `<server>__<tool>`. A tool that is not read-only asks for
  approval with request kind `approval`. `tool.started` / `tool.finished` carry
  `connector: <server>`.
- `GEOMIND_MCP_TIMEOUT` is a plain number of seconds (`30`, not `30s`). It is required when a
  connector is given.
- A connector result is data. A value from it that enters the case or the plant is confirmed by
  the user, with the connector named as its origin.

## v3 rename (Sahand 2026-11-03 20:58 UTC): "documents" -> "rag", "connectors" -> "mcp" everywhere in code

Proposed by GEOMIND II. BACKEND I confirms or corrects this. The app shows user-friendly names only.

| v2 name | v3 name |
|---|---|
| Workspace.documents(project_id, query) (project Library) | Workspace.rag(project_id, query) |
| Workspace.knowledge_search(query) / knowledge_files() / knowledge_file(name) (shared) | unchanged |
| Workspace.connectors(project_id) | Workspace.mcp(project_id) |
| agent tool search_documents | rag_search |
| agent tool read_document | rag_read (also reads `knowledge/<name>`) |
| event field `connector: <server>` | `mcp: <server>` |
| answer code documents_unavailable / connectors... | rag_unavailable / mcp_unavailable |
| gd.mcp.ConnectorError | gd.mcp.McpError (same codes) |

Old logs keep replaying: old tool names and fields are mapped on read.

v3 CONFIRMED by BACKEND I (20:59 UTC). files/file/memory unchanged. The backend keeps documents/connectors alongside until the geomind release uses the new names.

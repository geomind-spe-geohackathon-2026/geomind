# geomind S1b: rename swarmax to geomind, remove `core/`, contract 2.2

Prompt for Claude Code, run in `/Users/sahand/Desktop/crust-team` (the parent folder, because the package folder itself is renamed).

## Goal

Three changes to the agent package built in S1, in this order, each its own commit:

1. Remove the `core/` folder: its packages move to the top level of the package.
2. Rename the package `swarmax` to `geomind` (`import geomind as gd`), everywhere.
3. Bring the code up to the contract in Appendix A (interfaces section version 2.2): `RunStore.load_events`, the internal `error` event, `Callback.on_event`, `model` on `step.started`, the `options` shape, the `state.changed` shape.

No behaviour changes beyond item 3. All tests stay green after every commit.

## 0. Read first

- `swarmax/AGENTS.md` and every file in `swarmax/.claude/docs/`, then `swarmax/swarmax/__init__.py`.
- Write Appendix A verbatim to `docs/contracts.md` (overwrite; it replaces the older copy), then read its sections 2 and 3.
- If anything here contradicts the code in a way this prompt does not explain, stop and say so.

## 1. Rules (unchanged from S1)

- Follow `swarmax/.claude/docs/conventions.md` and `testing.md` exactly: code quality, no comments in code, `NOTE:` decisions in docstrings, `errors` classes, the framework-name rule.
- Tests: while working run only the tests of changed files and their importers (`scripts/test_changed.py`, parallel); before each commit run the full fast suite in parallel. Never the network.
- Temporary files in `.tmp/`. Subagents use lighter models (Sonnet or Haiku).
- Update `AGENTS.md` and `.claude/docs/` in the same commit as each change.
- Commit on `main` after each step. Do not push. Do not change `gemini/` or `backend/`.
- If something is missing, unclear or risky, stop and say so.

## 2. Step 1: remove `core/`

Move every package inside `swarmax/core/` one level up (`git mv`, so history follows):

```text
swarmax/
├── __init__.py  __main__.py  cli.py  run.py  stores.py
├── utils/  errors/
├── types/  runtime.py  prompts/
├── providers/  sandbox/  tools/
├── agents/  engine/  loops/
└── testing/
```

- New dependency order, enforced by the boundary test:
  `utils`, `errors` ← `types` ← `runtime` ← `prompts` ← `providers` ← `sandbox` ← `tools` ← `agents` ← `engine` ← `loops` ← `run` ← `testing` ← `cli` ← `__init__`
- Update every import, the boundary test, `test_changed.py` mappings, the tests mirror (`tests/unit/core/...` → `tests/unit/...`), examples and all docs. No `core` remains anywhere: add a test that fails if a `core` package or a `.core.` import reappears.
- `NOTE:` the folder named `types` shares its name with the standard library module; this is safe because every import is absolute (`geomind.types`). Write this in `conventions.md`.
- Check that every `gemini` import in the package uses only `gemini` public names (`gemini.errors`, `import gemini as gm`), never `gemini.core...`. gemini is about to drop its own `core/` folder; list any deep import you find in the report instead of changing gemini.

## 3. Step 2: rename to `geomind`

- `git mv swarmax/swarmax swarmax/geomind`, then rename the repository folder: `mv swarmax geomind` (run from `crust-team/`). The git history stays.
- Everywhere: package name in `pyproject.toml` (`name = "geomind"`), imports, the curated `__init__`, docs, examples, tests, CI, Makefile, the CLI command (`geomind run|replay|show`, entry point and `python -m geomind`), the root error class (`SwarmaxError` → `GeomindError`), the environment variable (`SWARMAX_MODEL` → `GEOMIND_MODEL`), log and event texts.
- The import alias in all docs and examples is `gd` (`import geomind as gd`), replacing `sx`. `NOTE:` not `gm`, which is gemini's alias.
- PyPI: the name `geomind` is taken by an unrelated, abandoned package. Keep `name = "geomind"` in `pyproject.toml` for local and editable installs; do not publish. Write this in `AGENTS.md`.
- Keep `.runs/` as the run folder name. Files written by S1 runs keep loading (event and checkpoint formats do not change); add a test with one stored S1 run as a fixture.
- Add a test that fails if `swarmax` or `sx.` appears in any tracked file, except `CHANGELOG.md` if you add one, with one line saying the package was renamed from `swarmax`.
- In `crust-team/docs/`: rename `swarmax-design.md` to `geomind-design.md` and replace the package name and the `sx.` alias inside it, `contracts.md` already uses the new name in its rename note; do not touch other files there.
- Report every place outside the package that still says `swarmax` (for example `backend/`, which you must not change).

## 4. Step 3: contract 2.2

Implement exactly what Appendix A sections 2 and 3 say; the differences from S1 are:

1. `RunStore.load_events(run_id)` is now part of the protocol (it was an extra in S1): in the protocol, both stores, `testing.check_run_store`, and `contracts.md` mapping in `.claude/docs/contracts.md`.
2. `error` is an internal event type; `on_error` receives it, and it is saved like every event.
3. `Callback.on_event(engine, event)` receives every event (public and internal), before the specific method; document it as the one method a publisher needs.
4. `step.started` data is `{index, model}` with the provider model id of the step's call.
5. `request.options` is a list of `{value, label}`, only for questions with fixed choices; the answer to such a question is `{"text": value}`; `ask_user(question, options=None)` accepts a list of strings or of `{value, label}` and normalises to the latter.
6. `state.changed` data is `{version, changes}` with `changes` as JSON Patch operations (`add`, `replace`, `remove`, JSON Pointer paths, id-addressed lists, `-` appends). Define the event class and its validation now; S2 emits it.
7. `Run.load(..., sandbox=..., permissions=...)` as in the contract example.

The contract-JSON test pins every public event against the new table. Update `.claude/docs/contracts.md` (every item mapped to code and test) and `events.md`.

## Done when

- No `core/`, no `swarmax`, no `sx.` left (tests enforce it); `import geomind as gd` works; `geomind run`, `replay` and `show` work with `FakeLLM`.
- Every item of Appendix A sections 2 and 3 is implemented, exported and tested.
- The full fast suite passes, Flake8, Black and isort are clean; three commits on `main`, not pushed.

## Report back

What changed; any deep `gemini.core` import found; every file outside the package that still says `swarmax`; anything in the contract that should change.

---

# Appendix A: `docs/contracts.md`

Write it exactly, between the marker lines (markers excluded). The prompt ends after this appendix.

<<<<<<<<<< BEGIN docs/contracts.md
# Contracts between the repos

Version 6 (2026-10-30). Version 6: the agent package `swarmax` is being renamed `geomind` (`import geomind as gd`), see section 3. File version, raised on every change: section 1 from the backend design (refresh, `active`, project owner and plant version, run request and error, chat edit and delete, error codes, `?cursor=`, validation details); sections 2 and 3 from the swarmax design (section 3 keeps its own interface version, now 2.2). Covers steps 1 and 2 of every repo. Later steps add their routes here before they start.

## 1. HTTP API (frontend ↔ backend)

- Base: `/api/v1`. JSON. Times are ISO 8601 with a timezone, UTC.
- Path = `/<domain>/<feature>/...`, the same names as the folders in both repos.
- Auth: bearer access token from `identity/authn`, renewed with `POST /identity/authn/refresh`. Tokens never go in URLs.
- Live events (section 2) are read with `fetch` and the bearer header (for example `@microsoft/fetch-event-source`), because the browser's `EventSource` cannot send an `Authorization` header.
- Errors: `{"error": {"code": "<snake_case>", "message": "<human text>", "details": {...}}}` with a matching HTTP status. Codes are stable; messages may change.
- Lists: `{"items": [...], "next": "<cursor or null>"}`; the next page is `?cursor=<next>` (optional `?limit=`, default 50).
- Stable error codes: `unauthorized` (401), `forbidden` (403), `not_found` and `<thing>_not_found` (404), `validation_failed` (422, `details = {"fields": {"<field>": "<message>"}}`), `conflict` (409), `run_not_waiting` (409), `plant_invalid` (422), `rate_limited` (429), `internal` (500). A project the caller may not see answers `404 project_not_found`, the same as a missing one.

### identity

| Method | Path | Body → Response |
|---|---|---|
| POST | `/identity/authn/login` | `{email, password}` → `{access_token, refresh_token, user}` |
| POST | `/identity/authn/refresh` | `{refresh_token}` → `{access_token, refresh_token}` |
| POST | `/identity/authn/logout` | → `204` |
| GET | `/identity/me` | → `user` |
| POST | `/identity/me/password` | `{old_password, new_password}` → `204` |
| GET | `/identity/users` | admin → list of `user` |
| POST | `/identity/users` | admin, `{email, name, password, role}` → `user` |
| PATCH | `/identity/users/{id}` | admin, `{role?, name?, active?}` → `user` |

`user = {id, email, name, role, active}`, `role` is `admin` or `member`. Users are deactivated, never deleted; an inactive user cannot sign in.

### workspace/projects

| Method | Path | Body → Response |
|---|---|---|
| GET | `/workspace/projects` | → list of `project` |
| POST | `/workspace/projects` | `{name}` → `project` |
| GET | `/workspace/projects/{id}` | → `project` |
| DELETE | `/workspace/projects/{id}` | → `204` |
| GET | `/workspace/projects/{id}/export` | → zip file |
| POST | `/workspace/projects/import` | multipart `file` → `project` |

`project = {id, name, owner: {id, name}, plant_version, created, updated}`; `plant_version` is the latest plant version number or `null`. Only the owner or an admin may read or change a project.

Export zip: `project.json` (`{format: 1, name, exported}`) and `plant/<number>.json` (`{number, note, created, content}`, `content` in gemini's plant format), one file per plant version. Import takes the same zip.

### assistant/chat

| Method | Path | Body → Response |
|---|---|---|
| GET | `/assistant/chat?project={id}` | → list of `chat` |
| POST | `/assistant/chat` | `{project, title?}` → `chat` |
| GET | `/assistant/chat/{id}/messages` | → list of `message` |
| POST | `/assistant/chat/{id}/messages` | `{content}` → `{message, run}` |
| PATCH | `/assistant/chat/{id}` | `{title}` → `chat` |
| DELETE | `/assistant/chat/{id}` | → `204` |

`chat = {id, project, title, created}`; `message = {id, chat, role, content, created, run?}`, `role` is `user` or `assistant`.

### assistant/runs

| Method | Path | Body → Response |
|---|---|---|
| GET | `/assistant/runs/{id}` | → `run` |
| GET | `/assistant/runs/{id}/events` | Server-Sent Events, see section 2 |
| GET | `/assistant/runs/{id}/log` | → `runlog` |
| POST | `/assistant/runs/{id}/answer` | `{request, answer}` → `run` (approve, deny, or reply to a question) |
| POST | `/assistant/runs/{id}/cancel` | → `run` |

`run = {id, chat, status, loop, started, ended, usage, request, error}`, `status` is `queued`, `running`, `waiting`, `done`, `failed` or `cancelled`. `request` is the pending request (as in the `request` event) while `waiting`, else `null`; `error` is `{code, message}` when `failed`, else `null`. Answering a run that is not waiting is `409 run_not_waiting`. `usage = {input_tokens, output_tokens, cost}`.

`runlog = {run, steps: [{index, agent, parent, llm_calls: [...], tool_calls: [...]}]}`, with `llm_call = {model, messages, answer, input_tokens, output_tokens, cost, duration}` and `tool_call = {call_id, tool, input, output, duration, error?}`. `agent` is the dotted agent path (`coordinator.designer`); `parent` is the parent step of a delegated (nested) run, or `null`. swarmax builds this object: `sx.runlog(events)`.

## 2. Live run events (backend → frontend, SSE)

Each event: `event: <type>`, `data: <json>`, `id: <sequence number>`. The stream replays from `Last-Event-ID` on reconnect. Every `data` also carries `agent` (dotted path) and `parent` (parent run id or `null`); they are left out of the table.

| Type | Data |
|---|---|
| `run.started` | `{run, loop}` |
| `step.started` | `{index, model}` (`model`: the provider model id this step calls, e.g. `anthropic/claude-sonnet-4.5`) |
| `text.delta` | `{index, text}` |
| `tool.started` | `{index, call_id, tool, input}` |
| `tool.finished` | `{index, call_id, output_summary, duration, error?}` |
| `step.finished` | `{index, usage}` (usage of this step) |
| `state.changed` | `{version, changes}`; see *Problem state changes* below (emitted from S2) |
| `request` | `{request, call_id?, kind, message, options?}`; `kind` is `approval` or `question`; `options` is `[{value, label}]` (a question with fixed choices; absent for free text and for approvals); the run is `waiting` |
| `usage` | `{input_tokens, output_tokens, cost}` (running totals) |
| `run.finished` | `{status, stop_reason, message?}` |

**Problem state changes.** `version` is the state version after the change (starts at 1, +1 per event). `changes` is a list of JSON Patch operations (RFC 6902 subset) on the problem state document:

```json
{"version": 4, "changes": [
  {"op": "add", "path": "/requirements/-", "value": {"id": "R3", "text": "Cover peak cooling", "metric": "cooling_coverage", "target": 1.0, "tolerance": 0.0, "status": "open"}},
  {"op": "replace", "path": "/assumptions/A1/confirmed", "value": true},
  {"op": "remove", "path": "/questions/Q2"}
]}
```

`op` is `add`, `replace` or `remove`; `path` is a JSON Pointer. Lists of items with an `id` (`requirements`, `assumptions`, `results`, `questions`) are addressed by id, not index; `-` appends. The document's top-level keys are `goal`, `requirements`, `assumptions`, `design`, `results`, `verification`, `questions` (shape in `../docs/swarmax-design.md` section 3). A client that missed a version reloads the full state (route added with B2 if needed).

**Answers to options.** For a question with `options`, the answer is `{"text": <value>}`; approvals keep `{"approved": true}` or `{"approved": false, "reason": ...}`.

These are the swarmax callback events with `event.is_public` true, forwarded as they are: `event.type` and `event.data()` (JSON-safe). swarmax also emits internal events (`llm.completed`, `tool.result`, `permission`, `retry`, `sandbox.provisioned`, `sandbox.closed`, `checkpoint`, `error`); the backend saves every event through `RunStore.save_event` but streams only public ones. The internal events are the run's source of truth, used for recovery and the full log. `Callback.on_event(engine, event)` receives every event, so a publisher needs one method. The backend adds no event types of its own.

## 3. swarmax interfaces (backend ↔ swarmax)

**Rename:** the package `swarmax` becomes `geomind`, imported as `import geomind as gd` (not `gm`, which is gemini), in the next agent-package prompt (together with removing its `core/` folder). Every `sx.` below then reads `gd.`; names after the prefix do not change. Until that prompt has run, the installed package is still `swarmax`.

Version 2.2 (2026-10-30: `load_events`, the `error` event and `on_event` added after swarmax S1; `model` on `step.started`, `options` shape and `state.changed` shape for the frontend). The backend implements `RunStore` and `Workspace` and passes them in; swarmax ships a file and a memory implementation of each, the `OpenRouter` provider (the backend may use it directly instead of its own `LLM`), and `FakeLLM` for tests. All of it exists after swarmax S1, so the backend never waits for later swarmax phases.

```python
class LLM(Protocol):
    async def complete(self, messages, tools, *, model, settings, on_text=None) -> Completion: ...
    # Completion: text, tool_calls, usage (input_tokens, output_tokens, cost), model, raw
    # on_text(delta) streams text; settings = temperature, max_tokens

class RunStore(Protocol):
    def save_event(self, run_id, event): ...
    def save_checkpoint(self, run_id, checkpoint): ...
    def load_checkpoint(self, run_id): ...
    def load_history(self, chat_id) -> list[Message]: ...
    def save_state(self, chat_id, state): ...          # problem state across messages
    def load_state(self, chat_id): ...                 # None when the chat has none
    def save_artifact(self, run_id, key, data): ...    # large tool results (bytes or JSON)
    def load_artifact(self, run_id, key): ...
    def load_events(self, run_id) -> list[Event]: ...   # in sequence order; recovery and replay

# RunStore and Workspace are sync; swarmax calls them from a worker thread.

class Workspace(Protocol):
    def plant(self, project_id): ...            # the stored plant as a gemini plant
    def documents(self, project_id, query): ... # document search: [{id, title, text, score}]

class SandboxProvider(Protocol):               # optional; swarmax ships LocalSandbox and DockerSandbox
    async def provision(self, manifest) -> Sandbox: ...
```

Entry point used by the backend:

```python
import swarmax as sx

run = sx.Run(
    message=content, chat=chat_id, project=project_id,
    history=store.load_history(chat_id),
    llm=llm, store=store, workspace=workspace,
    sandbox=sx.sandbox.DockerSandbox(), permissions=sx.Permissions(mode="ask"),
    callbacks=[publisher],
    hooks=[sx.hooks.TokenBudget(...), sx.hooks.RequireApproval(...),
           sx.hooks.Cancellation(is_cancelled)],
)
result = run.start()                  # or await run.astart(); RunResult: run_id, status, answer, request, usage, stop_reason

run = sx.Run.load(run_id, llm=llm, store=store, workspace=workspace, sandbox=...,
                  permissions=..., callbacks=[publisher], hooks=[...])
result = run.resume(request_id, answer)   # or await run.aresume(...); in another process; hooks and callbacks are passed again
result = run.resume()                     # continue a run whose process died while running

run.cancel()                          # same process; across processes use sx.hooks.Cancellation
```

`answer` is `{"approved": true}`, `{"approved": false, "reason": "..."}` or `{"text": "..."}` for a question. `status` values are those of `run` in section 1. A `Message` is `{role, content, tool_calls?, tool_call_id?}` with `role` `user`, `assistant`, `tool` or `system`; `load_history` returns only `user` and `assistant` messages.

The backend never chooses the loop or the agents; swarmax's coordinator does.
>>>>>>>>>> END docs/contracts.md

<!-- END OF PROMPT -->

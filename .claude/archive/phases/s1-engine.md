# geomind S1: Package, rules, engine and the full backend contract

Prompt for Claude Code, run in `/Users/sahand/Desktop/crust-team/geomind`.

## Goal

Create the Python package `geomind` with the same structure and conventions as `gemini`, and finish in this phase **everything the backend needs** (contracts.md sections 2 and 3, version 2), so the backend never waits for a later geomind phase:

- the agent, engine, tools, hooks, callbacks, checkpoints, replay and the `ToolLoop`;
- `gd.Run` with `start`, `load`, `resume` and `cancel`;
- the `LLM`, `RunStore` and `Workspace` protocols, with memory and file implementations, `OpenRouter` and `FakeLLM`;
- every live event type with its JSON form, `gd.runlog(events)` for `GET /runs/{id}/log`;
- conformance tests the backend can run against its own store and workspace;
- the harness structure from the design's section 11, fixed now so it does not change later: the event log as the source of truth, an async core with a sync façade, the sandbox for model-written code, declarative permissions, the context builder, retries, typed output.

Later phases add intelligence (gemini tools, problem state, coordinator, design loops) behind the same interfaces, without changing them.

```
geomind run "Say hello and list the tools you have" --model <openrouter model id>
geomind replay .runs/<run id>
geomind show .runs/<run id>
```

## 0. Read first

- `../gemini/AGENTS.md` and every file in `../gemini/.claude/docs/`, especially `conventions.md`, `testing.md`, `engine.md`, `modules.md`, `errors.md`, `utils.md`, `runtime.md`, `api.md`.
- Code: `../gemini/gemini/__init__.py`, `../gemini/gemini/core/modules/module.py`, `../gemini/gemini/core/engine/callbacks.py`, `../gemini/gemini/core/engine/engine.py`, `../gemini/gemini/utils/`, `../gemini/scripts/test_changed.py`, `../gemini/tests/unit/test_code_quality.py`, `../gemini/tests/unit/test_package_boundaries.py`, `../gemini/tests/unit/test_public_api.py`, `../gemini/conftest.py`, `../gemini/pyproject.toml`, `../gemini/Makefile`.
- `../docs/geomind-design.md` (the agreed design), `../docs/contracts.md` (version 2; sections 2 and 3 are what you implement), `../docs/agent-engineering-layers.md`, `../docs/open-source-harnesses.md`, `../docs/phases.md`. Copy them from the project folder (`geomind/design.md`, `phases/contracts.md`, `research/agent-engineering-layers.md`, `research/open-source-harnesses.md`, `phases/README.md`) if missing or older.
- If any of these is missing, stop and say so.

## 1. Rules for the whole task

These rules are also the content of step 1: they go into `AGENTS.md` and `.claude/docs/` before any code.

### Code quality

- Take every general rule of `../gemini/.claude/docs/conventions.md` (Dependencies idea, Naming outside port names, Comments, Code quality, Implicit mechanisms) and of `testing.md`, adapted to geomind. Drop only what is about physics, modules, ports, units, datasets or legacy.
- Python 3.11 to 3.14. Black, isort, 100-character lines, Flake8 with docstrings and `max-complexity = 10`.
- Simple, readable, just enough code: no dead code, unused options or parameters, speculative generality or golfed one-liners.
- Nesting at most three blocks; guard clauses; no `else` after `return` or `raise`; functions about 40 lines at most, one job each.
- Full-word names; booleans read as questions (`is_waiting`, `has_request`). Folder names one word, lower case, no underscores.
- No comments inside code. Allowed: the fixed constructor section headers (`# Agents`, `# Prompt`, `# Tools`, `# Output`, `# Model`) and tool directives (`# noqa: <code>`, `# type: ignore[<code>]`, `# pragma: no cover`). Explanations, reasons and decisions go into docstrings; a decision is a `NOTE:` sentence.
- Every deliberate error raises an `gd.errors` class. No bare `except`, no silent fallback.
- A bug gets a failing test first.
- Never name the framework that gemini's module design resembles, nor any other agent framework, in code, docstrings or docs. Describe the concept itself.
- Implicit mechanisms only where listed in section 4, each documented in `conventions.md` with its reason.
- Where geomind departs from gemini, write the reason as a `NOTE:` in the docstring and list it in `conventions.md`.

### Tests

- Tiers as in gemini: `tests/unit/` mirrors the package, `tests/integration/`, `tests/e2e/`, `tests/fixtures/` (recorded LLM completions as JSON).
- Never call the network in tests. Use `FakeLLM` and recorded completions; `OpenRouter` is tested against a fake HTTP transport.
- Development profile, while working and before every commit: `scripts/test_changed.py` runs the tests of changed files and of everything that imports them, transitively, in parallel (`-n auto`), budget under 300 s. Before each commit also run the full fast suite in parallel (it is small here). The release profile runs in CI only.
- No fast test over about 1 s.
- Code-quality tests copied from gemini and adapted: nesting, function length (with a documented `LONG_FUNCTIONS` list), `else` after early exit, raises use `gd.errors`, comments, framework names, package boundaries, public API.
- Temporary files and reports go to `.tmp/` (git-ignored). CLI runs go to `.runs/` (git-ignored).

### Docs

`AGENTS.md` (short map: Start here, layout, the gemini parallels, branching, the test command) and `.claude/docs/`: `api.md`, `conventions.md`, `testing.md`, `errors.md`, `contracts.md` (how geomind implements the backend contract, with links to `../docs/contracts.md`), `agents.md`, `engine.md`, `tools.md`, `providers.md`, `hooks.md`, `permissions.md`, `sandbox.md`, `events.md` (every event type, public or internal, with its JSON), `runtime.md`, `utils.md`. Update the relevant document in the same commit as the change, so a new session can read the docs and know the current state.

### Working

- Subtasks and subagents use lighter models (Sonnet or Haiku), never the main model.
- If something is missing, unclear or risky, stop and say so instead of guessing.
- If `geomind/` is not yet a git repository, run `git init -b main` there first; no remote yet. Commit after each step below on `main`. Do not create other branches. Do not push until told.
- Do not change `../gemini` or `../backend`. If gemini lacks something, write it in the report.

## 2. Layout and dependency order

```text
geomind/
├── __init__.py       # curated `import geomind as gd`
├── __main__.py       # python -m geomind → cli
├── cli.py            # run, replay, show
├── run.py            # Run: the façade the backend uses
├── testing/          # conformance checks for RunStore and Workspace implementations
├── utils/            # leaf: hooks (RemovableHandle), context settings, time, json
├── errors/           # leaf: every gd.errors class
├── core/
│   ├── types/        # Message, ToolCall, Completion, Usage, Action, Request, Deny, RunResult, events, runlog
│   ├── runtime.py    # context-local settings and the active run
│   ├── prompts/      # <role>.md files and Prompt
│   ├── agents/       # agent.py (Agent, AgentResult), general/assistant.py
│   └── engine/       # engine.py, step.py, log.py, recovery.py, context.py, callbacks.py, hooks.py, permissions.py, checkpoint.py, store.py, workspace.py, replay.py
├── providers/        # base.py (LLM protocol), openrouter.py, fake.py, retry.py
├── sandbox/          # base.py (Sandbox, SandboxProvider, Manifest, ExecutionResult), local.py, docker.py
├── tools/            # Tool, tool decorator, dispatch, builtins (ask_user, finish), code.py (run_python, read_file, write_file), delegate.py
└── loops/            # loop.py (Loop), tool.py (ToolLoop)
examples/  scripts/test_changed.py  tests/  .claude/docs/  AGENTS.md  pyproject.toml  Makefile
```

Dependency order, enforced by `tests/unit/test_package_boundaries.py` (a package imports only those to its left):

`utils`, `errors` ← `core.types` ← `core.runtime` ← `core.prompts` ← `providers` ← `sandbox` ← `tools` ← `core.agents` ← `core.engine` ← `loops` ← `run` ← `testing` ← `cli` ← `geomind/__init__`

`NOTE:` `core.types` sits below `providers` because a provider returns a `Completion`; `tools.delegate` reaches the engine only through the active run in `core.runtime`, never by import; `sandbox` sits below `tools` because the code tools use it.

`core/context/` (problem state, compaction) and `core/verify/` come in S2 and S3; do not create empty packages for them.

## 3. The parallels with gemini

| gemini | geomind | Meaning |
|---|---|---|
| `Module`, one tick | `Agent`, one decision | declarations in `__init__`, behaviour in `forward` |
| `ModuleResult` | `AgentResult` | built by `__call__`, never by user code |
| `Engine.simulate/replay` | `Engine.run/replay/resume` | drives the unit over steps, finite, no sleeping |
| `Callback` | `Callback` | observers, same method style |
| forward pre-hooks | `before_*` hooks | can deny or pause; registration returns a handle with `.remove()` |
| `gemini.backends` | `geomind.providers` | interchangeable implementations behind one protocol; named providers because they are LLM services |
| `gemini.ops` | `geomind.tools` | the primitive actions with dispatch |
| `optim` (drives `Engine.replay`) | `loops` (drive `Engine.run`) | algorithms over the engine |
| checkpoints | checkpoints | resume anywhere, in another process |

## 4. Design to implement

### Harness principles (design section 11; every part below follows them)

1. **The event log is the source of truth.** Every LLM completion and every tool result is saved as an event with `store.save_event` *before* the engine acts on it. A checkpoint is only a snapshot of the log for speed. Resume, crash recovery and replay are one mechanism (`recovery.py`): rebuild the run from its events and reuse recorded completions and results, never call them again. The engine keeps no state that is not in the log, so any process can continue any run.
2. **Side effects only in two places:** `providers` (LLM calls) and `tools.dispatch` (tool calls). Engine, context and loops are deterministic code over the log, so a durable executor could wrap the two later without a redesign. A tool declares `idempotent`; after a crash, a started tool without a recorded result is rerun only when idempotent, otherwise it becomes an error result for the model.
3. **Async core, sync façade.** Engine, agents, providers, sandbox and dispatch are `async`. Sync tools (gemini calls) run in a worker thread with a copied context (`contextvars.copy_context()`). Tool calls of one step that are all `read` or `compute` run concurrently; others run in order. `RunStore` and `Workspace` stay sync for the backend and are called through `asyncio.to_thread`. Users see `run.start()`/`run.resume()` (sync) and `await run.astart()`/`await run.aresume()`.
4. **Credentials stay in the harness.** Keys live only in providers; they never enter a sandbox, a prompt, an event, a checkpoint or a log. Events pass a redaction step for the known secret values.
5. **Stable identifiers.** Tool names, event types, checkpoint and event-log versions never change silently; a change is a new version, recorded in `events.md`.

### Agent (`core/agents/agent.py`)

```python
class Assistant(gd.Agent):
    """General assistant that answers with the tools it has."""

    def __init__(self):
        super().__init__()

        # Prompt
        self.prompt = gd.Prompt("assistant")

        # Tools
        self.ask_user = gd.tools.ask_user
        self.finish = gd.tools.finish

        # Output
        self.output = gd.Output(str)

        # Model
        self.model = gd.Model(temperature=0)
```

- Sections `# Agents`, `# Prompt`, `# Tools`, `# Output`, `# Model`, in that order, empty ones omitted. Declarations only in `__init__` after `super().__init__()`.
- Implicit mechanism (documented): `Agent.__setattr__` registers a `Tool` in the ordered tool registry, an `Agent` as a child with a dotted `path`, a `Prompt`, an `Output` and a `Model`. Unknown or duplicate names raise `gd.errors.DeclarationError` with a close-match suggestion.
- Listings: `tools(recurse=False)` (ordered dict by name), `named_agents()`, `children()`, `name` (snake_case class name), `path`, `Agent.help()` (first docstring paragraph plus declarations).
- `async def forward(self, context) -> Action`. The default renders the prompt, the context messages and the tool schemas and awaits `self.complete(messages)`. Override only for rule-based steps.
- `self.complete(messages)` calls the LLM of the active run (from `core.runtime`) with this agent's model and tools, streaming text to `on_text`. Outside a run it raises `gd.errors.RunError`.
- `await agent(context)` returns `AgentResult(action, messages, usage, duration)`. Order: `before_llm_call` hooks → `forward` → `on_llm_call` callbacks.
- No `Team` and no agent containers (`NOTE:` the order of agents is a policy, and policies are loops).
- `Prompt("assistant")` loads `core/prompts/assistant.md`; `Prompt.text(...)` for inline text. `Model(name=None, temperature=0, max_tokens=None)`; `name=None` means the default model from `gd.runtime`; `fallbacks=(...)` lists models tried in order when the provider keeps failing.
- `Output(kind, max_retries=2)`: the type of the final answer (`str` by default, or a Pydantic model). The answer of `finish` or of the last message is validated; a failure goes back to the model as feedback, up to `max_retries`, then the run fails with `stop_reason="error"`.

### Types (`core/types/`)

- Pydantic, frozen, JSON-safe: `Message(role, content, tool_calls=(), tool_call_id=None)` with roles `user`, `assistant`, `tool`, `system`; `ToolCall(id, name, input)`; `Usage(input_tokens, output_tokens, cost)` with `+`; `Completion(text, tool_calls, usage, model, raw)`; `Action(text, tool_calls)`; `Request(id, kind, message, options=None, call_id=None)` with `kind` `approval` or `question`; `Allow(input=None)` (optionally a changed tool input); `Deny(reason)`; `RunResult(run_id, status, answer, request, usage, steps, stop_reason)`.
- Answers to a request, exactly as in the contract: `{"approved": true}`, `{"approved": false, "reason": ...}`, `{"text": ...}`; validated, a wrong shape raises `gd.errors.RequestError`.
- Events: every event has `run_id`, `sequence`, `time`, `agent`, `parent`, a stable `type`, `is_public` and `data()`.
  - Public (streamed to the browser): the ten types of contracts.md section 2, **including `state.changed`** (emitted from S2); `data()` returns exactly the contract JSON, pinned by a test against the contract table.
  - Internal (stored, used by recovery, replay and the log): `llm.completed` (the full completion and the messages sent), `tool.result` (the full output), `permission` (the decision and the rule that made it), `retry`, `sandbox.provisioned`, `sandbox.closed`, `checkpoint`.
- `runlog(events)` builds the contract's `runlog` object from a run's events, nested runs included; exported as `gd.runlog`.

### Providers (`providers/`)

- `LLM` protocol, exactly as in contracts.md section 3: `async def complete(messages, tools, *, model, settings, on_text=None) -> Completion`.
- `retry.py`: retries with exponential backoff on HTTP 429, 5xx and timeouts (counts and delays from `gd.runtime`), then the model's `fallbacks`; every retry is a `retry` event. Wraps any `LLM`, so a backend-made provider gets it too.
- `OpenRouter(api_key=None, base_url=...)`: reads `OPENROUTER_API_KEY` when no key is given; streams with `httpx.AsyncClient` and a request timeout; fills `Usage` including cost from the response; HTTP and API errors raise `gd.errors.ProviderError` with status and message.
- `FakeLLM(completions)`: returns scripted completions in order and calls `on_text` with their text; raises `ProviderError` when the script is exhausted. `FakeLLM.from_events(events)` rebuilds the script from a stored run, for replay.

### Sandbox (`sandbox/`)

The "hands" for code the model writes (S3 uses it to write and test missing gemini modules). gemini tools are trusted library calls and stay in-process; model-written code only ever runs here.

```python
class Sandbox(Protocol):
    async def execute(self, command, *, timeout) -> ExecutionResult: ...  # exit_code, stdout, stderr, duration
    async def write(self, path, data): ...
    async def read(self, path) -> bytes: ...
    async def close(self): ...

class SandboxProvider(Protocol):
    async def provision(self, manifest) -> Sandbox: ...
```

- `Manifest(files={}, packages=("gemini",), python="3.11", cpu=1, memory="1g", disk="1g", timeout="10min", network=False)`: what goes in and the limits. gemini is mounted read-only.
- `LocalSandbox`: a subprocess in a temporary directory under `.tmp/sandbox/`, with time and memory limits and an empty environment (no keys). Documented in `sandbox.md` as development only and **not a security boundary**.
- `DockerSandbox`: a container with no network, read-only gemini, CPU, memory and disk limits, the run's files copied in; skipped in tests when Docker is absent, with one integration test behind a marker.
- Provisioned lazily by the engine on the first tool that needs it, once per run (a delegated run gets its own), closed at run end. A lost sandbox is a tool error the model can recover from; the next code tool provisions a new one.
- Output over a size limit is cut, with the full text saved as an artifact.

### Tools (`tools/`)

- `Tool(name, description, input_schema, function, *, effect, idempotent=True, timeout=None, max_retries=2)`. `effect` is one of `read`, `compute`, `write`, `execute` (sandbox code), `external` (network or anything outside the run). `Tool` is a protocol-shaped class, so toolsets from other sources (MCP later) fit without changes; `@gd.tool` builds one from a typed function (schema from the signature through Pydantic, description from the docstring).
- `await dispatch(tool, call)` validates input, runs with the tool's timeout (sync functions in a worker thread), times it and returns a tool result. Validation errors and any `gd.errors` or `gemini.errors` class become a result `{error: {class, message}}` with `is_error=True`, so the model can fix its call; after `max_retries` validation failures of one tool in a row, the run stops with `stop_reason="error"`. Any other exception is recorded, reported through `on_error`, and returned as an internal error result. Results over a size limit are saved with `store.save_artifact` and returned as `{reference, summary}`.
- Code tools (`code.py`), all `effect="execute"` or `write`: `run_python(code)`, `write_file(path, text)`, `read_file(path)`, each inside the run's sandbox.
- Built-ins: `ask_user(question, options=None)` returns a `Request` of kind `question` (the engine pauses); `finish(answer)` ends the run (after `before_finish` hooks).
- `Delegate(agent, max_summary_tokens=...)`: runs the agent in a nested engine run through the active run, with a clean context (task text only), a child run id and `parent` set on every event; returns the child's final answer, cut to the token limit.

### Engine (`core/engine/`)

- `Engine(callbacks=None, hooks=None, permissions=None, sandbox=None)`. `await run(agent, context, *, max_steps=30) -> RunResult`, finite.
- One step (`step.py`) = one agent call (its completion logged), the permission decision and dispatch of its tool calls (each result logged), then one checkpoint.
- Log and recovery (`log.py`, `recovery.py`): the order of writes above, and `recover(events)` that rebuilds context, usage, pending request and loop state from a run's events. Checkpoints are a shortcut for the same result; a test checks that recovery from events alone equals recovery from the checkpoint.
- The run stops on exactly one reason, stored in `RunResult.stop_reason`: `answer` (no tool calls), `finish`, `request`, `denied`, `step_limit`, `cancelled`, `error`. `status` follows the contract: `running`, `waiting`, `done`, `failed`, `cancelled`.
- Context builder (`context.py`): `Context` holds the run id and its messages; `messages_for(agent)` renders what the model sees in a fixed order: stable prefix (system prompt, tool schemas), then history, then the dynamic part last (budget left now; the problem state from S2), so prompt caching works. Large tool outputs appear as summaries with references. Kept small: S2 adds the problem state, compaction and skills here.
- Callbacks (`callbacks.py`): `Callback` with `on_run_start`, `on_step_start`, `on_llm_call`, `on_text`, `on_tool_start`, `on_tool_end`, `on_permission`, `on_state_change`, `on_request`, `on_step_end`, `on_error`, `on_run_end`, plain or `async`. Callbacks observe only; an exception in a callback is an `on_error` event and never changes the run. Each gets the engine and one event object. The engine also saves every event with `store.save_event`. Ship `EventLog` (JSON lines, or in memory).
- Hooks (`hooks.py`): `before_llm_call(agent, messages)`, `before_tool_call(agent, call)`, `before_finish(agent, action)`, plain or `async`, each returning `None` (no objection), `Deny(reason)` or `Request` (and for `before_tool_call` also `Allow(input=...)` to change the input):

| Decision | `before_llm_call` | `before_tool_call` | `before_finish` |
|---|---|---|---|
| `None` | call | call | finish |
| `Deny` | run stops, `denied` | tool skipped, reason is its result | finish refused, reason fed back |
| `Request` | pause | pause before the tool | pause before the answer |

  Register through `engine.register_hook(hook)`, which returns a handle with `.remove()`. Ship `TokenBudget(max_tokens)`, `CostBudget(max_cost)`, `RequireApproval(tools)`, `Cancellation(is_cancelled)` (a function the caller gives, checked before every LLM and tool call; ends the run with `cancelled`).
- Permissions (`permissions.py`): `Permissions(mode="ask", allow=(), ask=(), deny=())`, rules by tool name or effect (`"effect:execute"`). Every tool call is decided in this fixed order, written in `permissions.md`:
  1. `before_tool_call` hooks (deny or request ends the decision; an allow does not skip the rules);
  2. deny rules;
  3. ask rules (always a `Request` of kind `approval`);
  4. allow rules (an allow rule lets a `write`, `execute` or `external` tool run without asking in `ask` mode; it cannot override `readonly` or `plan`);
  5. the mode: `auto` allows all; `ask` (default) asks for `write`, `execute` and `external`; `readonly` denies all but `read` and `compute`; `plan` runs no tool and feeds back "plan mode: describe what you would do".
  `NOTE:` allow rules come before the mode, unlike the Claude Agent SDK order, because in geomind the mode decides every remaining call, so an allow rule after it could never apply.
  Every decision is a `permission` event naming the rule that made it. `RequireApproval(tools)` is a shortcut for ask rules. An approval answered by the user applies to that call id only.
- Requests: the engine saves a checkpoint holding the pending action (the exact tool call or answer), emits `request`, and returns `RunResult(status="waiting", request=...)`.
- Checkpoint (`checkpoint.py`): JSON, version 1, a snapshot of the log up to an event sequence number: run id, parent, chat, project, agent class path, context messages, pending request and action, step index, usage, loop state, runtime settings, creation time. Saved after every step and before a pause. A wrong version or shape raises `gd.errors.CheckpointError`.
- `Engine.resume(checkpoint, request_id, answer)`: an unknown or already answered request id raises `gd.errors.RequestError`. Approval runs the stored tool call without asking the same hook again for that call id; denial becomes the tool result; an answer to `ask_user` becomes its result. Then the steps continue.
- Store (`store.py`): the full `RunStore` protocol of contracts.md section 3 (all eight methods), with `MemoryRunStore` and `FileRunStore` (`.runs/<run id>/events.jsonl`, `checkpoint.json`, `artifacts/`; `.runs/chats/<chat id>/history.jsonl` and `state.json`). Plus `load_events(run_id)` on both, used by replay and `show`, `NOTE:` not part of the backend contract.
- Workspace (`workspace.py`): the `Workspace` protocol, `MemoryWorkspace(plants, documents)` and `FileWorkspace(root)` (plants as gemini plant files loaded with their class, documents as text files searched by simple keyword score). Unused by the S1 agents; the S2 tools call it.
- Replay (`replay.py`): `await Engine.replay(store, run_id)` reruns a stored run with its recorded completions through `FakeLLM.from_events`, no network, re-executes `read` and `compute` tools and reuses recorded results of the others, and checks that tool calls and the answer match; a mismatch raises `gd.errors.ReplayError` naming the first differing step.

### Loops (`loops/`)

- `Loop` base: `async def run(engine, task) -> RunResult`, `state_dict()` and `load_state_dict(state)`. The loop state is saved inside the run checkpoint, so a pause inside a loop resumes at the same place in another process. `NOTE:` loops are written as resumable steps, never with state held only in local variables.
- `ToolLoop(agent, max_steps=30)`: one engine run of one agent.

### Run (`run.py`)

Exactly as contracts.md section 3:

```python
run = gd.Run(message=..., chat=..., project=..., history=..., llm=..., store=...,
             workspace=None, sandbox=None, permissions=None, callbacks=[...], hooks=[...])
result = run.start()                     # or: result = await run.astart()
run = gd.Run.load(run_id, llm=..., store=..., workspace=None, sandbox=None,
                  permissions=None, callbacks=[...], hooks=[...])
result = run.resume(request_id, answer)  # or: await run.aresume(...)
run.cancel()
```

- Defaults: `chat=None`, `project=None`, `history=[]`, `store=MemoryRunStore()`, `workspace=None`, `sandbox=None` (code tools then return an error result saying no sandbox is configured), `permissions=Permissions(mode="ask")`, `llm=OpenRouter()` wrapped in the retry layer.
- `Run.load` also recovers a run whose process died while `running` (no pending request): `run.resume()` without arguments continues it from its events. In S1 the run uses `ToolLoop(Assistant())` and reports `loop="tool"` in `run.started`; S2 replaces this with the coordinator, which chooses the loop, without changing this signature.
- `cancel()` stops the run at the next hook point in the same process; across processes the backend uses `Cancellation`.

### Conformance checks (`testing/`)

`gd.testing.check_run_store(factory)` and `gd.testing.check_workspace(factory)`: plain functions that exercise every protocol method and the round trips geomind relies on (event order, checkpoint round trip, history order, state and artifact round trips, missing values), raising `AssertionError` with a clear message. geomind's own tests run them against its memory and file implementations; the backend runs them against its Postgres and MinIO implementations.

### Runtime (`core/runtime.py`)

Context-local settings on `utils.context.ContextSetting`, as in gemini: `default_model` (from `GEOMIND_MODEL`, else a fixed default), `max_steps`. `settings(**changes)` usable as `with` and decorator; `state()`/`load_state()`. Also the retry counts and delays, the tool result size limit, and the sandbox defaults. Also the active run (provider, store, sandbox, callbacks, hooks, permissions, delegate function) as a context variable read by `Agent.complete`, `dispatch` and `Delegate`; documented as an implicit mechanism.

### Public API (`geomind/__init__.py`, pinned by `tests/unit/test_public_api.py`)

`Run`, `Agent`, `Engine`, `Tool`, `tool`, `Prompt`, `Model`, `Output`, `Context`, `Message`, `Action`, `Request`, `Allow`, `Deny`, `Permissions`, `RunResult`, `runlog`, `agents`, `tools`, `loops`, `hooks`, `callbacks`, `providers`, `sandbox`, `stores`, `testing`, `runtime`, `errors`, `__version__`. `gd.stores` exposes `MemoryRunStore`, `FileRunStore`, `MemoryWorkspace`, `FileWorkspace`. `__dir__` shows only these.

### Errors (`errors/`)

`GeomindError` root; `DeclarationError`, `UnknownNameError`, `ProviderError`, `ToolError`, `RunError`, `RequestError`, `CheckpointError`, `ReplayError`, `LoopError`, `SandboxError`, `OutputError`; each also derives from the matching built-in, as in gemini. `errors.md` lists when each is raised. A permission denial is a tool result, not an exception.

### CLI (`cli.py`)

- `geomind run "<message>" [--model ID] [--max-steps N] [--mode ask|auto|readonly|plan] [--sandbox local|docker]`: runs with `OpenRouter` and `FileRunStore(".runs")`, prints text as it streams, asks in the terminal when a request pauses the run, then resumes.
- `geomind replay <run dir>`: offline rerun, prints pass or the first mismatch.
- `geomind show <run dir> [--format md]`: the log per step (agent, prompts, answers, tool calls with inputs and outputs, tokens, cost) and totals, built from `gd.runlog`.

## 5. Steps (commit after each)

### Foundation first (steps 1 to 4, before any agent code)

The framework must be solid before features: every rule written down and checked by a test, every folder in place with its job stated, so later steps (and later sessions) only fill in code.

1. **Rules and docs:** `AGENTS.md` and the complete `.claude/docs/conventions.md`, `testing.md`, `errors.md`, `contracts.md` and `api.md`, written from gemini's general rules and section 1 above, not stubs. `conventions.md` holds the dependency order, naming, comments, code quality, implicit mechanisms and the parallels table. The other docs (`agents.md`, `engine.md`, `tools.md`, `providers.md`, `hooks.md`, `runtime.md`, `utils.md`) start with their purpose, the planned API from section 4 and a "Status: planned" line, updated as each step lands. Add `CLAUDE.md` pointing to `AGENTS.md` if gemini has one.
2. **Tooling:** `pyproject.toml` (name `geomind`, deps `pydantic`, `httpx`, `pytest-asyncio` in dev, `gemini` as editable path `../gemini`; dev deps as in gemini, including `pytest-xdist`), Black/isort/Flake8 config, Makefile (`make test` = development profile, `make test-all`, `make lint`, `make format`), `.gitignore` (`.tmp/`, `.runs/`), a pre-commit config if gemini has one, and a CI workflow like gemini's (lint, development profile on pull requests, full suite on `main`).
3. **Skeleton:** every package of section 2 created with an `__init__.py` whose docstring states the package's job and what it may import; `utils/` (RemovableHandle, ContextSetting, time, json helpers) and `errors/` (every class) implemented in full, since everything else builds on them. No other code yet.
4. **Quality gates:** `tests/unit/test_package_boundaries.py` with the full order of section 2; `tests/unit/test_code_quality.py` with every check of section 1; `tests/unit/test_public_api.py` with the final list of section 4 (names not built yet are marked expected-to-fail and turned green as each step lands); a test that every link in `AGENTS.md` and `.claude/docs/` resolves; `scripts/test_changed.py`; root `conftest.py` with the 300 s development-profile guard and the slowest-tests report; `tests/fixtures/`. From here on every step is checked by these gates.

### Features

5. **Types and runtime:** all public and internal events with the contract JSON test, redaction, and `runlog`.
6. **Providers:** protocol, retry layer, `FakeLLM`, `OpenRouter` (fake transport).
7. **Sandbox:** protocol, `Manifest`, `LocalSandbox`, `DockerSandbox` (marker-gated test).
8. **Tools:** `Tool` with effects, `@tool`, async dispatch with timeouts and retries, `ask_user`, `finish`, code tools.
9. **Agent and prompts:** `Agent`, `AgentResult`, `Prompt`, `Model`, `Output`, `Assistant`, `assistant.md`.
10. **Engine and log:** steps, write order, context builder, callbacks, events, `EventLog`, concurrent read and compute tools.
11. **Hooks, permissions and requests:** the decision table, the permission order and modes, the shipped hooks; pause with checkpoint.
12. **Stores, workspace, conformance:** both stores (all eight methods), both workspaces, `gd.testing` checks run against them, large tool results as artifacts.
13. **Recovery, resume and replay:** `recover(events)`, `Engine.resume`, `Engine.replay`; tests that (a) pause, rebuild everything from a `FileRunStore` in a fresh engine, and resume to the same answer and events as an uninterrupted run; (b) kill a run between a logged completion and its tool results and continue it without a second LLM call; (c) recovery from events alone equals recovery from the checkpoint.
14. **Delegate:** nested run, child run id, its own sandbox, `parent` on events, summary limit, nested steps in `runlog`.
15. **Loops and Run:** `Loop`, `ToolLoop`, loop state in checkpoints, `gd.Run` with `start`, `astart`, `load`, `resume`, `aresume`, `cancel`.
16. **CLI and examples:** the three commands; `examples/basics/general/01_hello.py`, `02_custom_agent.py`, `03_approval.py`, `04_sandbox.py` (the model writes and runs a small Python calculation in `LocalSandbox`), and `examples/backend/general/01_queue_and_resume.py`, which shows the backend flow: start in one function, pause on approval, `Run.load` and `resume` in another, with events forwarded as SSE lines. Each runs with `FakeLLM` by default and `--live` for OpenRouter.
17. **Docs pass:** every document matches the code; `AGENTS.md` "Start here" lists them; `.claude/docs/contracts.md` maps every contract item to its code.

## Done when

- Every item of contracts.md sections 2 and 3 exists, is exported, is tested, and is listed in `.claude/docs/contracts.md`.
- `geomind run` works with OpenRouter; `geomind replay` reproduces it offline; `geomind show --format md` prints the log with prompts, answers and tokens.
- `RequireApproval` pauses a run; `Run.load(...).resume(...)` continues it in a fresh process; `TokenBudget` stops it with `stop_reason="denied"`; `Cancellation` stops it with `cancelled`.
- A run killed mid-step continues without repeating its recorded LLM call; recovery from events equals recovery from the checkpoint.
- `run_python` runs in `LocalSandbox` with no environment keys; the permission order is tested rule by rule; `readonly` and `plan` modes run no `write` or `execute` tool.
- A `Delegate` call shows as a nested run in `gd.runlog` and `geomind show`.
- All tests pass with `FakeLLM` only, the development profile stays under 300 s, Flake8 is clean.
- `AGENTS.md` and `.claude/docs/` describe the rules, layout, parallels, API and every implicit mechanism.

## Report back

What was built; every place geomind departs from gemini's conventions and why; anything in contracts.md that should change (say it before changing code that depends on it); anything gemini lacks for S2 (module metadata, catalogue, plant templates, economics); test time of the development profile; the token cost of one live `geomind run`.

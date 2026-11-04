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
- **First action of the task:** write each appendix at the end of this file to its target path under `../docs/` (create the folder; overwrite older copies), verbatim. Then read them: `../docs/geomind-design.md` (the agreed design), `../docs/contracts.md` (version 2; sections 2 and 3 are what you implement), `../docs/agent-engineering-layers.md`, `../docs/open-source-harnesses.md`, `../docs/phases.md`.
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

---

# Appendices: shared docs to write first

Each appendix is the full content of one file. Write it exactly, between the two marker lines (markers excluded). The file ends after Appendix 5.

## Appendix 1: `../docs/geomind-design.md`

<<<<<<<<<< BEGIN ../docs/geomind-design.md
# geomind design proposal (draft 1, 2026-10-30)

Answers to the ten open questions in the design brief, for discussion with Sahand. Nothing here is final until he agrees. Every name has its reason next to it.

Facts checked in gemini `refactor` (commit `80cd26b`, 2026-10-30 02:21) that shape this design:

- gemini now ships real heat and cold equipment: `HeatPump`, `AbsorptionUnit`, `AdsorptionChiller`, `Boiler`, `ThermalStorage`, `IceStorage`, `HeatConsumer`, `CoolingConsumer`, plus plants `HeatingSubstation`, `CoolingSubstation`, `DistrictNetwork`, `AtesPlant`, `Doublet`. Our old note "HX, boiler and filter are empty classes" is out of date.
- Every declaration exposes `schema` (Pydantic JSON schema), `quantity` and `unit`. `Module.help()` reads the docstring. So tool schemas can be generated, nothing written twice.
- gemini has **no class registry or catalogue** on purpose, and **plants are handwritten classes**: a plant file fills a tree but cannot create wiring.
- `Cost` (capex, fixed and variable opex, currency, price year, source) and `total_cost(plant)` exist. LCOH and CO2 do not.
- gemini forbids naming the framework its module design resembles, in any tracked file. geomind should adopt the same rule.

---

## 1. The Agent class

**One sentence:** an `Agent` is to one decision what a `Module` is to one tick. It turns a context into an action and never loops by itself.

```python
class Analyst(gd.Agent):
    """Runs simulations and reads results."""

    def __init__(self):
        super().__init__()

        # Agents
        self.reviewer = Reviewer()

        # Prompt
        self.prompt = gd.Prompt("analyst")

        # Tools
        self.simulate = gd.tools.gemini.simulate
        self.read_result = gd.tools.gemini.read_result
        self.review = gd.tools.Delegate(self.reviewer)

        # Model
        self.model = gd.Model("anthropic/claude-sonnet", temperature=0)
```

- Constructor sections `# Agents`, `# Prompt`, `# Tools`, `# Model`, in that order, the same idea as gemini's `# Modules`, `# Parameters`, ... . Assigning registers, like `Module.__setattr__`: a `Tool` goes to the tool registry, an `Agent` becomes a child with a dotted path (`coordinator.analyst`).
- Listings like gemini: `agent.tools(recurse=False)`, `agent.named_agents()`, `agent.path`, `agent.name`, `Agent.help()`.
- `forward(self, context) -> Action`. `Action` = text plus tool calls (the industry term from the observe/act cycle). The default `forward` is two lines: render the context with the prompt and tools, call `self.complete(messages)`. Override `forward` only for a rule-based step (for example a coordinator that routes some messages without the LLM).
- `self.complete(...)` uses the provider of the running run, read from a context variable, exactly as a module reads its running `_Call`. The agent declares *which model*; the run supplies *which provider*. So agents stay free of keys and HTTP.
- `agent(context)` returns `AgentResult` (action, messages sent, usage, duration), built by `Agent.__call__`, as `ModuleResult` is built by `Module.__call__`. Call order: `before_llm_call` hooks → `forward` → `on_llm_call` callbacks.
- **No `Team` class in S1 (recommended).** In gemini, `Sequential` exists because module wiring is data flow. Between agents, the order is a *policy*, and policies are loops (`makerchecker`, `design`, `compare`). A child agent is used through a `Delegate` tool or by a loop. If a fixed list of agents is ever needed, add `AgentList`/`AgentDict` then, like `ModuleList`/`ModuleDict`.

## 2. Engine vs loop

**The line:** the engine runs *one agent until it stops*; the loop decides *which run comes next and when the goal is met*. Same as gemini: `Engine.replay` runs a plant over a clock, `optim.calibrate` decides which replay to run next.

- **Engine step** = one agent call + the dispatch of its tool calls + their observations appended + one checkpoint. Events: `step.started`, `text.delta`, `tool.started`, `tool.finished`, `step.finished`.
- `Engine(callbacks=None, hooks=None).run(agent, context, max_steps=30) -> RunResult`. It stops on exactly one of: final answer (no tool calls), `finish` tool, a `Request` (status `waiting`), a hook stop, the step limit, cancellation, an error. The stop reason is a field of `RunResult`, never inferred.
- Finite, like gemini's engine: no sleeping, no scheduling, no threads of its own.
- **Loop** = `gd.loops.Loop` subclass with `run(engine, task) -> RunResult`. It owns the goal, the order of agents, the code verifiers between runs, and the stop rules. `ToolLoop` is one engine run of one agent. `DesignLoop` is: run designer → verify by code → write failures to the problem state → repeat until pass, budget or round limit.
- **Loop state is checkpointed.** A loop keeps its position in a small `state_dict()` (round, phase, best design so far), saved inside the run checkpoint. A loop is written as resumable steps, never as one long Python function holding state in local variables. This is what makes a pause in round 3 of a design loop resumable in another process.

## 3. Problem state

A Pydantic model `ProblemState` in `core/context/state.py`, the shared "notes outside the window":

```text
goal            text of the task
requirements    id, text, metric, target, tolerance, status (testable criteria)
assumptions     id, text, value, source (user | agent | default), confirmed
design          current plant reference (template + parameters) and its rationale
results         id, summary, reference to the stored full data
verification    last verifier report per check
questions       open questions for the user
```

- **Writers:** the model only through tools (`update_state` with explicit operations such as `add_requirement`, `set_assumption`), the engine for results and verifier reports. Every change is an event `state.changed`, so the log shows how it evolved.
- **Shown to the model:** rendered compactly *after* the stable prefix (system prompt and tool schemas) and the history, re-rendered every step, never appended, so the model always sees the current state once and the stable prefix stays cacheable (see 11.6).
- **Compaction:** it lives outside the message history, so compaction never touches it.
- **Checkpoints:** stored whole in every checkpoint; and per chat, so the next message continues it (contract change in section 8).
- Generic in shape, domain-specific in content: geomind core knows no geothermal words.

## 4. Tools from gemini

- **Few generic tools, not one per module (recommended, changes S2 draft).** ~45 equipment classes as 45 tools is the "bloated tool set" failure mode. Instead: `list_modules(category)`, `describe_module(name)` (schema from `Module.help()` and each declaration's `schema`, `unit`, bounds), `evaluate_module(name, parameters, inlets, controls)`, `list_plants`, `configure_plant(template, parameters)`, `simulate(plant, profile)`, `read_result(reference, path, field, start, end)`, `search_documents(query)`.
- The catalogue (name → class, category) lives in `geomind/tools/gemini.py`, built from `gm.modules` exports and their sub-package (`heat`, `pumps`, ...). It is geomind's index of gemini, so gemini needs no registry.
- **Large results:** stored through the store (see 8), returned as `{reference, summary}`; the summary gives min, max, mean and unit per field. `read_result` fetches a slice.
- **Errors are results:** a `gm.errors.*` or Pydantic validation error comes back as `{error: {class, message}}` with `is_error=True`, so the model fixes its call. gemini's close-match suggestions pass through. Any other exception is a bug: recorded, reported by `on_error`, and the tool result says "internal error".
- A tool is `gd.Tool(name, description, input_schema, function)`, or `@gd.tool` on a typed function (schema from the signature and docstring). Dispatch adds timing and the call id.

## 5. Hooks and requests

Three hook points; each returns one of four decisions:

| Decision | `before_llm_call` | `before_tool_call` | `before_finish` |
|---|---|---|---|
| `None` (allow) | call | call | finish |
| `gd.Deny(reason)` | run stops, reason logged | tool skipped, reason is the tool result | finish refused, reason fed back to the model |
| `gd.Request(...)` | pause | pause before the tool | pause before the answer |

- `before_finish` + verifiers is how "no design reaches the user unverified" is **enforced mechanically**: the `Verified` hook denies `finish` until every verifier passes.
- `Request(kind="approval" | "question", message, options=None)` gets an id. The engine saves a checkpoint holding the pending action (the exact tool call), emits `request`, and returns `RunResult(status="waiting", request=...)`. The process may exit.
- **Resume** in another process: `run = gd.Run.load(run_id, llm=, store=, workspace=, callbacks=, hooks=)` then `run.resume(request_id, answer)`. Approval runs the stored tool call without asking that hook again for the same call id; a denial becomes the tool result; an answer to `ask_user` becomes its result. The engine continues the step, then the loop continues from its saved state. Hooks and callbacks are code and are passed again, as in `gm.Engine.load_checkpoint(path, callbacks)`.
- **Cancel** across processes: built-in hook `gd.hooks.Cancellation(is_cancelled)` with a function the backend gives (reads Redis). `run.cancel()` stays for the same process.
- Shipped hooks: `TokenBudget`, `CostBudget`, `RequireApproval(tools=...)`, `Cancellation`, `Verified` (S3). Registration returns a handle with `.remove()`, as in gemini.

## 6. Multi-agent

- **Shared problem state, isolated conversations.** All agents read and write the one `ProblemState` (the blackboard). Each sub-agent gets a clean window: its prompt, the task text from the delegating agent, and the rendered state; never the parent's message history.
- **Delegation is a tool:** `gd.tools.Delegate(agent)` runs a nested engine run with a child run id and returns a short summary (token-limited) plus the state changes. No agent-to-agent chat messages.
- **Log:** every event carries the agent path (`coordinator.designer`) and the parent step, so the full nested transcript is in the competition log while the parent only saw the summary.
- Parallel delegates (S4 compare) run in a thread pool with `contextvars.copy_context()`, the same rule as gemini's runtime docs. S1 stays sequential.

## 7. Public API

```python
import geomind as gd

result = gd.Run(message="What heat does the example doublet deliver?",
                llm=gd.providers.OpenRouter(model="...")).start()
print(result.answer, result.usage)
```

Defaults: `MemoryRunStore`, no workspace, the `Coordinator` agent, which picks the loop.

Top level (pinned by a public-API test, as in gemini): `Run`, `Agent`, `Engine`, `Tool`, `tool`, `Prompt`, `Model`, `Context`, `Action`, `Request`, `Deny`, `RunResult`, `ProblemState`, and the namespaces `agents`, `tools`, `loops`, `hooks`, `callbacks`, `providers`, `verify`, `runtime`, `errors`, `__version__`.

`Run` is the façade the backend uses (interfaces, coordinator, loop choice, resume). `Engine` is the lower layer for tests, evals and custom loops, like `gm.Engine`.

## 8. Contract changes (section 3 of contracts.md)

1. `LLM.complete(messages, tools, *, model, settings, on_text=None) -> Completion`. Streaming as a text callback instead of `stream=True`, so the result type is always one `Completion`. `settings` = temperature, max tokens.
2. `RunStore`: add `save_state(chat_id, state)` / `load_state(chat_id)` (problem state across messages) and `save_artifact(run_id, key, data)` / `load_artifact(run_id, key)` (large tool results).
3. Resume needs a loader: `gd.Run.load(run_id, ...)` then `.resume(request_id, answer)`.
4. Events: add `step.finished {index, agent, usage}` and `state.changed {changes}`; add `agent` (dotted path) and `parent` to `step.started`, `tool.*` and `request`; `request` gets `call_id`.
5. `runlog.steps[]` gets `agent` and `parent`, so nested runs show as a tree.
6. The backend does not need to implement `LLM`: it can pass `gd.providers.OpenRouter(api_key=...)`. The protocol stays for tests and other providers.

## 9. What gemini must provide

| Need | Status | Proposal |
|---|---|---|
| Module metadata for tool schemas | exists (`help()`, declaration `schema`/`unit`) | nothing; maybe a `Module.describe()` returning one JSON dict, to avoid geomind walking private structure |
| Catalogue (name, category) | absent by design | geomind builds it from `gm.modules` exports |
| Plants an agent can configure | plants are handwritten; files cannot wire | **gemini adds a few heating-and-cooling plant templates** (wiring in Python, sizes as parameters, unused units switchable); the agent picks a template and sizes it. No physics or wiring in geomind |
| Economics | `Cost`, `total_cost` exist | gemini adds LCOH, annual opex from energy results, CO2 from electricity and fuel outputs |
| Balances for verifiers | `energy_balance`, `mass_balance` exist | check they work on simulated time series, not only one call |

The plant templates are the biggest risk for Challenge 2. The alternative (the agent writes Python plant classes) is powerful but hard to verify and unsafe; recommended only after the hackathon.

## 10. gemini's own agent folders

Answered 2026-10-30: both folders are empty on Sahand's machine. Decision: delete them from gemini (in the next gemini prompt); all agent logic lives in geomind, design physics (plant templates, sizing, economics) in gemini.

## 11. Harness, version 2 (after reviewing current harnesses)

Sahand asked for a structure that will not need to change later, including the sandbox. The review is in `open-source-harnesses.md`. Seven additions, all structural, all in S1:

### 11.1 Session log is the source of truth

The run's append-only event log (in `RunStore`) is authoritative. Every LLM completion and every tool result is saved as an event **before** the engine acts on it. A checkpoint is only a snapshot of the log for speed. Resume, crash recovery and replay are the same mechanism: rebuild from events, reuse recorded completions and results, never call them again. The engine itself holds no state that is not in the log, so any process can continue a run (as Managed Agents' stateless harness does).

Events therefore come in two groups: **public** (the SSE types of contracts.md section 2) and **internal** (`llm.completed` with the full completion, `tool.result` with the full output, `permission`, `retry`, `sandbox.provisioned`, `checkpoint`). The store saves all; the backend streams only public ones (`event.is_public`).

### 11.2 Side effects only in two places

LLM calls (`providers`) and tool calls (`tools.dispatch`) are the only side effects. Everything else in the engine and loops is deterministic code over the log. This is what lets a durable executor (Temporal, as Pydantic AI does) wrap them later without a redesign. Tools declare `idempotent`; after a crash, a started tool with no recorded result is rerun only if idempotent, otherwise it becomes an error result for the model.

### 11.3 Async core, sync façade

The engine is `async` inside (parallel tool calls, parallel delegates in the compare loop, streaming, FastAPI). Sync tools such as gemini calls run in a worker thread with a copied context. The public API stays simple: `run.start()` and `run.resume()` are sync (they run the event loop); `await run.astart()` and `await run.aresume()` exist for async callers. Changing sync to async later would touch every layer, so it is decided now.

### 11.4 Sandbox: the "hands" for code

Our gemini tools run in-process: they are trusted library calls. Code the model writes is not, and Challenge 1 asks the agent to *fill missing models*, which means writing and testing new gemini modules. So:

```python
class Sandbox(Protocol):
    async def execute(self, command, *, timeout) -> ExecutionResult: ...   # exit code, stdout, stderr, duration
    async def write(self, path, data): ...
    async def read(self, path) -> bytes: ...
    async def close(self): ...

class SandboxProvider(Protocol):
    async def provision(self, manifest) -> Sandbox: ...
```

- `Manifest`: what goes in (files, the gemini package read-only, Python version), limits (CPU, memory, time, disk) and `network=False` by default.
- Shipped: `LocalSandbox` (subprocess in a temporary directory, time and memory limits; for development only, clearly documented as not a security boundary) and `DockerSandbox` (no network, read-only gemini, limits; the backend's choice). Others (E2B, Modal) fit the same protocol later.
- Provisioned lazily, on the first tool that needs it, once per run; sub-agents get their own. A lost sandbox is a tool error the model can recover from.
- **No credentials ever enter a sandbox**, and secrets are redacted from events.
- Tools on top: `run_python(code)`, `write_file`, `read_file`; S3 adds `test_module(path)`, which runs gemini's module rules and tests on a new module inside the sandbox. A model-written module is only ever run inside the sandbox, never imported into the harness process.

### 11.5 Permissions: declarative, in a fixed order

Every tool declares an `effect`: `read`, `compute`, `write`, `execute` (sandbox code), `external` (network or anything outside the run). Each call is decided in one documented order, adapted from the Claude Agent SDK:

1. `before_tool_call` hooks (may deny or request; an allow does not skip the rules);
2. deny rules;
3. ask rules (always become a `Request` to the user);
4. allow rules (let a `write`, `execute` or `external` tool run without asking in `ask` mode; never override `readonly` or `plan`);
5. the mode: `auto` (allow all), `ask` (ask for `write`, `execute`, `external`; the default), `readonly` (deny all but `read` and `compute`), `plan` (no tool runs; the agent only proposes).

Allow rules come before the mode (unlike the Claude Agent SDK), because here the mode decides every remaining call; found by Claude Code's review of the S1 prompt.

`gd.Permissions(mode="ask", allow=[...], ask=[...], deny=[...])`, rules by tool name or effect. A decision is `Allow(input=None)` (optionally with a changed input), `Deny(reason)` or `Request`. `RequireApproval` becomes a shortcut for an ask rule. Every decision is a `permission` event, so the log shows why each tool ran.

### 11.6 Context builder

One component (`core/engine/context.py` now, `core/context/` in S2) builds every LLM call from the log: stable prefix first (system prompt, tool schemas, agent docs), then history, then the dynamic part (problem state, budget left) last, so prompt caching works. Large tool outputs stay in the log or as artifacts; the model sees summaries and references. **Skills** (`.md` instructions loaded on demand through a `read_skill` tool, for example "how to write a gemini module" from gemini's `modules.md`) go in `core/prompts/skills/` from S2.

### 11.7 Reliability details fixed now

- Providers: retries with backoff on 429 and 5xx, a fallback model list, request timeout; each retry is a `retry` event.
- Tools: timeout per tool, `max_retries` for validation errors fed back to the model.
- Typed output: an agent may declare `# Output` (a Pydantic model); the final answer is validated and a failure is sent back to the model, up to a limit. The design report in S3 uses this.
- Limits: steps, tokens, cost, tool calls, wall time, all as hooks.
- Stable identifiers: tool names, event types and checkpoint version never change silently; a change is a new version.
- Tool sources: `Tool` is a protocol, so MCP toolsets (`gd.tools.mcp(url)`) and exposing gemini tools as an MCP server fit later without changes.

## Impact on the phases

- S1 adds: `Agent` registry and sections, `Action`/`AgentResult`, resumable loop state, `Run.load`, `Deny`, `Cancellation`.
- S1 drops: `Team`.
- S2 changes: generic gemini tools instead of one tool per module; `ProblemState` writers and rendering as above; store contract additions.
- S3 adds: `Verified` hook on `before_finish`; depends on gemini plant templates and economics (a gemini prompt, outside geomind).
>>>>>>>>>> END ../docs/geomind-design.md

## Appendix 2: `../docs/contracts.md`

<<<<<<<<<< BEGIN ../docs/contracts.md
# Contracts between the repos

Version 2 (2026-10-30: sections 2 and 3 updated by the geomind design). Covers steps 1 and 2 of every repo. Later steps add their routes here before they start.

## 1. HTTP API (frontend ↔ backend)

- Base: `/api/v1`. JSON. Times are ISO 8601 with a timezone, UTC.
- Path = `/<domain>/<feature>/...`, the same names as the folders in both repos.
- Auth: bearer access token from `identity/authn`; refresh as the backend already does.
- Errors: `{"error": {"code": "<snake_case>", "message": "<human text>", "details": {...}}}` with a matching HTTP status. Codes are stable; messages may change.
- Lists: `{"items": [...], "next": "<cursor or null>"}`.

### identity

| Method | Path | Body → Response |
|---|---|---|
| POST | `/identity/authn/login` | `{email, password}` → `{access_token, refresh_token, user}` |
| POST | `/identity/authn/logout` | → `204` |
| GET | `/identity/me` | → `user` |
| POST | `/identity/me/password` | `{old_password, new_password}` → `204` |
| GET | `/identity/users` | admin → list of `user` |
| POST | `/identity/users` | admin, `{email, name, password, role}` → `user` |
| PATCH | `/identity/users/{id}` | admin, `{role}` → `user` |

`user = {id, email, name, role}`, `role` is `admin` or `member`.

### workspace/projects

| Method | Path | Body → Response |
|---|---|---|
| GET | `/workspace/projects` | → list of `project` |
| POST | `/workspace/projects` | `{name}` → `project` |
| GET | `/workspace/projects/{id}` | → `project` |
| DELETE | `/workspace/projects/{id}` | → `204` |
| GET | `/workspace/projects/{id}/export` | → zip file |
| POST | `/workspace/projects/import` | multipart `file` → `project` |

`project = {id, name, owner, created, updated}`. Only the owner or an admin may read or change a project.

### assistant/chat

| Method | Path | Body → Response |
|---|---|---|
| GET | `/assistant/chat?project={id}` | → list of `chat` |
| POST | `/assistant/chat` | `{project, title?}` → `chat` |
| GET | `/assistant/chat/{id}/messages` | → list of `message` |
| POST | `/assistant/chat/{id}/messages` | `{content}` → `{message, run}` |

`chat = {id, project, title, created}`; `message = {id, chat, role, content, created, run?}`, `role` is `user` or `assistant`.

### assistant/runs

| Method | Path | Body → Response |
|---|---|---|
| GET | `/assistant/runs/{id}` | → `run` |
| GET | `/assistant/runs/{id}/events` | Server-Sent Events, see section 2 |
| GET | `/assistant/runs/{id}/log` | → `runlog` |
| POST | `/assistant/runs/{id}/answer` | `{request, answer}` → `run` (approve, deny, or reply to a question) |
| POST | `/assistant/runs/{id}/cancel` | → `run` |

`run = {id, chat, status, loop, started, ended, usage}`, `status` is `queued`, `running`, `waiting`, `done`, `failed` or `cancelled`. `usage = {input_tokens, output_tokens, cost}`.

`runlog = {run, steps: [{index, agent, parent, llm_calls: [...], tool_calls: [...]}]}`, with `llm_call = {model, messages, answer, input_tokens, output_tokens, cost, duration}` and `tool_call = {call_id, tool, input, output, duration, error?}`. `agent` is the dotted agent path (`coordinator.designer`); `parent` is the parent step of a delegated (nested) run, or `null`. geomind builds this object: `gd.runlog(events)`.

## 2. Live run events (backend → frontend, SSE)

Each event: `event: <type>`, `data: <json>`, `id: <sequence number>`. The stream replays from `Last-Event-ID` on reconnect. Every `data` also carries `agent` (dotted path) and `parent` (parent run id or `null`); they are left out of the table.

| Type | Data |
|---|---|
| `run.started` | `{run, loop}` |
| `step.started` | `{index}` |
| `text.delta` | `{index, text}` |
| `tool.started` | `{index, call_id, tool, input}` |
| `tool.finished` | `{index, call_id, output_summary, duration, error?}` |
| `step.finished` | `{index, usage}` (usage of this step) |
| `state.changed` | `{changes}` (problem state operations; from S2) |
| `request` | `{request, call_id?, kind, message, options?}`; `kind` is `approval` or `question`; the run is `waiting` |
| `usage` | `{input_tokens, output_tokens, cost}` (running totals) |
| `run.finished` | `{status, stop_reason, message?}` |

These are the geomind callback events with `event.is_public` true, forwarded as they are: `event.type` and `event.data()` (JSON-safe). geomind also emits internal events (`llm.completed`, `tool.result`, `permission`, `retry`, `sandbox.provisioned`, `sandbox.closed`, `checkpoint`); the backend saves every event through `RunStore.save_event` but streams only public ones. The internal events are the run's source of truth, used for recovery and the full log. The backend adds no event types of its own.

## 3. geomind interfaces (backend ↔ geomind)

Version 2 (2026-10-30, from the geomind design thread). The backend implements `RunStore` and `Workspace` and passes them in; geomind ships a file and a memory implementation of each, the `OpenRouter` provider (the backend may use it directly instead of its own `LLM`), and `FakeLLM` for tests. All of it exists after geomind S1, so the backend never waits for later geomind phases.

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

# RunStore and Workspace are sync; geomind calls them from a worker thread.

class Workspace(Protocol):
    def plant(self, project_id): ...            # the stored plant as a gemini plant
    def documents(self, project_id, query): ... # document search: [{id, title, text, score}]

class SandboxProvider(Protocol):               # optional; geomind ships LocalSandbox and DockerSandbox
    async def provision(self, manifest) -> Sandbox: ...
```

Entry point used by the backend:

```python
import geomind as gd

run = gd.Run(
    message=content, chat=chat_id, project=project_id,
    history=store.load_history(chat_id),
    llm=llm, store=store, workspace=workspace,
    sandbox=gd.sandbox.DockerSandbox(), permissions=gd.Permissions(mode="ask"),
    callbacks=[publisher],
    hooks=[gd.hooks.TokenBudget(...), gd.hooks.RequireApproval(...),
           gd.hooks.Cancellation(is_cancelled)],
)
result = run.start()                  # or await run.astart(); RunResult: run_id, status, answer, request, usage, stop_reason

run = gd.Run.load(run_id, llm=llm, store=store, workspace=workspace,
                  callbacks=[publisher], hooks=[...])
result = run.resume(request_id, answer)   # or await run.aresume(...); in another process; hooks and callbacks are passed again
result = run.resume()                     # continue a run whose process died while running

run.cancel()                          # same process; across processes use gd.hooks.Cancellation
```

`answer` is `{"approved": true}`, `{"approved": false, "reason": "..."}` or `{"text": "..."}` for a question. `status` values are those of `run` in section 1. A `Message` is `{role, content, tool_calls?, tool_call_id?}` with `role` `user`, `assistant`, `tool` or `system`; `load_history` returns only `user` and `assistant` messages.

The backend never chooses the loop or the agents; geomind's coordinator does.
>>>>>>>>>> END ../docs/contracts.md

## Appendix 3: `../docs/agent-engineering-layers.md`

<<<<<<<<<< BEGIN ../docs/agent-engineering-layers.md
# Prompt, context, harness and loop engineering

Research notes, 2026-10-30. Four nested layers of building with LLM agents, and what each means for the GEMINI agent harness.

```
loop  ⊃  harness  ⊃  context  ⊃  prompt
```

| Layer | Question it answers | Unit of work |
|---|---|---|
| Prompt | Did I say it clearly? | one message |
| Context | Does the model see the right information? | one model call |
| Harness | Does it keep doing it right, safely? | one agent run |
| Loop | Does it run, check and improve without me? | many runs toward a goal |

(Framing from AI Builder Club; the other sources agree the layers nest rather than replace each other.)

## 1. Prompt engineering

Writing and organising the instructions of a single interaction: role, task, format, examples. The oldest layer, still needed, but no longer enough for agents that run many steps.

## 2. Context engineering

- **Origin:** popularised June 2025. Karpathy: "the delicate art and science of filling the context window with just the right information for the next step."
- **Anthropic's definition:** "the set of strategies for curating and maintaining the optimal set of tokens during LLM inference". Goal: "the smallest possible set of high-signal tokens that maximize the likelihood of some desired outcome."
- **Why:** context rot. Recall falls as the window fills, so context is a finite attention budget.
- **Techniques:**
  - System prompt at the "right altitude": between brittle if-else rules and vague guidance.
  - Few, non-overlapping, token-efficient tools. A bloated tool set is a top failure mode.
  - A few canonical examples instead of a list of edge-case rules.
  - Just-in-time retrieval: keep references (paths, IDs) and load data through tools when needed.
  - Compaction: summarise and restart when the window fills.
  - Structured notes outside the window (a NOTES.md, a to-do list), read back later.
  - Sub-agents with clean windows that return short summaries.
  - LangChain's four moves: write, select, compress, isolate.
- **Failure modes:** poisoning, distraction, confusion, clash.

## 3. Harness engineering

- **Origin:** early 2026. OpenAI's "Harness engineering: leveraging Codex in an agent-first world" (Ryan Lopopolo, 11 Feb 2026); the name is credited to Mitchell Hashimoto. "Agent = Model + Harness."
- **Definition (deepset):** "the discipline of designing the systems, constraints, and feedback loops that wrap around an AI model to make it reliable in production." The harness is everything except the model.
- **Components:**
  - Tools and their permission scopes.
  - Guardrails, permissions and approvals.
  - Verification: tests, validators, linters whose error messages tell the agent how to fix the problem, LLM-as-judge.
  - Docs as a map: a short AGENTS.md pointing into a structured docs folder. One huge instruction file failed at OpenAI.
  - Memory and progress files.
  - Observability: traces, logs, metrics, replay.
  - Sandboxes and isolation.
- **Main lesson:** after each failure, classify it (context, constraint, verification or planning) and fix that layer, so the same mistake cannot happen the same way again. "Constrain more, not less." Enforce rules mechanically, not in prose.

## 4. Loop engineering

- **Origin:** mid-2026, made popular by posts from Boris Cherny (Claude Code) and Peter Steinberger; Addy Osmani: "Loop engineering is replacing yourself as the person who prompts the agent." ADTmag notes it may be "more of a developer shorthand than a formal discipline."
- **Definition (IBM):** "designing agentic workflows, or loops, that iteratively guide AI agents toward completing user-defined goals" with minimal human intervention.
- **Stages:** goal → action → observation → adjustment (Kilo adds intent and context before action).
- **Practices:**
  - Goals with testable stopping criteria ("stop when all unit tests pass", not "make it faster").
  - Strong observations: "a loop is only as good as its observations."
  - Stopping rules: success, a blocker that needs a human, a destructive step, leaving scope, a failure or cost limit.
  - Triggers: schedules, CI events, hooks.
  - Maker and checker: one agent works, another reviews (but "a checker is still just an agent").
  - A persistent spine: a file or board that records each cycle's outcome.
- **Patterns:** test-driven, compiler-driven, review-driven, runtime debugging, product iteration.
- **Risks:** thrashing, overfitting to the verifier, context drift, unsafe autonomy, token cost ("a weak verifier produces bad answers all night, at token prices").
- **Rule of thumb:** "the loop defines what the agent does and when; the harness defines where it runs, what it can touch, and how it recovers."

## 5. What this means for our harness

| Layer | In our system |
|---|---|
| Prompt | System prompt per agent role; tool descriptions generated from module names and docstrings of the `gemini` package |
| Context | A shared problem state (the geomind idea) as the structured notes; module catalogue and plant data loaded through tools, not pasted; sub-agents per specialty return summaries; compaction for long design runs |
| Harness | Tools = `gemini` package calls; hooks for approval, token budget and access; physics verifiers (mass and energy balance, `gm.check`, bounds) as sensors with fix-it error messages; callbacks for traces and token logs; replay of recorded runs; a short agent map doc |
| Loop | Goal = a design brief with testable criteria (meets heating and cooling demand every hour, balances close, cost below X); observation = simulation results; adjustment = change design; stop on success, budget or a question for the user; maker (designer agent) and checker (verifier agent plus numeric checks) |

Our domain has an advantage over coding agents: the verifier can be physics. Energy balances, demand coverage and unit checks are hard numbers, not opinions, so loops can be trusted further.

Correction to my earlier proposal: the loop is not one swappable class inside the harness. It is the outer layer. The repo should keep the two apart: `harness` (runtime, tools, guardrails, context, observability) and `loops` (goals, verifiers, stop rules, triggers, maker/checker).

## Sources

- [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [LangChain: Context engineering for agents](https://www.langchain.com/blog/context-engineering-for-agents)
- [Mastra: Context engineering](https://mastra.ai/articles/context-engineering)
- [OpenAI: Harness engineering](https://openai.com/index/harness-engineering/)
- [deepset: Harness engineering](https://www.deepset.ai/blog/harness-engineering)
- [Atlan: Harness vs prompt vs context engineering](https://atlan.com/know/harness-engineering-vs-prompt-engineering/)
- [Louis Bouchard: Harness engineering](https://www.louisbouchard.ai/harness-engineering/)
- [IBM: What is loop engineering?](https://www.ibm.com/think/topics/loop-engineering)
- [ADTmag: Loop engineering emerges](https://adtmag.com/articles/2026/07/01/loop-engineering-emerges-as-developers-put-ai-coding-agents-on-repeat.aspx)
- [Kilo: What is loop engineering?](https://kilo.ai/articles/what-is-loop-engineering)
- [AI Builder Club: Prompt, context, harness, loop](https://www.aibuilderclub.com/blog/prompt-context-harness-evolution)
>>>>>>>>>> END ../docs/agent-engineering-layers.md

## Appendix 4: `../docs/open-source-harnesses.md`

<<<<<<<<<< BEGIN ../docs/open-source-harnesses.md
# How current agent harnesses are built (2026-10-30)

Research for the geomind design: what the main harnesses share, so geomind's structure does not need to change later. Facts from the sources at the end; my reading of them is marked "For geomind".

## 1. Anthropic Managed Agents: brain, hands, session

- Three separate parts: **session** ("the append-only log of everything that happened"), **harness** (the loop that calls the model and routes tool calls), **sandbox** (where code runs).
- The harness runs *outside* the container. Every "hand" has one shape: `execute(name, input) -> string`. Containers are created on demand (`provision({resources})`), only when a tool needs one; this cut time to first token by about 60% at p50.
- The harness is **stateless**. After a crash: `wake(sessionId)`, `getSession(id)` returns the event log, and a new harness continues from the last event (`emitEvent(id, event)` writes).
- A lost container is just a tool error given to the model, which can provision a new one.
- **Credentials never reach the sandbox**; MCP calls go through a proxy that fetches credentials from a vault. The harness itself never sees them either.
- The session lives outside the context window; the harness reads slices of events and transforms them into the prompt (for example, ordered for prompt-cache hits).

For geomind: the event log, not the checkpoint, is the source of truth; a checkpoint is a fast snapshot of it. Code execution is a separate, replaceable "hand".

## 2. OpenAI Agents SDK (April 2026 update)

- "Separating harness and compute helps keep credentials out of environments where model-generated code executes." Externalised state lets a lost sandbox be replaced without losing the run (snapshot and rehydrate).
- Sandbox providers are pluggable (E2B, Modal, Daytona, Cloudflare, Vercel, Runloop, Blaxel, or your own); `SandboxAgent`, `Manifest` (describes the workspace files: local dirs, S3, GCS, ...), `SandboxRunConfig(client=...)`, `UnixLocalSandboxClient` for local work.
- Primitives: MCP, skills (instructions loaded on demand: "progressive disclosure"), `AGENTS.md`, shell tool, apply-patch tool, file tools, configurable memory. Sub-agents can each get their own sandbox.

For geomind: a `Sandbox` protocol with a local and a container implementation, and a manifest of what files go in.

## 3. Claude Agent SDK: permissions

Fixed evaluation order for every tool call:

1. hooks (can deny; an "allow" from a hook does not skip the rules below);
2. deny rules (deny wins even in the most permissive mode);
3. ask rules (always reach the user callback);
4. permission mode (`default`, `dontAsk`, `acceptEdits`, `plan`, `bypassPermissions`, `auto`);
5. allow rules;
6. the `canUseTool` callback.

A decision is allow (optionally with an **updated input**) or deny with a message for the model.

For geomind: permissions are declarative rules plus a mode, evaluated in one documented order, separate from hooks; tools declare their effect so rules can be written per effect.

## 4. LangGraph: durable execution

- Checkpoints per step through a `BaseCheckpointSaver` (`put`, `put_writes`, `get_tuple`, `list`); resume needs a thread id.
- Durability modes: `exit`, `async`, `sync` (persist before the next step).
- Writes of tasks that finished inside a failed step are kept as "pending writes", so they are not run again on resume. Work after the checkpoint runs again, including LLM calls; side effects must therefore be idempotent or wrapped as recorded tasks.
- Pause and resume through `interrupt()` and a resume command.

For geomind: record each LLM completion and each tool result as an event *before* acting on it; on resume, recorded results are reused, never recomputed.

## 5. Pydantic AI: typed agents and durability

- Dependencies are injected into tools through a run context; typed outputs are validated, and a failed validation is sent back to the model to retry.
- Durable execution through Temporal, DBOS or Prefect: model requests and tool calls become *activities* (recorded side effects); the rest of the loop is deterministic workflow code. Activity names "must essentially never change". Tools should be `async`.

For geomind: keep LLM calls and tool calls the *only* side effects, each behind one function, so a durable executor can wrap them later without a redesign; give tool and event names stable identifiers.

## 6. What the harnesses agree on

| Primitive | Managed Agents | OpenAI SDK | Claude SDK | LangGraph | Pydantic AI |
|---|---|---|---|---|---|
| Append-only session log | yes | sessions | transcript | checkpoints | message history |
| Stateless, resumable loop | yes | yes | resume | yes | durable exec |
| Sandbox behind an interface | yes | yes | settings sandbox | no | no |
| Credentials outside the sandbox | yes | yes | yes | n/a | n/a |
| Declarative permissions + callback | approvals | approvals | yes | interrupts | approvals |
| Hooks before/after tools | yes | guardrails | yes | n/a | n/a |
| Skills loaded on demand | yes | yes | yes | no | no |
| MCP tools | yes | yes | yes | adapters | yes |
| Typed final output | n/a | yes | yes | n/a | yes |
| Side effects as recorded steps | events | snapshots | n/a | tasks | activities |

## Sources

- [Anthropic: Scaling Managed Agents, decoupling the brain from the hands](https://www.anthropic.com/engineering/managed-agents)
- [OpenAI: The next evolution of the Agents SDK](https://openai.com/index/the-next-evolution-of-the-agents-sdk/)
- [Claude Agent SDK: permissions](https://code.claude.com/docs/en/agent-sdk/permissions)
- [LangGraph: persistence and checkpointers](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [Pydantic AI: durable execution](https://pydantic.dev/docs/ai/api/pydantic-ai/durable_exec/)
- [dev.to summary of Managed Agents architecture](https://dev.to/luhuidev/anthropic-managed-agents-2026-agent-harness-architecture-for-production-ai-agents-3899)
>>>>>>>>>> END ../docs/open-source-harnesses.md

## Appendix 5: `../docs/phases.md`

<<<<<<<<<< BEGIN ../docs/phases.md
# Implementation phases

Three repos move forward in parallel, each with its own phases. They meet only through the contracts in [contracts.md](contracts.md), so no repo waits for another to start.

```
crust-team/
├─ frontend/   React + Vite + Tailwind      → talks to backend through the HTTP API contract
├─ backend/    FastAPI                       → uses geomind through the geomind interface contract
├─ geomind/    agent package                 → uses gemini as a library
├─ gemini/     physics and engine (existing)
└─ infrastructure/  docker-compose (small; done inside backend phase 1)
```

## Phases per repo

| Step | Backend | Frontend | geomind |
|---|---|---|---|
| 1 | [B1 Foundations](backend/phase-1-foundations.md) | [F1 Shell](frontend/phase-1-shell.md) | [S1 Engine](geomind/s1-engine.md) |
| 2 | [B2 Assistant](backend/phase-2-assistant.md) | [F2 Assistant](frontend/phase-2-assistant.md) | [S2 Tools and context](geomind/phase-2-tools-and-context.md) |
| 3 | [B3 Plant and time series](backend/phase-3-plant-and-timeseries.md) | [F3 Plant model](frontend/phase-3-plant.md) | [S3 Design agents](geomind/phase-3-design-agents.md) |
| 4 | [B4 Well performance](backend/phase-4-performance.md) | [F4 Time series](frontend/phase-4-timeseries.md) | [S4 Compare and evals](geomind/phase-4-compare-and-evals.md) |
| 5 | | [F5 Well performance](frontend/phase-5-performance.md) | |

Later, after the hackathon: `integrity` and `reporting/regulatory`.

## How parallel work stays in sync

- **Contracts first.** `contracts.md` fixes the HTTP routes and payloads for steps 1 and 2, the live event types, and the geomind interfaces. Each repo builds against the contract, not against the other repo's code.
- **Mocks until the other side exists.** The frontend uses a mock API (MSW) built from the contract. The backend uses `geomind.providers.FakeLLM` and the contract's interfaces; it installs the real geomind as soon as S1 is done.
- **A contract change is a change to `contracts.md` first,** announced to all three. No repo changes a shared route or interface silently.
- **Integration points:**
  - After B1 + F1: the frontend switches from mocks to the real API for identity and projects.
  - After S1: the backend installs geomind (editable, `../geomind`) in B2.
  - After B2 + F2 + S2: the first full chat in the browser with gemini tools.
  - After S3: Challenge 2 designs appear in the browser with no extra backend or frontend work.

## What the competition needs

S1 to S4 plus B2 and F2. Everything else makes the product complete.

## Shared references

Put these in `crust-team/docs/` before starting; every phase refers to them:

```
crust-team/docs/feature-map.md               domains, features, use-cases, folder names
crust-team/docs/agent-engineering-layers.md  prompt, context, harness, loop
crust-team/docs/contracts.md                 contracts.md from this folder
crust-team/docs/phases.md                    this README
```

Legacy inventories, referred to by the porting phases (B3, B4, F3 to F5), stay where they are:

```
crust-team/gemini-legacy-backend-analysis/backend-features.md
crust-team/gemini-legacy-frontend-analysis/frontend-features.md
```

## Rules for every phase

- Folder names: one word, lower case, no underscores, as in the feature map.
- Code quality: simple, readable, just enough code; nesting at most 3; functions about 40 lines at most; no dead or speculative code; no comments inside code (docstrings only, plus fixed section headers).
- Tests: only the tests of changed code and its importers while working, in parallel; the full fast suite before each commit. Never call the network in tests. Temporary files go to `.tmp/` (git-ignored).
- Docs: update `AGENTS.md` and the docs folder in the same commit as the change, so a new session knows the current state.
- Subtasks and subagents use lighter models.
- If something is missing, unclear or risky, stop and say so instead of guessing.
- Commit after each step. Do not push until told to.
>>>>>>>>>> END ../docs/phases.md

<!-- END OF PROMPT -->

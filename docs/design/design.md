# geomind design proposal (draft 1, 2026-10-30)

Answers to the ten open questions in [brief.md](brief.md), for discussion with Sahand. Nothing here is final until he agrees. Every name has its reason next to it.

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
        self.model = gd.Model("deepseek/deepseek-v4.1-flash-1017", temperature=0)
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

Sahand asked for a structure that will not need to change later, including the sandbox. The review is in `../research/open-source-harnesses.md`. Seven additions, all structural, all in S1:

### 11.1 Session log is the source of truth

The run's append-only event log (in `RunStore`) is authoritative. Every LLM completion and every tool result is saved as an event **before** the engine acts on it. A checkpoint is only a snapshot of the log for speed. Resume, crash recovery and replay are the same mechanism: rebuild from events, reuse recorded completions and results, never call them again. The engine itself holds no state that is not in the log, so any process can continue a run (as Managed Agents' stateless harness does).

Events therefore come in two groups: **public** (the SSE types of contracts.md section 2) and **internal** (`llm.completed` with the full completion, `tool.result` with the full output, `permission`, `retry`, `sandbox.provisioned`, `checkpoint`). The store saves all; the backend streams only public ones (`event.is_public`).

### 11.2 Side effects only in two places

LLM calls (`providers`) and tool calls (`tools.dispatch`) are the only side effects. Everything else in the engine and loops is deterministic code over the log. This is what lets a durable executor wrap them later without a redesign. Tools declare `idempotent`; after a crash, a started tool with no recorded result is rerun only if idempotent, otherwise it becomes an error result for the model.

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

Every tool declares an `effect`: `read`, `compute`, `write`, `execute` (sandbox code), `external` (network or anything outside the run). Each call is decided in one documented order, adapted from an agent harness we studied:

1. `before_tool_call` hooks (may deny or request; an allow does not skip the rules);
2. deny rules;
3. ask rules (always become a `Request` to the user);
4. allow rules (let a `write`, `execute` or `external` tool run without asking in `ask` mode; never override `readonly` or `plan`);
5. the mode: `auto` (allow all), `ask` (ask for `write`, `execute`, `external`; the default), `readonly` (deny all but `read` and `compute`), `plan` (no tool runs; the agent only proposes).

Allow rules come before the mode (unlike that harness), because here the mode decides every remaining call; found by Claude Code's review of the S1 prompt. As built in S1, `readonly` and `plan` are checked before the ask rules, so approving an ask rule can never run a `write` tool in `readonly`.

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

## 12. Phase S2 proposal (2026-10-30, for discussion)

The package is now `geomind` (`import geomind as gd`); S1 and S1b are built. S2 makes it useful: real gemini tools, the problem state, long conversations, the coordinator and the first evals.

### 12.1 Order and dependency

S2 depends on the gemini restructure (no `gemini/core`, a class registry, files storing registry names). geomind uses **only gemini's public API** (`import gemini as gm`): the registry, `Module.describe()`, the plant loader. So: gemini restructure first, then S2. Before S2 also do one live OpenRouter run, because evals spend real tokens.

### 12.2 gemini tools (`tools/gemini.py`)

Few, generic, typed, each with an `effect`:

| Tool | Effect | Does |
|---|---|---|
| `list_modules(category=None)` | read | names and one-line summaries from gemini's registry |
| `describe_module(name)` | read | `Module.describe()`: parameters, controls, boundaries, inlets, outputs with units and bounds |
| `evaluate_module(name, parameters, inlets, controls)` | compute | one call of one module, compact outputs |
| `read_plant()` | read | the project's plant from `Workspace.plant`, as a compact tree |
| `simulate(changes, profile)` | compute | a copy of the plant with parameter or control changes, run by `gm.Engine.simulate`; full results as an artifact, summary back |
| `read_result(reference, path, field, start, end)` | read | a slice of a stored result |
| `search_documents(query)` | read | `Workspace.documents` |

Plant templates (`list_plants`, `configure_plant`) wait for gemini's templates and move to S3. Units: inputs accept unit strings (`"150 m3/h"`), outputs state their unit; gemini's `validate` does the conversion, never geomind.

### 12.3 Problem state (`context/state.py`)

- `ProblemState` (Pydantic) with the keys of the contract: `goal`, `requirements`, `assumptions`, `design`, `results`, `verification`, `questions`, plus `version`.
- One tool `update_state(changes)` taking JSON Patch operations exactly as the contract's `state.changed`; validated against the model, then applied, then a `state.changed` event. The event log stays the source of truth: the state is rebuilt from `state.changed` events.
- Per chat: loaded with `load_state(chat)` at run start, saved with `save_state` at run end.
- Rendered last in the context, compact (one line per item), so the cached prefix stays stable.

### 12.4 Long conversations (`context/`)

- `history.py`: the chat history from `load_history`, newest turns verbatim.
- `compaction.py`: past a token threshold (a runtime setting, default 60% of the model window), older turns become one summary message made by a cheap model; the problem state and the last N turns stay verbatim; a `compaction` internal event records it.
- `skills.py` + `prompts/skills/*.md`: instructions loaded on demand by a `read_skill(name)` tool; the system prompt lists only skill names and one line each. First skills: `gemini-units`, `reading-results`, `writing-a-gemini-module` (for S3).

### 12.5 Coordinator (`agents/coordination/coordinator.py`)

- Every run starts with the coordinator: one LLM call on a cheap model with a typed `Output(Route)`: `Route(kind="answer" | "loop", loop="tool", agent="analyst", brief=...)`. A short direct answer ends the run; otherwise `Run` starts the chosen loop with the chosen agent and the brief.
- The route is logged as a normal step, so the competition log shows the decision.
- S3 adds the design loops to the choices without changing the coordinator's shape.

### 12.6 Agents in S2

`Coordinator` (routing), `Analyst` (gemini tools, problem state, documents), `Summarizer` (compaction only). Models per role in `runtime`: cheap for coordinator and summarizer, strong for analyst.

### 12.7 Evals (`evals/`)

- `evals/tasks/<area>/<name>.yaml`: message, plant, and criteria checked by code (numbers with tolerance, a tool that must or must not be called, a question that must be asked).
- `python -m evals.run --tasks basics [--live]`: offline by default from recorded completions; `--live` records new ones.
- Report per task and total: passed, steps, tool calls, tokens, cost, time; written to `evals/reports/`.
- First five tasks on the example doublet: operating point; ESP at another frequency; heat delivered at a given flow; a missing parameter that needs `ask_user`; a module lookup.

### 12.8 Fixes carried over from S1b

- Replace the hidden split string of the old package name with an explicit, documented exception list in the name test.
- `step.finished` carries `text` (the step's full assistant text); stop saving `text.delta` events (stream-only; full text is in `llm.completed` and `step.finished`), export `gd.event_from_dict`, and give tools the workspace through `context.session`.
- Load plants through gemini's public loader (registry names), never by import path; old plant files go through `gm.plants.migrate(old_dict)` first (gemini step 4 stores registry names plus a `format` version).

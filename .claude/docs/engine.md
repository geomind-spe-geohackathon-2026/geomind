# Engine

The engine runs one agent until it stops, over an append-only event log. Loops decide which run
comes next. It is finite: it never sleeps or schedules itself. Code is in `geomind/engine/`.

## Harness principles

1. **The event log is the source of truth.** Every completion and tool result is saved before the
   engine acts on it, and it is the only run state. `apply(state, event)` in
   `recovery.py` is the only code that changes run state: the engine calls it as each event is
   saved, and `recover(events)` calls it on stored events, so the two cannot differ.
2. **Side effects only in two places:** providers and `tools.dispatch`. The rest is deterministic
   code over the log, so a durable executor could wrap those two later.
3. **Async core, sync facade.** Stores and workspaces stay sync and are called through
   `asyncio.to_thread`. `Run` is the sync facade.
4. **Credentials stay in the harness.** Events pass `redact_event` with the known secrets of the
   provider, so a key stays out of the log and the callbacks.
5. **Stable identifiers.** Tool names, event types and the event-log version
   never change silently.

## API

`Engine(callbacks=None, hooks=None, permissions=None, sandbox=None, *, llm=None, store=None,
workspace=None)`. `llm`, `store` and `workspace` are keywords beyond the agreed signature, since a
run needs them. `llm` gets the retry layer, `store` defaults to `MemoryRunStore`, and `permissions`
to `Permissions(mode="ask")`.

- `await run(agent, context, *, max_steps=None, loop=None) -> RunResult`
- `await run_first(agent, context, *, root) -> RunResult`: the routing call, a nested run of `root`
  in its log before `root` starts, with no `parent_step`; `run` of `root` (or `decline`) then
  continues the numbering and starts from its usage, and `recover` adds the usage of such a run
  from its completions, so `RunResult.usage` counts the routing call after a resume too. Delegates
  add theirs with their `tool.result`, and a summary with its `compaction` event.
- `await resume(run_id, request_id=None, answer=None, *, agent=None, loop=None) -> RunResult`
- `await Engine.replay(store, run_id) -> RunResult`
- `register_hook(hook)` returns a handle with `.remove()`; `hooks()` lists them.

## One step

`step.py`: one agent call (its completion logged), the decision and dispatch of its tool calls
(each result logged), then `step.finished` and `usage`. A step is written over the
log: each part looks at the state and does only what is not recorded yet, so a step continues from
any point, after a pause or a crash, without a second LLM call.

Tool calls of one step that are all `read` or `compute` run concurrently, and others run in order.
`ask_user` and `finish` always run alone, because the engine handles what they return. Results of
one step join the history together, in call order, so a replay sees the same prompt whatever
finished first.

A run stops on exactly one reason, in `RunResult.stop_reason`:

| `stop_reason` | `status` | Meaning |
|---|---|---|
| `answer` | `done` | no tool calls: the text is the answer |
| `finish` | `done` | the `finish` tool |
| `request` | `waiting` | paused for the user |
| `denied` | `failed` | a hook denied an LLM call, or the user denied one |
| `step_limit` | `failed` | `max_steps` reached |
| `cancelled` | `cancelled` | `Cancellation` or `run.cancel()` |
| `not_implemented` | `failed` | a stub loop or hook; its message names the phase |
| `error` | `failed` | a provider failed, a tool was called wrongly too often, the output never fit, or any other exception |

A root run that stops on a budget, time or step limit has an `answer` anyway, built from its record
with no LLM call (see [hooks](hooks.md#shipped-hooks)); its `stop_reason` and `status` stay.

Any `Exception` ends the run with `error`, with its class and message in an `error` event, because
a provider made by the backend raises its own errors and a client must see the run end. A dying
process is a `BaseException`, is not caught, and can be recovered.

## Context

`Context(run_id=None, messages=(), *, chat=None, project=None, steps_left=None, problem=None)`.
`messages_for(agent)` renders a stable prefix (system prompt; tool schemas travel beside the
messages), then the history, then the dynamic part last, so prompt caching works. The dynamic part
is the steps left and then the [problem state](context.md), the very last part of every call. It is
never stored in the history.

Before each LLM call of a step, the engine compacts a context that has grown too long; see
[context.md](context.md#long-conversations).

## Callbacks

`Callback` has `on_run_start`, `on_step_start`, `on_llm_call`, `on_text`, `on_tool_start`,
`on_tool_end`, `on_permission`, `on_state_change`, `on_request`, `on_step_end`, `on_error` and
`on_run_end`, plain or `async`, each receiving the engine and one event. `on_event(engine, event)`
receives every event, public and internal, before the specific method, so it is the one method a
publisher needs: forward `event.type` and `event.data()` when `event.is_public`. Callbacks observe only: an exception
in one is an `error` event, reported to `on_error`, and never changes the run. `EventLog(path=None)`
writes JSON lines or keeps events in memory.

## Hooks, permissions, events, tools

See [hooks.md](hooks.md), [permissions.md](permissions.md), [events.md](events.md) and
[tools.md](tools.md).

## Loops


`Loop` has `async run(engine, task)`, `resume(engine, run_id, request_id, answer)`,
`state_dict()` and `load_state_dict(state)`. The state of a loop is logged on `run.started` and in
an internal `loop_state` field of `step.finished`, so a pause inside a loop resumes at the same
place in another process.
Loops are written as resumable steps, never with state held only in local variables.
`ToolLoop(agent, max_steps=None)` is one engine run of one agent.

`DesignLoop(designer, verifier, max_rounds=5)` (`loops/design.py`) runs one root run whose agent is
a rule-based `DesignDriver`. The order is: the designer (size, simulate, self-check, optimise, and
record `design.reference` and `design.result`), the verifier on that final design once, the
`Economist`, the `Explainer`, which finishes the run. The designer's first task names the project's
plant files (`project_plant_names`, read from the workspace without an LLM call; nothing is said
when there are none), so it stores one with `read_plant(project_plant=...)` and `build_plant`
before it sizes or searches. Before designing, a state with no case or a
case without demand makes the driver ask the user (`ask_user`); it stops with `no_case` at
`max_rounds` when the designer still leaves none. After the verifier the driver checks the design
again with gemini (`gd.verify` over the stored run, `verify/design.py`). Pass or fail is `gm.evaluate.verdict` alone. Only a failure sends the
design back to the designer, with a task that routes gemini's failures (name, detail) by their
domain: subsurface, surface, sizing, or coupled (subsurface first). The loop stops on a pass, at
`max_rounds`, when one round fails exactly as the one before, or when an agent asks the user; each
stop is written as `stop: <reason>` in the driver's step text and the answer. A loop that ends
without a pass moves the design to `design.rejected` before it answers, so it never presents it. It
registers the `Verified` hook.

`CompareLoop(designer, verifier, max_rounds=5, concurrency=None)` (name `compare`, driver
`ComparisonDriver`) compares families. The `Designer` plans: the families come from the request or
the case, else it proposes them from `list_plants`, confirmed with `ask_user` or, in an `auto` run,
recorded as unconfirmed assumptions. It records `design.families` and `design.search`. One
`FamilyDesigner` nested run per family designs it (no `set_case`, `save_profile` or `ask_user`) and
adds its entry at `/design/alternatives/-`. `concurrency` (else the setting `compare_concurrency`,
unset meaning one at a time) is how many run in one driver step; a run that may wait for a user,
mode `ask`, always takes one at a time, since a run holds one pending request. A family that
fails or is infeasible keeps its reason and stops nothing. The driver then moves the state's design
to each feasible family, the `Verifier` checks it once and gemini's verdict sets `verified` or
`rejected`. The `Economist` compares the verified ones (`design.comparison`), the driver names the
recommended design, the `Explainer` writes the comparison, and `show --format md` prints the table.

`Delegate(..., runs_beside=True)` lets the delegate calls of one step run together, and
`total_usage` counts a sibling still running and the worst case of every other call in flight, so
a budget covers the whole loop. A bounded call (`TokenBudget(bound_input=True)`, a priced
`CostBudget`, `ProjectBudget`) holds its input bound plus the output tokens it may use, priced
where a price is known (`RunSession.reserve`), until it returns or fails; a call that would pass
the cap with what others hold is not sent, and the run stops with the budget code and a partial
answer. An unbounded cap only refuses once it is reached, as before. A time limit cannot hold an
in-flight call back: it stops the next one. A stop answers with the finished alternatives. `StudyCompareLoop` (driver `CompareDriver`, name
`compare`) is the loop up to 0.4.5: logs and recordings of it run on it, and `loop_for` picks it from
the stored driver class.

A loop whose
`run` raises `NotImplementedYet` is turned by `Run.astart` into `Engine.decline(loop, context,
error)`: a run that starts and ends in the log, with `stop_reason="not_implemented"`. `loop_of(route)` in `run.py` builds the loop a `Route` names.

## Recovery and resume

`recover(events, run_id=None)` folds a log through `apply` into a `RunState` (`engine/state.py`).
`Run.load`, `Engine.resume`, `Engine.replay` and crash recovery all read `store.load_events(run_id)`
and nothing else.

`Engine.resume(run_id, request_id, answer)` rebuilds the state from the log. An unknown or already
answered request raises `RequestError`, and a run that ended
raises `RunError`. Approval runs the stored call without asking again; denial becomes the tool
result; a reply to `ask_user` becomes its result. Without a request, it continues a run whose
process died: the recorded completion is reused, and a started tool without a result runs again
only when `idempotent`; otherwise it becomes an error result for the model. An accepted answer is
logged before the run ends, so a crash after it repeats no LLM call. A nested run left open by a
crash ends with `error`, and its usage goes to the parent. If the crash came after the answer of a
nested request reached the child, `resume()` continues the child, or takes its outcome when it
ended.

## Nested runs

All delegation logic is in `engine/delegation.py`; `tools/delegate.py` stays the tool.
`Delegate` runs an agent through `session.delegate` in a child session sharing the root's
`RunLog`: same store key, same sequence, its own `run_id`, and `parent` set. A pause in the child logs `request` once; the parent logs a `permission` event with
decision `wait` and pauses on the same request id, and an answer to the parent passes down.

## Replay

`await Engine.replay(store, run_id, *, replayed=None, workspace=None)` (`replay.py`) reruns a
stored run and every nested run of its tree, without network and with permissive permissions,
since the log holds the outcome of the original decisions. Each run has its own `FakeLLM` built
from its own `llm.completed` events and its own recording rules (results, refused answers, end of
the recording), keyed by run id because call ids repeat across runs, and within a run by step and call id, because
a model may reuse an id in a later step (ids are unique only within one completion). A nested run that ended with
an answer runs again as a real nested run with its recorded run id; it belongs to the call whose
step and task it started with (`parent_step` and its first message, `_child_calls`), not to every
call open while it ran, so parallel delegates keep their own runs, at any depth. The delegate
call is then not reused: its result comes from the nested run, and the nested run writes its own
state changes. A nested run that did not end with an answer, or any nested run of a run with a
project when no `workspace` is given (the log holds no project files), is reused as before: its
recorded answer, its state changes (`_nested_changes`) and, from the recorded chat's space in the
store, its artifacts. A replayed nested run reads an artifact it did not write itself from there too.
A rule step calls no model, so the replay never stops it. In every run, `read` and `compute` tools
run again; others reuse recorded results, as do calls that were denied or answered. A paused run,
or a nested run still waiting on the user, stops where its log ends. Calls of every run are
compared by their place in the run (the step, then the position in the model's `tool_calls`), and
the end of every finished nested run too. A difference raises `ReplayError` naming the run id,
its agent, the step and the tool. `replayed`, a list, receives the events of the replayed tree,
and the root log names the loop of the recording, so exports of a run and its replay compare.

**A log of another geomind version checks the agents' decisions, not the tools' outputs.** When
the root `run.started` records a geomind version other than the current one, or none (0.3.0), the
replay does not run pure tools (`read`, `compute`): each keeps its recorded result and the problem
state changes of the nested runs it started (`_nested_changes`), because a tool
may have changed its input or output since (0.4.0 added `name` to the study tools). Tools that
write the problem state (`reruns_in_replay`) and the call that ends a run still run. The
completions, the calls, the step order and the answers are still compared. A difference in gemini
alone only reports (`versions differ`) and runs the tools. `Engine.reuses_tools` carries this and
`reuses_tool_results` decides it.

## Stores and workspaces

`RunStore` is the nine-method protocol of the contract, `load_events` and the two chat-artifact
methods included. `MemoryRunStore`
and `FileRunStore(root=".runs")` add `add_message(chat_id, message)`.
`UsageLedger.spent(project_id)` (`gd.stores`) returns the `Usage` of the finished runs of a
project; `MemoryUsageLedger.add(project_id, usage)` and `FileUsageLedger(root)` ship, and
`ProjectBudget` reads one, in a worker thread (`asyncio.to_thread`).
`FileRunStore` writes `<root>/<run id>/events.jsonl` and `artifacts/`, and
`<root>/chats/<chat id>/history.jsonl`, `state.json` and `artifacts/`. Unsafe ids raise
`RunError`.

**Where an artifact lives.** The problem state is per chat, so every artifact it can name is in the
chat's space (`save_chat_artifact(chat_id, key)`): `case/<file name>`, `<sha256>.file`,
`design/<name>`, `study/<name>` and `studies.index`, `result/<id>` and `<id>.results`/`.plant`/`.case`/`.files`, `module/<name>.py`,
and a cut tool output. `RunSession.save_artifact`/`load_artifact` use it, with the chat id of the
run, or its root run id for a run without a chat (a CLI `run`), so nothing changes for that run. The
run's own space (`save_artifact(run_id, key)`) is for what no state names and is not used by the
engine today. `design/<name>` and `study/<name>` are written once: the same content again is fine, other content is a
`ToolError` (path `name`) that asks for a new name, so a result never points at a changed design;
`RunSession` checks it for every caller, so the rule holds for any store.

An artifact key of `FileRunStore` is one safe name, or a [reference](tools.md#references) of the
form `design/<name>`, `study/<name>`, `result/<id>` or `case/<file name>`; any other `/` raises `RunError`.

`Workspace` has `plants(project_id)`, `case(project_id)` and `documents(project_id, query)`.
`MemoryWorkspace(plants, documents, cases)` holds values; `FileWorkspace(root)` reads gemini's
project folder `<root>/<project id>/`: the plant files `plants/*.json` as dicts by file stem, and
text files in `documents/`, searched by keyword count.
`gd.testing.check_run_store` and `check_workspace` are the
conformance checks.

## Replays of stopped runs

`load_loop_state` gives an agent what its loop logged: a replay or a resume rebuilds the driver from
its class, so `DesignDriver` takes `max_rounds` from `run.started.loop_state` and decides as the run
did. A log without it keeps the constructor's value. A run that stopped at a budget, a time limit
or a pending question replays up to the end of its log and ends `cancelled` there: the replay
compares the calls, repeats no hook and asks no model for more.

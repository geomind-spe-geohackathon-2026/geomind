# Engine

The engine runs one agent until it stops, over an append-only event log. Loops decide which run
comes next. It is finite: it never sleeps or schedules itself. Code is in `geomind/engine/`.

## Harness principles

1. **The event log is the source of truth.** Every completion and tool result is saved before the
   engine acts on it. A checkpoint is a snapshot of the log for speed. `apply(state, event)` in
   `recovery.py` is the only code that changes run state: the engine calls it as each event is
   saved, and `recover(events)` calls it on stored events, so the two cannot differ.
2. **Side effects only in two places:** providers and `tools.dispatch`. The rest is deterministic
   code over the log, so a durable executor could wrap those two later.
3. **Async core, sync facade.** Stores and workspaces stay sync and are called through
   `asyncio.to_thread`. `Run` is the sync facade.
4. **Credentials stay in the harness.** Events pass `redact_event` with the known secrets of the
   provider, so a key stays out of the log, the checkpoint and the callbacks.
5. **Stable identifiers.** Tool names, event types, and the checkpoint and event-log versions
   never change silently.

## API

`Engine(callbacks=None, hooks=None, permissions=None, sandbox=None, *, llm=None, store=None,
workspace=None)`. `llm`, `store` and `workspace` are keywords beyond the agreed signature, since a
run needs them. `llm` gets the retry layer, `store` defaults to `MemoryRunStore`, and `permissions`
to `Permissions(mode="ask")`.

- `await run(agent, context, *, max_steps=None, loop=None) -> RunResult`
- `await resume(checkpoint, request_id=None, answer=None, *, agent=None, loop=None) -> RunResult`
- `await Engine.replay(store, run_id) -> RunResult`
- `register_hook(hook)` returns a handle with `.remove()`; `hooks()` lists them.

## One step

`step.py`: one agent call (its completion logged), the decision and dispatch of its tool calls
(each result logged), then `step.finished`, `usage` and a checkpoint. A step is written over the
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
| `error` | `failed` | a provider failed, a tool was called wrongly too often, the output never fit, or any other exception |

Any `Exception` ends the run with `error`, with its class and message in an `error` event, because
a provider made by the backend raises its own errors and a client must see the run end. A dying
process is a `BaseException`, is not caught, and can be recovered.

## Context

`Context(run_id=None, messages=(), *, chat=None, project=None, steps_left=None)`.
`messages_for(agent)` renders a stable prefix (system prompt; tool schemas travel beside the
messages), then the history, then the dynamic part last, so prompt caching works. The dynamic part
is a system message with the steps left; S2 adds the problem state. It is never stored in the
history.

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


`Loop` has `async run(engine, task)`, `resume(engine, checkpoint, request_id, answer)`,
`state_dict()` and `load_state_dict(state)`. The state of a loop is saved in the `checkpoint` event
and the run checkpoint, so a pause inside a loop resumes at the same place in another process.
Loops are written as resumable steps, never with state held only in local variables.
`ToolLoop(agent, max_steps=None)` is one engine run of one agent.

## Recovery and resume

`recover(events, run_id=None)` folds a log through `apply`, and `catch_up(state, events)` applies
what came after a snapshot. A checkpoint (version 1, `checkpoint.py`) is that same state as JSON,
saved after every step, before a pause and at the end; a wrong version or shape raises
`CheckpointError`.

`Engine.resume(checkpoint, request_id, answer)` first catches up with the log. An unknown or already answered request raises `RequestError`, and a run that ended
raises `RunError`. Approval runs the stored call without asking again; denial becomes the tool
result; a reply to `ask_user` becomes its result. Without a request, it continues a run whose
process died: the recorded completion is reused, and a started tool without a result runs again
only when `idempotent`; otherwise it becomes an error result for the model. An accepted answer is
logged before the run ends, so a crash after it repeats no LLM call. A nested run left open by a
crash ends with `error`, and its usage goes to the parent. If the crash came after the answer of a
nested request reached the child, `resume()` continues the child, or takes its outcome when it
ended.

## Nested runs

`Delegate` runs an agent through `session.delegate` in a child session sharing the root's
`RunLog`: same store key, same sequence, its own `run_id`, `parent` set, its own checkpoint under
its own run id. A pause in the child logs `request` once; the parent logs a `permission` event with
decision `wait` and pauses on the same request id, and an answer to the parent passes down.

## Replay

`await Engine.replay(store, run_id)` (`replay.py`) reruns a stored run through
`FakeLLM.from_events`, without network and with permissive permissions, since the log holds the
outcome of the original decisions. `read` and `compute` tools run again; others reuse recorded
results, as do calls that were denied or answered. A paused run stops where its log ends, so it
never runs its pending tool. A different call, count or answer raises `ReplayError` naming the
first differing step.

## Stores and workspaces

`RunStore` is the nine-method protocol of the contract, `load_events` included. `MemoryRunStore`
and `FileRunStore(root=".runs")` add `add_message(chat_id, message)`.
`FileRunStore` writes `<root>/<run id>/events.jsonl`, `checkpoint.json` and `artifacts/`, and
`<root>/chats/<chat id>/history.jsonl` and `state.json`. Unsafe ids raise `RunError`.

`Workspace` has `plant(project_id)` and `documents(project_id, query)`. `MemoryWorkspace(plants,
documents)` holds values; `FileWorkspace(root)` reads `<root>/<project id>/plant.json`, loaded by
the class the file names, and text files in `documents/`, searched by keyword count. The S1
agents do not use it; the S2 tools will. `gd.testing.check_run_store` and `check_workspace` are the
conformance checks.

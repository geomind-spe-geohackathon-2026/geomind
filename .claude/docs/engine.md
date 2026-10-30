# Engine

The engine runs one agent until it stops, over an append-only event log. Loops decide which run
comes next. It is finite: it never sleeps or schedules itself. Code is in `swarmax/core/engine/`.

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
| `error` | `failed` | a provider failed, a tool was called wrongly too often, or the output never fit |

## Context

`Context(run_id=None, messages=(), *, chat=None, project=None, steps_left=None)`.
`messages_for(agent)` renders a stable prefix (system prompt; tool schemas travel beside the
messages), then the history, then the dynamic part last, so prompt caching works. The dynamic part
is a system message with the steps left; S2 adds the problem state. It is never stored in the
history.

## Callbacks

`Callback` has `on_run_start`, `on_step_start`, `on_llm_call`, `on_text`, `on_tool_start`,
`on_tool_end`, `on_permission`, `on_state_change`, `on_request`, `on_step_end`, `on_error` and
`on_run_end`, plain or `async`, each receiving the engine and one event. `on_event` is an addition:
it receives every event, because the public `usage` event has no method of its own and the backend
publisher needs one place to forward `event.is_public` events. Callbacks observe only: an exception
in one is an `error` event, reported to `on_error`, and never changes the run. `EventLog(path=None)`
writes JSON lines or keeps events in memory.

## Hooks, permissions, events, tools

See [hooks.md](hooks.md), [permissions.md](permissions.md), [events.md](events.md) and
[tools.md](tools.md).

## Loops

See `swarmax/loops/`.

# Context

What a model needs beyond its messages, in `geomind/context/`. Everything there is deterministic: an
LLM call or an event stays in the engine.

## Problem state

`ProblemState` (`context/state.py`) holds the notes of one chat, outside the message window: `version`,
`goal`, `requirements`, `assumptions`, `design`, `results`, `verification` and `questions`, with the
item shapes of [design section 3](../../../docs/geomind-design.md). It is frozen: a change is a new
state.

- **Writing.** The model writes through `update_state(changes)`. `apply_changes(state, changes)`
  takes the contract's JSON Patch operations, validates each one and returns a new state with
  `version + 1`, or raises `StateError` with what to fix. A patch applies whole or not at all.
- **The log is the source of truth.** `run.started` stores the state a run starts from, and each
  `state.changed` is applied by `apply` in `engine/recovery.py`, so `recover` rebuilds it. A replay
  reruns `update_state`.
- **Per chat.** `Run` loads the state with `store.load_state(chat)`, empty when `None`, and the engine
  saves it with `store.save_state(chat, state)` when a root run ends, as a JSON object. A paused run
  has not ended, so it saves nothing yet.
- **Nested runs share it.** All agents of a tree read and write one state. A change in a child also
  reaches the runs above it, and `recover` applies `state.changed` from the whole tree.
- **Shown to the model.** `render(state)` gives one line per item, the last part of every call, never
  in the message list. An untouched state (`version` 0) renders nothing.

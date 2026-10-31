# Context

What a model needs beyond its messages, in `geomind/context/`. Everything there is deterministic: an
LLM call or an event stays in the engine.

## Problem state

`ProblemState` (`context/state.py`) holds the notes of one chat, outside the message window: `version`,
`goal`, `requirements`, `assumptions`, `design`, `results`, `verification` and `questions`. It is
frozen: a change is a new state.

| Key | Shape |
|---|---|
| `goal` | text |
| `requirements` | `[{id, text, metric, target, tolerance, status}]`, testable; `status` starts `open` |
| `assumptions` | `[{id, text, value, source, confirmed}]`; `source` is `user`, `agent` or `default` |
| `design` | an object, free in shape |
| `results` | `[{id, summary, reference}]`; `reference` names the stored data |
| `verification` | an object, free in shape |
| `questions` | `[{id, text}]` |

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

## Long conversations

`history.py` turns messages into turns: a turn starts at a user message and holds everything up to the
next one, so a tool call never parts from its result.

`compaction.py` decides. Before an LLM call, when the rendered context passes `compaction_threshold`
(default 0.6) of the model's window, all turns but the last `compaction_keep_turns` (default 6) are
replaced by one summary message. The window comes from a small table per model, with a safe default,
and tokens are estimated at four characters each, so a replay gives the same answer. With nothing old
enough to replace, the run goes on: an open turn stays whole.

`engine/compaction.py` makes the one call to the `Summarizer` agent (cheap model, no tools, not
streamed) and logs an internal `compaction` event holding the completion. `apply` makes the
replacement, so a recovered run holds it and a replay gets the same summary from `FakeLLM.from_events`.
Hooks do not see this call, and its usage counts toward the run.

The problem state is outside the messages, so compaction never touches it. The summary goes the other
way: `apply` keeps it in `ProblemState.compaction` as `{summary, turns}`, saved with `save_state`,
because `load_history` always returns every message and the contract has no other per-chat storage.
`restore(history, compaction)` gives the next run the summary and the newer turns, so a chat compacts
once and not on every message. That key is outside the patchable document: a patch cannot reach it and
`render` does not show it.

## Skills

`prompts/skills/*.md` hold instructions a model loads on demand. The first paragraph of a file is its
one line. An agent that has the `read_skill` tool gets the list of names with one line each in its
system prompt; the rest costs nothing until it is read. `read_skill(name)` returns one skill, and an
unknown name is an error result with the close match. The skills are `gemini-units` and
`reading-results`.

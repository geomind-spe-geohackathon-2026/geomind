# Context

What a model needs beyond its messages, in `geomind/context/`. Everything there is deterministic: an
LLM call or an event stays in the engine.

## Problem state

`ProblemState` (`context/state.py`) holds the notes of one chat, outside the message window: `version`,
`goal`, `requirements`, `assumptions`, `design`, `results`, `verification`, `questions` and
`brief`. It is frozen: a change is a new state.

| Key | Shape |
|---|---|
| `goal` | text |
| `requirements` | `[{id, text, metric, target, tolerance, status}]`, testable; `status` starts `open` |
| `assumptions` | `[{id, text, value, source, confirmed}]`; `source` is `user`, `agent` or `default` |
| `design` | an object, free in shape; `reference` names the current `design/<name>` |
| `results` | `[{id, summary, reference}]`; `reference` names the stored data |
| `verification` | an object, free in shape; `result` names the `result/<id>` that verifies the design, which `Verified` checks again |
| `questions` | `[{id, text}]` |
| `brief` | a [`Brief`](#the-brief), or `null` when no brief is set |

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

## The brief

`Brief` (`context/brief.py`) is what a design must meet, as a brief states it. Every field is
optional, and `None` means "not given": a limit the brief does not give is not checked, and
verification lists it under `not_given`.

| Field | Shape |
|---|---|
| `source` | a preset name, `user` (values the user gave) or `agent` |
| `demand` | `{heating, cooling}`: a gemini profile name or a stored `profile/<name>` |
| `doublets` | `{min, max}`, whole numbers |
| `doublet_flow` | `{min, max}`, amounts |
| `max_brine_cooling`, `pump_efficiency` | an amount |
| `operating_days` | a whole number |
| `volume_balance` | true when produced and injected liquid volumes must be equal |
| `heating`, `cooling` | `{supply, return_temperature}`, amounts |
| `reservoir` | `{depth, thickness, gradient, surface_temperature, pressure, permeability, density, viscosity, gas_liquid_ratio, gas_composition}`; the composition is mole fractions |

An amount is what gemini takes: a text `"<number> <unit>"` or a Value `{value, unit}`. Nothing in
`context/` converts it; the tools use `gm.units`.

- **Presets.** `PRESETS` holds the named briefs, and is the only place their numbers live. The one
  preset is `hackathon_2027`, the GEMINI hackathon challenge requirements of 28 October 2026: the
  two gemini demand profiles, the reservoir and brine values, 1 to 3 doublets, 50 to 300 m3/h,
  40 K, 70 % pump efficiency, equal volumes, 330 operating days, supply 100 and 20 degC. It gives
  no return temperature: 60 and 25 degC are assumptions of a design. `preset(name)` returns one,
  and `with_changes(brief, changes)` merges the JSON of a partial brief into one.
- **Who sets it.** The Designer (or any agent) sets it with `set_brief(preset=None, changes=None)`,
  or with `update_state` on `/brief`. In a design run the designer sets it first: the preset when
  the request is the hackathon challenge, otherwise the values the request gives; it asks the user
  for a demand the request does not give, and never takes the hackathon's numbers for another
  brief. The `DesignLoop` driver checks after each designer round that the brief has a demand, and
  asks the user when it has not.
- **Who reads it.** `simulate` builds `gm.schedule`'s rules and takes the demand from it, and
  verification checks its limits. Without a brief both use the `hackathon_2027` preset, as before
  briefs were data, and say so in their output. `render` shows it to every agent.

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

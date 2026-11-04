# Context

What a model needs beyond its messages, in `geomind/context/`. Everything there is deterministic: an
LLM call or an event stays in the engine.

## Problem state

The `design` section is typed by `DesignState` (`context/state.py`; `ProblemState.design_state`):
`reference`, `result` and `start_result` are reference strings (`design/<name>`, `result/<id>`; the
pattern is advertised, not enforced) and `alternatives` is a list of `{family, design, result, verdict, reason}` (the last two since 0.4.6);
other keys are free. `update_state` refuses an object where a reference belongs. A stored 0.4.x state
with one loads: an object carrying a `reference` is converted, any other is kept under
`design.unreadable`.

`ProblemState` (`context/state.py`) holds the notes of one chat, outside the message window: `version`,
`goal`, `requirements`, `assumptions`, `design`, `results`, `verification`, `questions`, `case`
and `case_origin`. It is frozen: a change is a new state.

| Key | Shape |
|---|---|
| `goal` | text |
| `requirements` | `[{id, text, case_requirement, status}]`: the user's words; `case_requirement` is the `name` of the case requirement that gemini judges, or null; `status` starts `open` |
| `assumptions` | `[{id, text, value, source, confirmed, reason, citation}]`; `source` is `user`, `agent` or `default`; `reason` and `citation` (a published source's details) are optional |
| `design` | an object, free in shape; `reference` names the current `design/<name>`, `result` its whole-year run, `start_result` the sized start's run and `alternatives` the other families simulated, `[{family, design, result}]` |
| `results` | `[{id, summary, reference}]`; `reference` names the stored data |
| `verification` | an object, free in shape; `result` names the `result/<id>` that verifies the design, which `Verified` checks again |
| `questions` | `[{id, text}]` |
| `case` | a [gemini case](#the-case) as the dict of a `case.json`, or `null` when no case is set; it replaced the former `brief` |
| `case_origin` | `{case, files}`: the case the user or the project gave, its files as `{name: sha256}`, or `null`; see [the case](#the-case) |

- **Writing.** The model writes through `update_state(changes)`, except `case` and `case_origin`,
  which only the case tools write (`update_state` refuses them with `not_allowed`). `apply_changes(state, changes)`
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

## The case

The problem is a gemini `gm.Case` (a `case.json`, its series CSV files and its `economics.json`;
sections `time`, `site`, `demand`, `utilities`, `economics`, `requirements` and optionally
`initial_state`). The state holds it as plain JSON in `case`, header included (`format`, `kind`,
`name`), and `context/` knows nothing of its content; `render` shows only the time, the section
names and the files of the demand series.

- **Stored as given.** `case` is the content of a `case.json` plus the merge-patch changes of the
  user and the model, validated by `gm.Case.from_dict` and `Case.check`. It is never
  `case.to_dict()`; the stored case is what the user gave. A test keeps that the stored case of
  `shallow_district` gives its heating peak of 3.034 MW.
- **The files.** The files a case names (the `file` of each series, such as `data/demand.csv`, and
  its `economics` file) are not in the state. Their names are relative paths: nothing absolute, no
  `..` (`geomind/stores/casefiles.py`). The run store keeps them as chat artifacts `case/<file name>`
  (bytes; `save_chat_artifact`, so every run of the chat reads them), so the run store is the source of truth and a run does not read a project folder.
  `case_of(context)` in `tools/gemini/case.py` returns
  `gm.Case.from_dict(state.case, files={name: bytes})`; there is no temporary folder. With no case
  it raises `ToolError` telling the model to call `set_case` or `ask_user`: there is no fallback
  case anywhere.
- **Who sets it.** `set_case(source=None, changes=None, requirements=None, economics=None)`:
  `source="project"` loads the project's case through `Workspace.case(project)` and copies its
  files into the run; `changes` is an RFC 7386 JSON merge patch on the case, except
  `requirements` and `economics`, which `changes` refuses; `requirements` is
  `{name: requirement | null}` (add or replace by name, remove with null, the others stay);
  `economics` is a merge patch on the content of the economics file, stored as a new content file.
  gemini validates the result with `Case.from_dict` and `Case.check()`; a rejected case comes back
  as a tool error with gemini's `path`, `code` and message, and nothing is stored. `save_profile`
  writes a user's demand values to `data/<name>.csv` (a `time` column and the values), points the
  service's `power` at it and, when the profile does not cover the case's `time`, sets the time to
  the profile's span in the same call. `update_state` cannot write the case.
- **The case the user gave.** `case_origin` is the project's case (`source="project"`, without the
  changes of the same call) or the first case of the chat, which comes from the user's request or
  answer. Later changes leave it as it is; each file is kept by its content as `<sha256>.file`.
  `case_changes` (`origin.py`) lists every difference of `case` from it: a section key, a
  requirement by name (`requirements.<name>`), and every file whose content changed
  (`file <name>`), the economics file included: a change of the economics is a change of the
  case. `verify_design` fails a design with `case_changed` while any difference is left, so no
  agent passes by weakening the case. The design loop then asks the user: `approve` runs
  `accept_case` (only the driver holds it), which makes the current case the origin; `restore`
  sends the design lead back to `set_case(source="origin")`.
- **Who reads it.** `read_case(section=None)` returns the case, a section, `economics` (the
  parsed content of the economics file) or `schema` (`gm.Case.schema()` with
  `gm.case.Economics.schema()` under `economics_schema`). The gemini tools read the case through
  `case_of`.

## Long conversations

`history.py` turns messages into turns: a turn starts at a user message and holds everything up to the
next one, so a tool call never parts from its result.

`compaction.py` decides. Before an LLM call, when the agent's context passes `compaction_threshold`
(0.6) of the model's window (`context_window`, below), all turns but the last
`compaction_keep_turns` (6) are replaced by one summary message. The agent's context is the larger
of its own rendered messages, estimated at four characters a token, and the input tokens the
provider counted for its own last call (`RunState.last_input_tokens`, which holds the tool schemas
the estimate lacks; a compaction clears it). Both come from the log, so a replay gives the same
answer. With nothing old enough to replace, the run goes on: an open turn stays whole.

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

## Old results in the history

`Context._history()` renders the messages. A tool result stored by reference (see
[tools.md](tools.md#dispatch)) is whole in the step after its call; once a later assistant message
exists, its message is `stored_form` (kept in `RunState.stored`, built by `apply` from the
`tool.result` event, so a replay or a recovery gives the same text). A call input over 800
characters in an older assistant message becomes an empty input, and its outline a line of the
message's text, `[<tool> was called with long arguments, left out of this history: <outline>. They
are no input to send again.]`, so nothing call-shaped is left to copy (a copied
`{"shortened": ...}` of older logs is refused, naming the real arguments). A message changes once, so
the prefix before it stays the same for the provider's cache, and the dynamic part stays last. The
log and the store keep everything; compaction sees the shortened text. An event without a reference
(0.4.x, or a short result) is never shortened.

## Skills

`prompts/skills/*.md` hold instructions a model loads on demand. The first paragraph of a file is its
one line. An agent that has the `read_skill` tool gets the list of names with one line each in its
system prompt; the rest costs nothing until it is read. `read_skill(name)` returns one skill, and an
unknown name is an error result with the close match. The skills are `gemini-units` and
`reading-results`.

## Context window

`context_window(model)` in `geomind/context/compaction.py` returns the window in tokens: the setting
`context_window` (`GEOMIND_CONTEXT_WINDOW`) if set, else `context_length` from OpenRouter's public
model list. `load_windows` reads the list once per process, in a worker thread, when a run on a real
provider starts (and before a call, for a resumed run); when the list cannot be read or lacks a
model it raises `RunError` naming `GEOMIND_CONTEXT_WINDOW`. There is no table and no guess (before
0.4.2 an unknown model got 128 000). A fake or scripted run never fetches and is never over the
threshold unless the setting gives a window. `GEOMIND_CONTEXT_WINDOW` overrides the list for every
model, so a live run should leave it unset or give the real window: a smaller value compacts early.

## Per agent or per run tree

A run tree is a root run and its nested runs (delegates), on one log. Each limit counts one of two
things, and the two never mix (Sahand, 2026-11-04):

- **Context, per agent call.** Compaction, the window bound of a call's `max_tokens` (the window
  less the input bound of the call's own messages and tools) and `context_exceeded` (the
  provider's 400 for that one call) read only the calling agent's own conversation. A nested run
  starts with its task only and compacts on its own context; a parent never compacts or is
  refused for what its children used.
- **Steps, per agent run.** Each run, nested ones included, counts its own steps from 1:
  `max_steps` (`GEOMIND_MAX_STEPS`) for a run, or the delegate's own setting (`engineer_max_steps`)
  for an engineer. A parent's steps are never spent by its children.
- **Budgets, per run tree.** `TokenBudget(max_tokens)`, `CostBudget(max_cost)`, `ProjectBudget`
  and `TimeLimit` are spending caps over the whole tree (`RunSession.total_usage`: the run, the
  runs above it, its siblings and the calls in flight), set by their caller with no default; a
  hook not given is off. A token budget is a cost budget in tokens, never a context window.

`usage` totals are cumulative: `RunState.usage`, `step_usage`, `RunResult.usage`, the `usage`
event and a delegate's `tool.result.usage` (`take_child_usage`) include what nested runs spent.
They are for budgets and reports; no context decision reads them. Per call figures are in
`llm.completed.completion.usage`.

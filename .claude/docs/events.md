# Events

Every event of a run, in `geomind/types/events.py`. An event has `run_id`, `sequence`, `time`,
`agent` (the dotted agent path), `parent` (the parent run id of a nested run, or `null`), a stable
`type`, `is_public` and `data()`. Event log version: 1. Types never change silently: a change is a
new version, recorded here.

The engine saves every event with `store.save_event` and hands it to callbacks, except
`text.delta`, which goes to callbacks only: `llm.completed` and `step.finished` hold the full text,
so recovery and replay never need the pieces. Nested runs
save under the root run id, with their own `run_id` and one shared `sequence`, so a root log holds
the whole tree. `event.to_dict()` holds every field and `event_from_dict` rebuilds the event;
`event.data()` is what a client sees.

## Public events

`data()` is exactly the JSON of [contracts.md](../../../docs/contracts.md) section 2, always with
`agent` and `parent`. An optional key whose value is `null` is left out. A test pins each one.

| Type | Class | `data()` |
|---|---|---|
| `run.started` | `RunStarted` | `{run, loop}` |
| `step.started` | `StepStarted` | `{index, model}` |
| `text.delta` | `TextDelta` | `{index, text}` |
| `tool.started` | `ToolStarted` | `{index, call_id, tool, input}` |
| `tool.finished` | `ToolFinished` | `{index, call_id, output_summary, duration, error?}` |
| `step.finished` | `StepFinished` | `{index, usage, text}`; `text` is the step's full assistant text, `""` if none |
| `state.changed` | `StateChanged` | `{version, changes}` |
| `study.recorded` | `StudyRecorded` | `{run, index, call_id, study, tool, method, designs, best?}` |
| `request` | `RequestMade` | `{request, call_id?, kind, message, options?}` |
| `usage` | `UsageUpdated` | `{input_tokens, output_tokens, cost}`, running totals |
| `run.finished` | `RunFinished` | `{status, stop_reason, message?}` |

`study.recorded` is sent once by a study tool, after its artifact `study/<name>` and `studies.index`
are saved (see [Stored studies](tools.md#stored-studies)); it is public but not one of the ten
events of the shared contract. `run` is the run that called the tool, `index` its step, `call_id`
the call (`null` outside a call), `study` the key `study/<name>`, `tool` the study tool, `method`
the gemini study method (`run`, `minimize`, `sample`, `sensitivity`), `designs` the names of the
plants it ran over (the `designs.read` references without `design/`) and `best` the reference of
the design it recommends; like every optional key it is left out of `data()` when `null`.
Callbacks get it as `on_study_recorded`. A log of 0.3.1 or older has none.

**Unknown types.** A log written by a newer version may hold event types this one lacks. Every
reader of a log ignores them: `events_from_dicts` skips a `type` that is not in `EVENT_CLASSES`,
`FileRunStore.load_events` uses it, and the same rule binds the backend's store and stream.
`event_from_dict` still raises `RunError` for an unknown type, as a direct call asks for one.

`run.started` also stores, not streamed, `versions`: `{geomind, gemini, python}` of the process that
began the run, on every run, nested ones included; `gemini` is left out when it cannot be imported.
A log of 0.3.0 has none (`{}`); the export then reads `run_manifest.json`. `model` is the
provider model id the step calls. A run stored by S1 has none, and its JSON leaves
the key out. `options` is `[{value, label}]`, for a question with fixed choices, and is absent for
free text and for approvals.

`version` of `state.changed` is the state version after the change, starting at 1. `changes` is a
list of JSON Patch operations, validated by `geomind/types/patch.py`: `op` is `add`, `replace` or
`remove`, `path` is a JSON Pointer under a top-level key of the problem state, lists of items with
an `id` are addressed by id, and `-` ends the path of an `add` that appends an item with an `id`.

`StepFinished` also stores `loop_state`, the state of the loop.

`RunStarted` also stores what rebuilds the run: `root`, `agent_class`, `max_steps`, `chat`,
`project`, `parent_step`, `messages`, `problem`, `settings` and `loop_state`. `RequestMade` also stores the
pending action: `point` (`tool`, `llm` or `finish`) and `call`. `RunFinished` also stores `answer`.

## Internal events

Stored and used by recovery, replay and the log; never streamed. `data()` holds all their fields.

| Type | Class | Fields |
|---|---|---|
| `llm.completed` | `LLMCompleted` | `index`, `completion`, `messages`, `duration` |
| `compaction` | `Compacted` | `index`, `completion` (its `text` is the summary), `messages`, `duration`, `turns` |
| `tool.result` | `ToolRecorded` | `index`, `call_id`, `tool`, `input`, `output`, `is_error`, `is_validation`, `is_finish`, `duration`, `source`, `reference`, `feedback`, `usage` |
| `permission` | `PermissionDecided` | `index`, `decision`, `rule`, `point`, `call_id`, `tool`, `reason`, `input`, `request`, `child`, `call` |
| `retry` | `Retried` | `attempt`, `model`, `error`, `delay` |
| `sandbox.provisioned` | `SandboxProvisioned` | `provider` |
| `sandbox.closed` | `SandboxClosed` | `is_lost` |
| `error` | `ErrorRaised` | `error_class`, `message`, `where` |

`tool.result` with `call_id` `null` is feedback to the model about its final answer, shown as a
user message: `feedback` is `output` (failed validation) or `finish` (refused by a hook). With
`is_finish` it is the accepted answer instead, and `call_id` tells a `finish` call from a plain
answer. Its `source` is `tool`, `denied`, `answer` or `interrupted`. A `permission` decision is `allow`, `deny`,
`ask`, `answer` (a user settled a request) or `wait` (a nested run paused, and this run waits on the
same request).

`error` is saved like every event, and `on_error` callbacks receive it.

Text is redacted as one stream: the last characters of `text.delta` wait for the next piece, as
many as a known secret could still need. Without known secrets nothing waits. Artifacts pass the
same redaction as events.

## Run log

`gd.runlog(events)` builds the contract `runlog` object from the events of a root run, nested
runs included. A step's `parent` is the step of the parent run that delegated it, while an event's
`parent` is the parent run id; both are as the contract defines them.

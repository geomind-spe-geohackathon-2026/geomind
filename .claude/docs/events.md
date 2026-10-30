# Events

Every event of a run, in `swarmax/types/events.py`. An event has `run_id`, `sequence`, `time`,
`agent` (the dotted agent path), `parent` (the parent run id of a nested run, or `null`), a stable
`type`, `is_public` and `data()`. Event log version: 1. Types never change silently: a change is a
new version, recorded here.

The engine saves **every** event with `store.save_event` and hands it to callbacks. Nested runs
save under the root run id, with their own `run_id` and one shared `sequence`, so a root log holds
the whole tree. `event.to_dict()` holds every field and `event_from_dict` rebuilds the event;
`event.data()` is what a client sees.

## Public events

`data()` is exactly the JSON of [contracts.md](../../../docs/contracts.md) section 2, always with
`agent` and `parent`. An optional key whose value is `null` is left out. A test pins each one.

| Type | Class | `data()` |
|---|---|---|
| `run.started` | `RunStarted` | `{run, loop}` |
| `step.started` | `StepStarted` | `{index}` |
| `text.delta` | `TextDelta` | `{index, text}` |
| `tool.started` | `ToolStarted` | `{index, call_id, tool, input}` |
| `tool.finished` | `ToolFinished` | `{index, call_id, output_summary, duration, error?}` |
| `step.finished` | `StepFinished` | `{index, usage}` |
| `state.changed` | `StateChanged` | `{changes}`; emitted from S2 |
| `request` | `RequestMade` | `{request, call_id?, kind, message, options?}` |
| `usage` | `UsageUpdated` | `{input_tokens, output_tokens, cost}`, running totals |
| `run.finished` | `RunFinished` | `{status, stop_reason, message?}` |

`RunStarted` also stores what rebuilds the run: `root`, `agent_class`, `max_steps`, `chat`,
`project`, `parent_step`, `messages`, `settings` and `loop_state`. `RequestMade` also stores the
pending action: `point` (`tool`, `llm` or `finish`) and `call`. `RunFinished` also stores `answer`.

## Internal events

Stored and used by recovery, replay and the log; never streamed. `data()` holds all their fields.

| Type | Class | Fields |
|---|---|---|
| `llm.completed` | `LLMCompleted` | `index`, `completion`, `messages`, `duration` |
| `tool.result` | `ToolRecorded` | `index`, `call_id`, `tool`, `input`, `output`, `is_error`, `is_validation`, `is_finish`, `duration`, `source`, `reference`, `feedback`, `usage` |
| `permission` | `PermissionDecided` | `index`, `decision`, `rule`, `point`, `call_id`, `tool`, `reason`, `input`, `request`, `child`, `call` |
| `retry` | `Retried` | `attempt`, `model`, `error`, `delay` |
| `sandbox.provisioned` | `SandboxProvisioned` | `provider` |
| `sandbox.closed` | `SandboxClosed` | `is_lost` |
| `checkpoint` | `CheckpointSaved` | `index`, `loop_state` |
| `error` | `ErrorRaised` | `error_class`, `message`, `where` |

`tool.result` with `call_id` `null` is feedback to the model about its final answer, shown as a
user message: `feedback` is `output` (failed validation) or `finish` (refused by a hook). With
`is_finish` it is the accepted answer instead, and `call_id` tells a `finish` call from a plain
answer. Its `source` is `tool`, `denied`, `answer` or `interrupted`. A `permission` decision is `allow`, `deny`,
`ask`, `answer` (a user settled a request) or `wait` (a nested run paused, and this run waits on the
same request).

`error` is an addition to the internal list of the contract: `on_error` callbacks need an event
object, and a survived error belongs in the log. See
[contracts.md](contracts.md#proposed-changes).

Text is redacted as one stream: the last characters of `text.delta` wait for the next piece, as
many as a known secret could still need. Without known secrets nothing waits. Artifacts pass the
same redaction as events.

## Run log

`sx.runlog(events)` builds the contract `runlog` object from the events of a root run, nested
runs included. A step's `parent` is the step of the parent run that delegated it, while an event's
`parent` is the parent run id; both are as the contract defines them.

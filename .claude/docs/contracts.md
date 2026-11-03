# Contracts

How geomind implements the backend contract: [contracts.md](../../../docs/contracts.md), file
version 15, sections 2 and 3, interface version 2.5. A change to the contract is a change to that
file first, announced to all repositories. `tests/unit/test_contract_map.py` checks that every code
path below exists.

## Section 2: live run events

| Contract item | Code | Test |
|---|---|---|
| The ten public event types and their JSON | `geomind/types/events.py` | `tests/unit/types/test_events.py` |
| `event.type`, `event.data()`, `event.is_public` | `geomind/types/events.py` | `tests/unit/types/test_events.py` |
| `agent` and `parent` on every `data` | `geomind/types/events.py` | `tests/integration/test_delegate.py` |
| `id: <sequence>`, one number per root run | `geomind/engine/log.py` | `tests/unit/engine/test_log.py` |
| The internal events, `error` included | `geomind/types/events.py` | `tests/unit/types/test_events.py` |
| `model` on `step.started` | `geomind/engine/step.py` | `tests/unit/engine/test_engine.py` |
| `options` as `[{value, label}]` | `geomind/types/decisions.py` | `tests/unit/types/test_decisions.py` |
| `ask_user` normalises `options` | `geomind/tools/builtins.py` | `tests/unit/tools/test_builtins.py` |
| Answers to options | `geomind/types/decisions.py` | `tests/unit/types/test_decisions.py` |
| `study.recorded` as `{run, index, call_id, study, tool, method, designs, best?}` (beyond the shared contract) | `geomind/types/events.py` | `tests/unit/types/test_events.py` |
| `state.changed` as `{version, changes}` | `geomind/types/events.py` | `tests/unit/types/test_events.py` |
| The JSON Patch subset | `geomind/types/patch.py` | `tests/unit/types/test_patch.py` |
| Patches applied, addressed by id, `version` + 1 | `geomind/context/state.py` | `tests/unit/context/test_state.py` |
| `step.finished.text`, `text.delta` not stored | `geomind/engine/session.py` | `tests/unit/engine/test_log.py` |
| `state.changed` emitted by `update_state` | `geomind/engine/session.py` | `tests/integration/test_problem_state.py` |
| `Callback.on_event`, the one method of a publisher | `geomind/engine/callbacks.py` | `tests/unit/engine/test_callbacks.py` |
| Every event but `text.delta` through `RunStore.save_event` | `geomind/engine/session.py` | `tests/unit/engine/test_log.py` |
| Public events reach a publisher | `geomind/engine/callbacks.py` | `tests/integration/test_delegate.py` |

**Every consumer ignores unknown event types.** A newer geomind adds event types (0.4.0:
`study.recorded`), so a publisher, a stream client, a store reader or any code that reads a log
skips a `type` it does not know instead of failing. `event_from_dict` itself still raises
`RunError` on an unknown type, because a caller that asks for one expects a known event;
`events_from_dicts` (`geomind/types/events.py`) is the reader of a stored log and skips them, and
`FileRunStore.load_events` uses it. The backend's own `RunStore.load_events` and its stream must
do the same.

Events that S1 stored have no `model` on `step.started`; that key is left out of their JSON. A backend publisher overrides
`Callback.on_event` and forwards `event.type` and `event.data()` when `event.is_public`.
`examples/backend/general/01_queue_and_resume.py` shows it. To store an event use `event.to_dict()`,
and to read one back `event_from_dict`.

## Section 3: geomind interfaces

| Contract item | Code | Test |
|---|---|---|
| `LLM` | `geomind/providers/base.py` | `tests/unit/providers/test_base.py` |
| Tool error codes `no_case` and `case_incomplete` (beyond the shared contract) | `geomind/tools/gemini/case.py` | `tests/unit/tools/gemini/test_case.py` |
| Optional `Workspace.files(project_id) -> [{name, size, media_type}]`, `Workspace.file(project_id, name) -> bytes \| None` (beyond the shared contract) | `geomind/stores/workspace.py` | `tests/unit/stores/test_workspace.py` |
| Tool error codes `files_unavailable`, `not_text` (beyond the shared contract) | `geomind/tools/files.py` | `tests/unit/tools/test_files.py` |
| `Completion`, `Usage`, `Message` | `geomind/types/messages.py` | `tests/unit/types/test_messages.py` |
| `RunStore`, all seven methods, `load_events` included | `geomind/stores/run.py` | `tests/unit/testing/test_conformance.py` |
| `Workspace` | `geomind/stores/workspace.py` | `tests/unit/testing/test_conformance.py` |
| `SandboxProvider`, `Sandbox` | `geomind/sandbox/base.py` | `tests/unit/sandbox/test_base.py` |
| `gd.sandbox.LocalSandbox` | `geomind/sandbox/local.py` | `tests/unit/sandbox/test_local.py` |
| `gd.sandbox.DockerSandbox` | `geomind/sandbox/docker.py` | `tests/unit/sandbox/test_docker.py` |
| `gd.providers.OpenRouter` | `geomind/providers/openrouter.py` | `tests/unit/providers/test_openrouter.py` |
| `gd.providers.FakeLLM` | `geomind/providers/fake.py` | `tests/unit/providers/test_fake.py` |
| Memory and file stores | `geomind/stores/run.py` | `tests/unit/stores/test_run.py` |
| `UsageLedger`, memory and file usage ledgers | `geomind/stores/usage.py` | `tests/unit/stores/test_usage.py` |
| Memory and file workspaces | `geomind/stores/workspace.py` | `tests/unit/stores/test_workspace.py` |
| Internal `compaction` event | `geomind/types/events.py` | `tests/unit/engine/test_compaction.py` |
| Everything in this section, name by name | `tests/unit/snapshots/api.json` | `tests/unit/test_contract_map.py` |
| The schemas and samples of the exchanged documents | `geomind/schemas/` | `tests/unit/test_frozen_api.py` |
| `gd.Run`, `start`, `astart`, `load`, `resume`, `aresume`, `cancel` | `geomind/run.py` | `tests/unit/test_run.py` |
| `gd.Permissions` | `geomind/engine/permissions.py` | `tests/unit/engine/test_permissions.py` |
| `gd.hooks.TokenBudget`, `ProjectBudget`, `RequireApproval`, `Cancellation` | `geomind/engine/hooks.py` | `tests/unit/engine/test_hooks.py`, `tests/unit/engine/test_partial.py` |
| `RunResult` and the statuses | `geomind/types/results.py` | `tests/unit/types/test_results.py` |
| The shapes of `answer` | `geomind/types/decisions.py` | `tests/unit/types/test_decisions.py` |
| `resume()` of a dead run | `geomind/engine/recovery.py` | `tests/integration/test_recovery.py` |
| Resume in another process | `geomind/run.py` | `tests/e2e/test_process_restart.py` |
| `load_state` at start, `save_state` at the end | `geomind/run.py` | `tests/integration/test_problem_state.py` |

## Section 1: the parts geomind builds

| Contract item | Code | Test |
|---|---|---|
| `runlog` through `gd.runlog(events)` | `geomind/types/runlog.py` | `tests/unit/types/test_runlog.py` |
| `tool_call.error` is `true`, the Problem is in `tool_call.output` | `geomind/types/runlog.py` | `tests/unit/test_frozen_api.py` |

## For the backend

- Run `gd.testing.check_run_store(factory, seed_history)` and
  `gd.testing.check_workspace(factory, project=..., query=...)` against your implementations.
- `load_history` is read-only in the contract, so `check_run_store` takes `seed_history(store,
  chat_id, messages)` to fill a chat.
- `gd.Run` gets no `queued` status: that one is the backend's, before `start`.
- Pass `sandbox` and `permissions` again to `Run.load`, like hooks and callbacks; a run does not
  store them.
- `event.to_dict()` holds every field a store must keep, and `event_from_dict` restores it.
- **Chat artifacts (an addition).** `save_chat_artifact(chat_id, key, data)` and
  `load_chat_artifact(chat_id, key)` keep the artifacts the problem state can name in the chat's
  space, so a second message of a chat reads the case files, designs and results of the first.
  Same keys, same safe-key rules, same types (bytes or a JSON value, `None` when missing) as the
  run's. A chat's space and a run's are separate (`check_run_store` tests it). `FileRunStore`
  writes `<root>/chats/<chat id>/artifacts/...`. Geomind saves every artifact below in the chat's
  space; the run's methods remain for what is per run. A run without a chat uses its root run id
  as its chat id.
- Artifact keys (the rule applies to both spaces) may hold a `/`: `design/<name>`, `study/<name>`, `result/<id>` and `case/<file name>`
  (bytes: the series and economics files of the run's case; the file name is a relative path such
  as `data/demand.csv`, each part safe). A user's demand profile is a file of the case,
  `case/<file name>`. `check_run_store` tests them. A run also keeps keys
  without a `/`: `<id>.results`, `<id>.plant`, `<id>.case`, `<id>.files` and `<sha256>.file`
  (bytes: a case file by its content, which an older run reads).
- `Workspace.files(project_id)` and `Workspace.file(project_id, name)` are optional, and a backend
  adds both or neither. `files` returns `[{"name": str, "size": int, "media_type": str}]`, one row per
  file the user attached, `[]` without any: `name` is what the agent passes back, `size` is in bytes
  and `media_type` a MIME type. `file` returns the file's `bytes`, or `None` for any other name. Both
  are sync, called from a worker thread. Without them `list_files`, `read_document` and
  `set_case(files=...)` answer `files_unavailable` and the rest of a run is unchanged.
- `Workspace.case(project_id)` returns the project's case as `(case dict, {name: bytes})` or
  `None`: the content of its `case.json` as written, and the bytes of every file it names,
  `economics.json` and the series (`data/demand.csv`), by their relative path. `check_workspace`
  checks that every named file is there and every name is a safe relative path. The file workspace
  reads gemini's project folder `<root>/<project>/` (`case.json`, `economics.json`, `data/`,
  `plants/`, `documents/`); the memory one takes `cases={project: (dict, files)}`.
  `Workspace.plants(project_id)` returns `{name: plant file dict}`, one entry per `plants/*.json`
  (the name is the file stem, the dict the file as written, `kind: plant`), and `{}` without
  plants; the memory one takes `plants={project: {name: dict}}`. There is no single-plant method:
  `read_plant` picks the file by name, or the only one (`gm.Plant.from_dict` builds it per call).
  `check_workspace` checks the shape and `{}` for an unknown project.
- **What the backend stores for a project.** Its `case.json` (the case as written, read by
  `Workspace.case`), its `economics.json`, the series files they name and its plant files. The problem state holds the case under the key
  `case` (it replaced `brief`), and a run copies the files into its own `case/<file name>`
  artifacts. Nothing else of the case needs storing.
- **Tool errors.** A gemini `ValidationError` passes through with its `path`, `code` and message
  (`missing_value`, `invalid_design`, `unknown_name`...). A gap in gemini is a `ToolError` with
  code `not_implemented`; a missing case is `no_case` telling the model to call `set_case` or
  `ask_user`, and a case missing values is `case_incomplete`. See [tools.md](tools.md#error-results).
- `RunResult.stop_reason` may be `not_implemented`, with `status="failed"`.

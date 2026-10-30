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
| `state.changed` as `{version, changes}` | `geomind/types/events.py` | `tests/unit/types/test_events.py` |
| The JSON Patch subset | `geomind/types/patch.py` | `tests/unit/types/test_patch.py` |
| `Callback.on_event`, the one method of a publisher | `geomind/engine/callbacks.py` | `tests/unit/engine/test_callbacks.py` |
| Every event but `text.delta` through `RunStore.save_event` | `geomind/engine/session.py` | `tests/unit/engine/test_log.py` |
| Public events reach a publisher | `geomind/engine/callbacks.py` | `tests/integration/test_delegate.py` |

`state.changed` exists with its JSON and validation, and is emitted from S2. Events that S1 stored
have no `model` on `step.started`; that key is left out of their JSON. A backend publisher overrides
`Callback.on_event` and forwards `event.type` and `event.data()` when `event.is_public`.
`examples/backend/general/01_queue_and_resume.py` shows it. To store an event use `event.to_dict()`,
and to read one back `event_from_dict`.

## Section 3: geomind interfaces

| Contract item | Code | Test |
|---|---|---|
| `LLM` | `geomind/providers/base.py` | `tests/unit/providers/test_base.py` |
| `Completion`, `Usage`, `Message` | `geomind/types/messages.py` | `tests/unit/types/test_messages.py` |
| `RunStore`, all seven methods, `load_events` included | `geomind/stores/run.py` | `tests/unit/testing/test_conformance.py` |
| `Workspace` | `geomind/stores/workspace.py` | `tests/unit/testing/test_conformance.py` |
| `SandboxProvider`, `Sandbox` | `geomind/sandbox/base.py` | `tests/unit/sandbox/test_base.py` |
| `gd.sandbox.LocalSandbox` | `geomind/sandbox/local.py` | `tests/unit/sandbox/test_local.py` |
| `gd.sandbox.DockerSandbox` | `geomind/sandbox/docker.py` | `tests/unit/sandbox/test_docker.py` |
| `gd.providers.OpenRouter` | `geomind/providers/openrouter.py` | `tests/unit/providers/test_openrouter.py` |
| `gd.providers.FakeLLM` | `geomind/providers/fake.py` | `tests/unit/providers/test_fake.py` |
| Memory and file stores | `geomind/stores/run.py` | `tests/unit/stores/test_run.py` |
| Memory and file workspaces | `geomind/stores/workspace.py` | `tests/unit/stores/test_workspace.py` |
| `gd.Run`, `start`, `astart`, `load`, `resume`, `aresume`, `cancel` | `geomind/run.py` | `tests/unit/test_run.py` |
| `gd.Permissions` | `geomind/engine/permissions.py` | `tests/unit/engine/test_permissions.py` |
| `gd.hooks.TokenBudget`, `RequireApproval`, `Cancellation` | `geomind/engine/hooks.py` | `tests/unit/engine/test_hooks.py` |
| `RunResult` and the statuses | `geomind/types/results.py` | `tests/unit/types/test_results.py` |
| The shapes of `answer` | `geomind/types/decisions.py` | `tests/unit/types/test_decisions.py` |
| `resume()` of a dead run | `geomind/engine/recovery.py` | `tests/integration/test_recovery.py` |
| Resume in another process | `geomind/run.py` | `tests/e2e/test_process_restart.py` |

## Section 1: the parts geomind builds

| Contract item | Code | Test |
|---|---|---|
| `runlog` through `gd.runlog(events)` | `geomind/types/runlog.py` | `tests/unit/types/test_runlog.py` |

## For the backend

- Run `gd.testing.check_run_store(factory, seed_history)` and
  `gd.testing.check_workspace(factory, project=..., query=...)` against your implementations.
- `load_history` is read-only in the contract, so `check_run_store` takes `seed_history(store,
  chat_id, messages)` to fill a chat.
- `gd.Run` gets no `queued` status: that one is the backend's, before `start`.
- Pass `sandbox` and `permissions` again to `Run.load`, like hooks and callbacks; a run does not
  store them.
- `event.to_dict()` holds every field a store must keep, and `event_from_dict` restores it.

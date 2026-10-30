# Contracts

How geomind implements the backend contract: [contracts.md](../../../docs/contracts.md), version 2,
sections 2 and 3. A change to the contract is a change to that file first, announced to all
repositories. `tests/unit/test_contract_map.py` checks that every code path below exists.

## Section 2: live run events

| Contract item | Code | Test |
|---|---|---|
| The ten public event types and their JSON | `geomind/types/events.py` | `tests/unit/types/test_events.py` |
| `event.type`, `event.data()`, `event.is_public` | `geomind/types/events.py` | `tests/unit/types/test_events.py` |
| `agent` and `parent` on every `data` | `geomind/types/events.py` | `tests/integration/test_delegate.py` |
| `id: <sequence>`, one number per root run | `geomind/engine/log.py` | `tests/unit/engine/test_log.py` |
| The internal events | `geomind/types/events.py` | `tests/unit/types/test_events.py` |
| Every event through `RunStore.save_event` | `geomind/engine/session.py` | `tests/unit/engine/test_log.py` |
| Public events reach a publisher | `geomind/engine/callbacks.py` | `tests/integration/test_delegate.py` |

`state.changed` exists with its JSON and is emitted from S2. A backend publisher overrides
`Callback.on_event` and forwards `event.type` and `event.data()` when `event.is_public`.
`examples/backend/general/01_queue_and_resume.py` shows it. To store an event use `event.to_dict()`,
and to read one back `event_from_dict`.

## Section 3: geomind interfaces

| Contract item | Code | Test |
|---|---|---|
| `LLM` | `geomind/providers/base.py` | `tests/unit/providers/test_base.py` |
| `Completion`, `Usage`, `Message` | `geomind/types/messages.py` | `tests/unit/types/test_messages.py` |
| `RunStore`, all eight methods | `geomind/engine/store.py` | `tests/unit/testing/test_conformance.py` |
| `Workspace` | `geomind/engine/workspace.py` | `tests/unit/testing/test_conformance.py` |
| `SandboxProvider`, `Sandbox` | `geomind/sandbox/base.py` | `tests/unit/sandbox/test_base.py` |
| `gd.sandbox.LocalSandbox` | `geomind/sandbox/local.py` | `tests/unit/sandbox/test_local.py` |
| `gd.sandbox.DockerSandbox` | `geomind/sandbox/docker.py` | `tests/unit/sandbox/test_docker.py` |
| `gd.providers.OpenRouter` | `geomind/providers/openrouter.py` | `tests/unit/providers/test_openrouter.py` |
| `gd.providers.FakeLLM` | `geomind/providers/fake.py` | `tests/unit/providers/test_fake.py` |
| Memory and file stores | `geomind/engine/store.py` | `tests/unit/engine/test_store.py` |
| Memory and file workspaces | `geomind/engine/workspace.py` | `tests/unit/engine/test_workspace.py` |
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
- Pass `permissions` again to `Run.load`, like hooks and callbacks; a run does not store them.

## Proposed changes

These are additions the contract does not list yet; nothing in it was changed.

- `load_events(run_id)` as a ninth `RunStore` method. The contract leaves it out, yet continuing a
  run whose process died needs the events after the last checkpoint. A store without it can still
  pause and resume from its checkpoint; `resume()` without arguments then raises `RunError`
  instead of repeating recorded calls. `Engine.replay` needs it too.
- `error` as an eighth internal event type: `on_error` callbacks need an event object, and a
  survived error belongs in the log. See [events.md](events.md).
- `Callback.on_event`, beyond the listed methods: the public `usage` event has no method of its
  own, and a publisher needs one place to forward everything.

# Public API

Use `import geomind as gd`. The curated top level is `Run`, `Agent`, `Engine`, `Tool`, `tool`,
`Prompt`, `Model`, `Output`, `Context`, `Message`, `Action`, `Request`, `Allow`, `Deny`,
`Permissions`, `RunResult`, `runlog`, `event_from_dict`, `agents`, `tools`, `verify`, `loops`, `hooks`,
`callbacks`, `providers`, `sandbox`, `stores`, `testing`, `runtime`, `errors` and `__version__`.
`tests/unit/test_public_api.py` pins this list. New top-level names require a concrete common user
workflow, documentation, and a public-API test.

`Run` is the facade the backend uses. `Engine` is the lower layer for tests, evals and custom
loops. `gd.stores` exposes `MemoryRunStore`, `FileRunStore`, `MemoryWorkspace`, `FileWorkspace` and
the `RunStore` and `Workspace` protocols.

`gd.verify.verify(plant, results, case)` returns `{passed, checks, failures, metrics}` for a
`gm.Plant`, its `gm.Results` and the `gm.Case` they ran on: gemini's verdict, with each failure
routed to a domain. `verify_design(context)` does the same on the problem state's design.

## Run

```python
import geomind as gd

result = gd.Run(message="Say hello").start()
print(result.answer, result.usage)
```

```python
run = gd.Run(message=..., chat=..., project=..., history=..., llm=..., store=...,
             workspace=None, sandbox=None, permissions=None, callbacks=[...], hooks=[...],
             agent=None)
result = run.start()                     # or: result = await run.astart()
run = gd.Run.load(run_id, llm=..., store=..., workspace=None, sandbox=None,
                  permissions=None, callbacks=[...], hooks=[...])
result = run.resume(request_id, answer)  # or: await run.aresume(...)
result = run.resume()                    # continue a run whose process died
run.cancel()
```

Defaults: `chat=None`, `project=None`, `history=()`, `store=MemoryRunStore()`, `workspace=None`,
`sandbox=None`, `permissions=Permissions(mode="ask")`, `llm=OpenRouter()`; the engine adds the
retry layer to any provider. `start` asks the `Coordinator` first: its `Route` picks the loop and the
agent through the tables `LOOPS` and `AGENTS` of `geomind/run.py`, so the backend names neither. The
routing call is a nested run of the run (`parent` and `root` are the run's id), logged before the run
starts; its tokens are in `RunResult.usage`, with every delegate, loop round and summary. A routing run that fails keeps the
default: `ToolLoop` with `Analyst`, or `CodeAssistant` when a sandbox is configured. `agent` replaces
the routing, for testing one agent by hand, and so does a `run.loop` set before `start`. `answer` is `{"approved": true}`, `{"approved": false, "reason": "..."}` or
`{"text": "..."}`. `run.start()` inside an event loop raises `RunError`: use `astart`.

## Command line

- `geomind run "<message>" [--model ID] [--max-steps N] [--mode ask|auto|readonly|plan]
  [--sandbox local|docker] [--loop tool|design] [--project PATH]
  [--recording FILE] [--record FILE] [--max-tokens N] [--max-cost USD]` runs with `OpenRouter` and
  `FileRunStore(".runs")`, prints text as it streams, asks in the terminal when a request pauses the
  run, then resumes. `--loop` chooses the loop instead of the coordinator; `--recording` runs from
  recorded completions, offline; `--record` writes the completions of this run for that.
  `--max-tokens` and `--max-cost` are the spending cap: `TokenBudget` and `CostBudget` deny the next
  model call once the whole run, nested runs included, is over it, and the run ends `denied`. Beside the log it writes
  `.runs/<run id>/run_manifest.json`: the geomind and gemini commits (and whether either has
  uncommitted changes), `gd.__version__` and `gm.__version__`, the SHA-256 of each demand profile, of
  the recording and of the project's plant, the model ids each agent called, the run's settings, and
  the seeds (none: gemini is deterministic, geomind draws no random numbers, agents run at
  temperature 0).
  `--mode auto` with OpenRouter and no cap refuses to start (`RunError`).
- `geomind check-live [--max-cost USD] [--max-tokens N]` checks a first live run: `OPENROUTER_API_KEY`
  set (the value is never printed), every role's model id in OpenRouter's public model list (one
  GET; skipped with a message when it fails), and a cap given. It prints one line per missing item
  and exits 1 when anything is missing. See `evals.md`, "First live run".
- `geomind chat [--agent NAME] [--project PATH] [--live] [--recording FILE] [--model ID]
  [--max-steps N]` is an interactive session with any agent of `gd.agents`, skeletons included,
  `analyst` by default. Each turn prints the streamed
  text, every tool call with its input and a short output, the requests, answered at the prompt, and
  the problem state. `/state`, `/log` (the run log of the last turn), `/reset` (a new chat) and `/quit`
  are commands. It needs `--live` for OpenRouter or `--recording` for `FakeLLM` from a recording. Runs
  are saved in `.runs/`, so `geomind show` works on them.
- `geomind replay <run dir>` reruns offline and prints pass or the first mismatch.
- `geomind show <run dir> [--format md]` prints the log per step and the totals, built from
  `gd.runlog`. `--format md` is the export a report includes as it is: tokens by agent, by step and
  in total (the routing call and nested runs included, rule steps not counted as model calls), each
  agent's system prompt once, then every step with the messages new to it, its answers in full and
  its tool calls, whose output is cut at 2000 characters.

## Examples

`examples/basics/general/01_hello.py`, `02_custom_agent.py`, `03_approval.py`, `04_sandbox.py` and
`examples/backend/general/01_queue_and_resume.py`. Run them from the repository root as
`PYTHONPATH=. python examples/...`; each uses `FakeLLM` by default and OpenRouter with `--live`.

## Frozen interfaces

The interfaces the backend and the agent developer depend on are final and pinned by tests, so the
backend never breaks later. `gd.__version__` follows semver below 1.0, the same rule as gemini.

| What | Pinned in |
|---|---|
| `gd.Run` and its methods, `RunResult` with statuses and stop reasons | `tests/unit/snapshots/api.json` |
| The protocols `RunStore`, `Workspace`, `LLM`, `Sandbox`, `SandboxProvider`, and `Callback` | `api.json` |
| `gd.Permissions`, the shipped hooks, `Completion`, `Usage`, `Message` | `api.json` |
| Every event type with its `data()` keys, the answer shapes, `gd.runlog`, `gd.__all__` | `api.json` |
| Every tool: name, first line of the description, effect, idempotent, input schema | `tests/unit/snapshots/tools.json` |
| `Agent` methods, the declaration sections, `Prompt`, `Model`, `Output`, `Route` | `tests/unit/snapshots/agents.json` |
| The names of `LOOPS` and `AGENTS`, the loop constructors, the eval task, the CLI | `agents.json` |
| The documents exchanged with the backend | `geomind/schemas/*.json`, with one sample each in `samples/` |

The schemas are package data: `events.json` (one schema per public event's `data()`),
`problem_state.json`, `state_changed.json` (the JSON Patch subset), `request.json`, `answer.json`,
`runlog.json`, `tool_error.json` and `eval_task.json`. Each is generated from the model that defines
it, never edited by hand. Validate through the models, not with a schema library.
`tests/unit/test_frozen_api.py` compares all of it with the live package and names each item that
differs. `tests/unit/test_contract_map.py` checks that every item of the shared contract is in
`api.json`.

**The change rule.** A change to a frozen item needs, in the same commit:

1. a version raise in `geomind/__init__.py` and `pyproject.toml`: a breaking change raises the minor
   version, an addition or a fix the patch version;
2. `python scripts/snapshot_api.py`, which refuses to overwrite a snapshot of the current version;
   `--allow-same-version` is for an additive, non-breaking change only, and the changelog says which;
3. an entry in [CHANGELOG.md](../../CHANGELOG.md);
4. a note to Sahand when the shared contract is affected.

A stub keeps its signature when it is filled: filling one changes no snapshot.

**Not frozen:** prompt texts, skill texts, internal modules (anything not in a snapshot), and the
model ids in `runtime.py`.

## Errors

Every exception class is available as `gd.errors.<Name>`; see [errors.md](errors.md).

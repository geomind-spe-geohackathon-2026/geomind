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
retry layer to any provider. A run uses `ToolLoop` with `Analyst`, or `CodeAssistant` when a sandbox is
configured, through the tables `LOOPS` and `AGENTS` of `geomind/run.py`; `agent` replaces that choice,
for testing one agent by hand. `answer` is `{"approved": true}`, `{"approved": false, "reason": "..."}` or
`{"text": "..."}`. `run.start()` inside an event loop raises `RunError`: use `astart`.

## Command line

- `geomind run "<message>" [--model ID] [--max-steps N] [--mode ask|auto|readonly|plan]
  [--sandbox local|docker]` runs with `OpenRouter` and `FileRunStore(".runs")`, prints text as it
  streams, asks in the terminal when a request pauses the run, then resumes.
- `geomind chat [--agent NAME] [--project PATH] [--live] [--recording FILE] [--model ID]
  [--max-steps N]` is an interactive session with any agent of `gd.agents`, skeletons included,
  `analyst` by default. Each turn prints the streamed
  text, every tool call with its input and a short output, the requests, answered at the prompt, and
  the problem state. `/state`, `/log` (the run log of the last turn), `/reset` (a new chat) and `/quit`
  are commands. It needs `--live` for OpenRouter or `--recording` for `FakeLLM` from a recording. Runs
  are saved in `.runs/`, so `geomind show` works on them.
- `geomind replay <run dir>` reruns offline and prints pass or the first mismatch.
- `geomind show <run dir> [--format md]` prints the log per step and the totals, built from
  `gd.runlog`.

## Examples

`examples/basics/general/01_hello.py`, `02_custom_agent.py`, `03_approval.py`, `04_sandbox.py` and
`examples/backend/general/01_queue_and_resume.py`. Run them from the repository root as
`PYTHONPATH=. python examples/...`; each uses `FakeLLM` by default and OpenRouter with `--live`.

## Frozen interfaces

The list, the snapshots and the change rule arrive with the freeze commits.

## Errors

Every exception class is available as `gd.errors.<Name>`; see [errors.md](errors.md).

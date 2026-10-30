# Evals

Testing an agent by tasks. `evals/` is at the repository root, outside the package:

```text
evals/
├── tasks/<agent>/<name>.yaml         message, plant and criteria
├── recordings/<agent>/<name>.jsonl   one completion as JSON per line
├── tasks_format.py                   the task file and its criteria
├── run.py                            the runner
└── reports/                          generated; only summary.md is tracked
```

```bash
python -m evals.run --agent analyst          # offline, from recordings
python -m evals.run --agent analyst --live   # OpenRouter; writes the recording anew
```

`--live` needs `OPENROUTER_API_KEY` and stops with a clear message without it. Exit codes: 0 all
passed, 1 a task failed, 2 nothing could run (no tasks, an unknown agent, no key). A run uses
`Permissions(mode="auto")`, a memory store and `gd.agents.named(agent)`.

## Task file

| Field | Required | Meaning |
|---|---|---|
| `message` | yes | what the user says |
| `plant` | no | a project folder, opened with `FileWorkspace` |
| `history` | no | earlier messages, each `{role, content}` |
| `answers` | no | replies to the agent's questions, in order; a question with no reply left ends the run |
| `criteria` | yes | what must hold, checked by code, never by an LLM |

```yaml
message: How deep is the well?
answers: ["2100 m"]
criteria:
  - {kind: number, value: 2100, tolerance: 1, unit: m}
  - {kind: tool, tool: update_state}
  - {kind: tool, tool: search_documents, called: false}
  - {kind: question, contains: depth}
  - {kind: state, path: /goal}
```

## Criteria

| `kind` | Fields | Holds when |
|---|---|---|
| `number` | `value`, `tolerance`, `unit` (optional) | the answer holds a number within `tolerance` of `value`, followed by `unit` if one is given |
| `tool` | `tool`, `called` (default `true`) | the tool was called, or with `called: false` was not |
| `question` | `contains` | a question to the user holds this text, in any case |
| `state` | `path` | this JSON Pointer of the final problem state is set; items of a list are named by id |

A file with an unknown `kind` or field fails when it loads. A run that ends with `failed` fails its
task, whatever the criteria say.

## Report

`evals/reports/summary.md` and the terminal show, per task and in total: passed, steps, tool calls,
tokens, cost and time, then every failure with its reason.

## Recordings

A recording is what the provider answered, so an offline run makes no call. Write one with `--live`,
or by hand as JSON lines of `{text, tool_calls, usage, model}`. A recording that ends too early fails
the task with `run: error`.

## Status

There is no task yet: the sample task, the heat of the example doublet at 150 m3/h, needs the gemini
tools, whose number will be checked against gemini's own result. `tasks/<agent>/` exists for the
analyst and every skeleton. The runner and every kind of criterion are tested in
`tests/integration/test_evals.py`, with the real `Analyst`.

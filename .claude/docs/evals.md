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
| `state` | `path`, `equals` (optional) | this JSON Pointer of the final problem state is set, to `equals` when given; items of a list are named by id |
| `verified` | `checks` (optional) | gemini's checks pass again on the final state's design and result, with its brief (`verify_design`), and each named check is among them and passed |

A file with an unknown `kind` or field fails when it loads. A run that ends with `failed` fails its
task, whatever the criteria say.

## Report

`evals/reports/summary.md` and the terminal show, per task and in total: passed, steps, tool calls,
tokens, cost and time, then every failure with its reason.

## Suites

A folder of `SUITES` in `evals/run.py` runs its tasks through a loop instead of one agent:
`python -m evals.run --agent challenge2` runs `evals/tasks/challenge2/` through the `DesignLoop`.
Its four tasks are the hackathon brief and three variants, each with its own brief: `more_cooling`
(gemini's cooling profile scaled to a 15 MW peak, stored with `save_profile`), `colder_reservoir`
(25 K/km) and `user_profile` (30 daily heating values the user types, January only). Each names its
criteria: the brief set as given (`state` with `equals`), the design `verified` with the checks of
the demand met and of the brief's limits. A variant fails when the agents ignore its brief:
`tests/integration/test_evals.py` runs the hackathon design under the colder-reservoir and
more-cooling briefs (`tests/fixtures/recordings/*_ignored.jsonl`) and the loop rejects it on
`d0.gradient` and on `cool_users.unmet_sensible`. The recordings are hand-written, as the comment at
the top of each task says, with every reference and number from the real tools; the live run
replaces them.

## Recordings

A recording is what the provider answered, so an offline run makes no call. Write one with `--live`,
or by hand as JSON lines of `{text, tool_calls, usage, model}`. A recording that ends too early fails
the task with `run: error`.

## Status

`tasks/analyst/` holds five tasks on gemini's example doublet (`evals/projects/doublet/plant.json`,
`gm.plants.example("DoubletHeatPlant")`): the ESP operating point, the heat the exchanger delivers at
150 m3/h, a missing pipe diameter that needs `ask_user`, a module lookup, and the ESP at 45 Hz. Each
number in a criterion is gemini's, from the same inputs as the recorded tool call.
`tests/integration/test_evals.py` runs them offline.

`tasks/designer/`, `verifier/`, `economist/`, `explainer/` and `coordinator/` hold one task each; the
verifier and economist run the base design (`evals/projects/base/plant.json`) over the year. Their
recordings are written by hand too, with every reference and number from the real tool calls.

The recordings are written by hand (`model: hand-written`, no usage) until the first live run
writes them anew; see [plan.md](plan.md) S2b.6. The tasks give mass flows in kg/s beside m3/h,
because a module inlet takes a mass flow and the agent converts nothing itself. The runner and every
kind of criterion are tested in `tests/integration/test_evals.py`, with the real `Analyst`.

## The official brief

`evals/runs/official_brief_scripted.jsonl` is a scripted recording of the design loop on the
official brief: hand-written completions in the order the loop asks its agents, with every
reference and number from the real tools on the base design over the year. `tests/e2e/
test_official_brief.py` runs `geomind run --loop design --recording` on it and replays the run. It
checks the path to a verified design, not a model; the live run replaces it.

**The base design of this recording was found by hand**, in this repository's development, not by
an agent: the absorption chiller's generator in series between the heat pump and the boiler, and
the co-produced gas to the flare (`base_spec` in `tests/fixtures/hackathon.py`). Before 1 November
2026 the `designing-a-plant` skill and the Designer's prompt described that topology; since then
the skill is general and names no answer, and the hackathon's numbers are in the `hackathon-2027`
note. A live run therefore shows what the agents find on their own; the scripted run shows only that
the harness carries a verified design from the command line to the report.

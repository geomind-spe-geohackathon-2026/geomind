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
| `plant` | no | a project folder, opened with `FileWorkspace`: `case.json`, its demand file and, when the task starts from a plant, `plant.json` |
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
| `verified` | `checks` (optional) | `gd.verify.verify(plant, results, case)` passes again on the final state's design and its stored result, on the case that run used (`verify_design`), and each named check is among them and passed |

A file with an unknown `kind` or field fails when it loads. A run that ends with `failed` fails its
task, whatever the criteria say.

## Report

`evals/reports/summary.md` and the terminal show, per task and in total: passed, steps, tool calls,
tokens, cost and time, then every failure with its reason.

## Projects

The eval cases are data in `evals/projects/<project>/`: `case.json`, its demand CSV and, for some,
`plant.json`. They are **copies** of gemini's examples (gemini `dev` at `cca153b8`, folders
`inputs/examples/hackathon_2026`, `inputs/doublet_heat`), not paths into `../gemini`: a copy keeps
the recorded numbers and criteria stable when gemini's examples change, and a clone of this
repository needs no sibling checkout. When gemini's examples change, copy them again, rerun
`python -m evals.run --agent challenge2` and update the numbers of the criteria.

| Project | Holds | Used by |
|---|---|---|
| `hackathon` | the hackathon case, no plant | designer, coordinator and the `challenge2` tasks |
| `hackathon_plant` | the same case and `plants/HackathonPlant.json` | explainer; the plant dict the recordings build |
| `more_cooling` | the case with the demand CSV's cooling column x 1.5 (15 MW peak), no plant | `challenge2/more_cooling` |
| `doublet` | gemini's `doublet_heat/plant.json`, no case | analyst tasks |

The hackathon case is gemini's as it is, plus the constraints "demand is met" that the example case
lacks: for `heating_supply` and for `cooling_supply`,
`{"on": ..., "quantity": "unmet", "max": {"value": 1, "unit": "W"}, "over": "each", "when": "always"}`.
It is 1 W, not 0, because the roundoff of a met demand is 1e-15 MW. No other constraint is invented.
The projects are built by a script from the gemini folders (see `.tmp/adapt/G.md` of the adaptation);
`tests/integration/test_evals.py` checks they load, keep gemini's demand and hold the constraints.

## Suites

A folder of `SUITES` in `evals/run.py` runs its tasks through a loop instead of one agent:
`python -m evals.run --agent challenge2` runs `evals/tasks/challenge2/` through the `DesignLoop`.
Its four tasks are the hackathon case and three variants, each a case change:

| Task | Variant | What fails when it is ignored |
|---|---|---|
| `hackathon` | the case as it is | an unmet demand or a violated limit (`verified`) |
| `more_cooling` | the `more_cooling` project, a 15 MW cooling peak | the hand-found design fails `cool_users.supply_in.temperature` (21.67 degC against 20 degC) and `cool_users.unmet_sensible` (`verified`) |
| `colder_reservoir` | `set_case` changes `environment.ground.gradient` to 25 K/km | nothing physical: the design still passes, and no case constraint limits the boiler (for gemini's hand-found HackathonPlant its heat goes from 254 to 29 705 MWh and the LCTS from 48.5 to 53.6 EUR/MWh), and we do not invent one. The task checks `/case/environment/ground/gradient/value` is 25 and that the answer's LCTS is the 25 K/km value of the recorded design, 46.82 EUR/MWh (`number`), not the 35.93 of the same design at 30 K/km |
| `user_profile` | 30 January days of the user's heating and cooling (30 values given in the message): `set_case` cuts `time`, drops the duration constraint and the demand, `save_profile` twice, `set_case` restores the temperatures | `/case/time/end` or `/case/demand/file` is not the user's, or the heating demand is unmet |

A variant fails when the agents ignore its change: `tests/integration/test_evals.py` runs
`tests/fixtures/recordings/*_ignored.jsonl` on the variant's task. The unsized hackathon design on
the 15 MW case fails gemini's checks, repeats its failure and is rejected (`stop: repeated_failure`);
the design that ignores 25 K/km passes the checks but fails the `/case` state and the LCTS number.

The user's message of every `challenge2` task states what the Designer needs for `size_plant` and
`optimize`: the backup policy (`peak`), the objective (`lcts`), the variables (none: the case's
choices) and the evaluations (12). `answers` replies to the loop's first question (the run holds no
case yet; the reply tells the Designer to use the project's case). Tasks state their criteria on
`/case` paths. The recordings are hand-written decisions (`model: hand-written`): the Designer
builds gemini's `HackathonPlant` dict, sizes it, simulates, checks, optimises and simulates the best
design; every reference and number in the tool results is from a real gemini run, because they were
written by answering each model call from the results the run already held (the script is in the
adaptation notes). The live run replaces them.

## Recordings

A recording is what the provider answered, so an offline run makes no call. Write one with `--live`,
or by hand as JSON lines of `{text, tool_calls, usage, model}`. A recording that ends too early fails
the task with `run: error`.

## Status

`tasks/analyst/` holds five tasks on gemini's example doublet (`evals/projects/doublet/plant.json`):
the ESP operating point, the heat the exchanger delivers at 150 m3/h, a missing pipe diameter that
needs `ask_user`, a module lookup, and the ESP at 45 Hz. Each number in a criterion is gemini's,
from the same inputs as the recorded tool call. `tests/integration/test_evals.py` runs them offline.

`tasks/designer/`, `explainer/` and `coordinator/` hold one task each. The Verifier and the
Economist no longer have a task of their own: they cannot simulate or set a case, so they are
evaluated inside `challenge2` (the criteria `check_results`, `estimate_costs` and the LCTS number of
`hackathon`). Their recordings are hand-written (`model: hand-written`, no usage) until the first
live run writes them anew. The tasks give mass flows in kg/s beside m3/h, because a
module inlet takes a mass flow and the agent converts nothing itself.

## The scripted runs

`evals/runs/hackathon_scripted.jsonl` and `tests/fixtures/recordings/shallow_district_scripted.jsonl`
are scripted recordings of the design loop on the hackathon case and on gemini's shallow-district
example: hand-written decisions in the order the loop asks its agents (Designer: set the case, read
it, build, size, simulate, check, optimise, simulate the best, record; Verifier: check once;
Economist; Explainer), with every reference and number from the real tools.
`tests/e2e/test_scripted_design.py` runs `geomind run --loop design --project <case folder>
--recording ...` on each, answers the loop's question, and replays the run. It checks the path to a
verified design, not a model; the live run replaces it. A design run needs a project with a
`case.json`: the command stops without one.

**The plant of these recordings was found by hand** (gemini's `HackathonPlant`, and the shallow
example's `plant.json`), not by an agent. A live run shows what the agents find on their own; the
scripted runs show only that the harness carries a verified design from the command line to the
report.

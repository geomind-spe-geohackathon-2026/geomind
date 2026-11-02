# Evals

Testing an agent by tasks. `evals/` is at the repository root, outside the package:

```text
evals/
├── tasks/<agent>/<name>.yaml         message, plant and criteria
├── recordings/<agent>/<name>.jsonl   one completion as JSON per line (agent: a folder of tasks)
├── tasks_format.py                   the task file and its criteria
├── run.py                            the runner
└── reports/                          generated; only summary.md (the loop report) is tracked
```

```bash
python -m evals.run --agent analyst          # offline, from recordings
python -m evals.run --agent analyst --live   # OpenRouter; writes the recording anew
python -m evals.run --report                 # offline: every task through three loops
```

`--live` needs `OPENROUTER_API_KEY` and stops with a clear message without it. Exit codes: 0 all
passed, 1 a task failed, 2 nothing could run (no tasks, an unknown agent, no key). A run uses
`Permissions(mode="auto")`, a memory store and `gd.agents.named(agent)`.

## Task file

| Field | Required | Meaning |
|---|---|---|
| `message` | yes | what the user says |
| `plant` | no | a project folder, opened with `FileWorkspace` (gemini's layout: `case.json`, `economics.json`, `data/`, `plants/`); a task about "the project's plant" needs exactly one file in `plants/` |
| `history` | no | earlier messages, each `{role, content}` |
| `answers` | no | replies to the agent's questions, in order; a question with no reply left ends the run |
| `max_steps` | no | caps the steps of every agent of the run (`runtime` setting `max_steps`), for a task about a tight budget |
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

`python -m evals.run --agent <name>` prints, and writes to `evals/reports/<name>.md` (not
tracked), per task and in total: passed, steps, tool calls, tokens, cost and time, then every
failure with its reason.

`designer/project_plant` (project `hackathon`, recorded by script, no live call) lists the plants,
reads the project plant, stores it with `build_plant` and sizes `design/start`.

`python -m evals.run --report` writes the tracked `evals/reports/summary.md`: every task of every
folder, offline from its recording, through `ToolLoop`, `DesignLoop` and `CompareLoop` (the
`MakerCheckerLoop` is gone). One table per loop, a row per task and a total: criteria met, steps,
tool calls, tokens, cost and time. `ToolLoop` runs the task's agent (the Designer alone for a suite).
A recording holds the decisions of one loop, so a loop whose agents ask for other steps meets a task
it cannot finish: its criteria are unmet, and the table shows how many held. A loop that raises
fails its task and does not stop the report. Time differs between runs, so
`tests/integration/test_evals.py` (slow) compares the checked-in report with a new one with the
time cells blanked. Regenerate and commit it when a task, a recording or a loop changes.

## Projects

The eval cases are gemini's project folders in `evals/projects/<project>/`: `case.json`,
`economics.json`, `data/demand.csv` and, for some, `plants/`. They are **copies** of gemini's
examples (`../gemini/examples/hackathon_2026` and `shallow_district`, gemini 0.5.0), not paths into
`../gemini`: a copy keeps the recorded numbers and criteria stable when gemini's examples change,
and a clone of this repository needs no sibling checkout. When gemini's examples change, copy them
again, rerun `python -m evals.run --agent challenge2` and update the numbers of the criteria.
`tests/integration/test_evals.py` checks the copies are byte-equal to the examples, and that each
variant differs from its example in one thing.

| Project | Holds | Used by |
|---|---|---|
| `hackathon` | the hackathon example with its six plant files | the `challenge2` tasks `hackathon`, `colder_reservoir`, `user_profile`, `tight_budget`; designer, coordinator |
| `hackathon_plant` | the same, with the one plant file `HackathonPlant` | explainer; `examples/basics/general/05_case.py` |
| `shallow_district` | the shallow-district example | `challenge2/verifier` |
| `more_cooling` | the case with the demand CSV's cooling column x 1.5 (15 MW peak), no plants | `challenge2/more_cooling` |
| `colder_reservoir` | the case with `site.ground.gradient` 25 K/km, no plants | the variant as a project, for runs and tests |
| `higher_gas` | the economics with `energy.gas` 70 EUR/MWh (the example's 39.92), no plants | `challenge2/economist` |
| `user_profile` | 30 January days of the user's heating and cooling (`data/demand.csv` of 30 rows, `time.end` 2027-01-31, no `running_time_limit`), no plants | the variant as a project, for runs and tests |

A variant is a new case or economics file; a variant has no `plants/`, because the model starts
from a plant class (`read_plant(plant_class=...)`) and builds the plant file itself. Gemini's cases
carry their own requirements (delivered share, supply temperature, flow range, brine cooling), and
none is added here.

## Suites

A folder of `SUITES` in `evals/run.py` runs its tasks through a loop instead of one agent:
`python -m evals.run --agent challenge2` runs `evals/tasks/challenge2/` through the `DesignLoop`;
`--agent compare` runs `evals/tasks/compare/` through the `CompareLoop`. The `challenge2` tasks:

| Task | Project | What it checks, and what fails when it is ignored |
|---|---|---|
| `hackathon` | `hackathon` | the case as it is: an unmet requirement (`verified`), the LCTS of the design (`number`) |
| `more_cooling` | `more_cooling` | a 15 MW cooling peak: the unsized plant fails `cold_delivered` and `cooling_supply_temperature` (`verified`) |
| `colder_reservoir` | `hackathon` | `set_case` changes `site.ground.gradient` to 25 K/km: the case state (`/case/site/ground/gradient/value`) and the LCTS of the 25 K/km design (`number`), not the 30 K/km one |
| `user_profile` | `hackathon` | 30 January days of the user's demand: `set_case` cuts `time` and drops `running_time_limit`, `save_profile` twice (heating, cooling), the `/case` paths are the user's and the requirements hold |
| `verifier` | `shallow_district` | the Verifier's part on a second example: `check_results` is called, `/verification/result` is set, the design is verified |
| `economist` | `higher_gas` | the Economist's part: `estimate_costs` and `sample_uncertainty` are called, the LCTS in the answer is the one on the higher gas price (`number`), `/results/costs` is recorded |
| `tight_budget` | `hackathon` | `max_steps: 7`: the Designer cannot reach `optimize`, so the loop ends without a design and says so; `optimize` and `estimate_costs` are not called |

### The compare task

`compare/two_families` (project `hackathon`) asks the `CompareLoop` for two topologies of the
project's case, `HeatingAbsorptionCoolingPlant` and `HeatingCoolingPlant`, with the peak backup
policy and the doublets (1 to 2) as the only range, compared with one `run_study` named `families` (objective
`lcts`, 5 evaluations, seed 1), whose designs are stored as `design/families_<plant>`; the
`sample_uncertainty` calls of the challenge2 recordings are named `draws`. Criteria: `run_study` and `check_results` are called,
`/design/study/runs` and `/design/reference` are set, `/verification/passed` is true and
`verified` holds (gemini's verdict on the recorded design). The recording is hand-written
(`model: hand-written`, the task file says so): the decisions are by hand, the numbers in the tool
results (the ranked table of the study, the references) come from real gemini runs, because it
was written by answering each model call from the results the run already held. The Designer
builds both plants from gemini's example files, since a project with several plants has no
named-plant access. The live run replaces it.

A variant fails when the agents ignore its change: `tests/integration/test_evals.py` runs
`tests/fixtures/recordings/*_ignored.jsonl` on the variant's task. The unsized plant on the 15 MW
case fails gemini's checks, repeats its failure and is rejected (`stop: repeated_failure`); the
design that ignores 25 K/km passes the checks but fails the `/case` state and the LCTS number.

The user's message of every `challenge2` task states what the Designer needs: the plant class
(`HeatingHeatPumpCoolingPlant`), the backup policy (`peak`, which the plant file already holds),
the objective (`lcts`), the ranges (the plant's own) and the evaluations (30, `seed 0`; gemini wants
5 per variable). `answers` replies to the loop's first question (the run holds no case yet; the
reply tells the Designer to use the project's case). A task that changes the project's case
(`colder_reservoir`, `user_profile`) has a second answer, `approve`: verification fails with
`case_changed` until the user approves a case that differs from the one they gave, so the loop asks
once. Tasks state their criteria on `/case` paths.

The recordings are hand-written decisions (`model: hand-written`): the Designer reads the plant
class, sets the case, builds the plant file, sizes it, simulates, checks, optimises, simulates and
checks the best design, and records it. When the search finds no feasible design (the 15 MW case in
30 evaluations) the Designer records the sized design instead, which passes. Every reference and
number in the tool results is from a real gemini run, because the recordings were written by
answering each model call from the results the run already held. The live run replaces them.

## Recordings

A recording is what the provider answered, so an offline run makes no call. Write one with `--live`,
or by hand as JSON lines of `{text, tool_calls, usage, model}`. A recording that ends too early fails
the task with `run: error`.

## Status

`tasks/analyst/` holds five tasks on gemini's modules, with no project: the ESP discharge pressure at
60 Hz, its head at 45 Hz and 30 kg/s, the heat of an exchanger at 150 m3/h, a missing pipe diameter
that needs `ask_user`, and a module lookup. The messages carry the module parameters, because a
module takes every value of its own. Each number in a criterion is gemini's, from the same
`evaluate_module` call as the recording, in display units (MW, Pa).
`tests/integration/test_evals.py` runs them offline.

`tasks/designer/`, `explainer/` and `coordinator/` hold one task each. The Verifier and the
Economist have tasks of their own in `challenge2` (`verifier`, `economist`), because they cannot
simulate or set a case and so run inside the design loop. Their recordings are hand-written
(`model: hand-written`, no usage) until the first live run writes them anew.

## The scripted runs

`evals/runs/hackathon_scripted.jsonl` and `tests/fixtures/recordings/shallow_district_scripted.jsonl`
are scripted recordings of the design loop on the hackathon project and on gemini's shallow-district
example: hand-written decisions in the order the loop asks its agents (Designer: read the plant
class and the case, build, size, simulate, check, optimise, simulate and check the best, record;
Verifier: check once; Economist; Explainer), with every reference and number from the real tools.
`tests/e2e/test_scripted_design.py` runs `geomind run --loop design --project <project folder>
--recording ...` on each, answers the loop's question, and replays the run. It checks the path to a
verified design, not a model; the live run replaces it. A design run needs a project with a
`case.json`: the command stops without one.

**The plant file of these recordings is gemini's example file** (`HeatingHeatPumpCoolingPlant.json`
of each example), not one an agent wrote. A live run shows what the agents find on their own; the
scripted runs show only that the harness carries a verified design from the command line to the
report.

## First live run

The harness has never called a model. Do the first live run in three steps, each with a cap.

```bash
export OPENROUTER_API_KEY=...        # in your shell only, never in a file
geomind check-live --max-cost 1
geomind run "What is the ESP operating point?" --loop tool --project <folder> --mode auto --max-cost 1
geomind run "<the brief>" --loop design --project <case folder> --mode auto --max-cost 20 \
  --record evals/runs/official_brief_live.jsonl
```

1. `geomind check-live --max-cost 1` prints one line per missing item and exits non-zero when
   anything is missing: the key (only "set" or "not set" is shown), a model id of any role (the
   resolved settings, `default_model` where a role has none) absent from OpenRouter's public model
   list, and the cap. Without network the list check is skipped with a message.
2. A cheap Analyst question: `geomind run "<question about the project>" --loop tool --project
   <folder> --mode auto --max-cost 1`. `--loop tool` is the Analyst's loop.
3. The design loop with `--loop design --project <case folder> --mode auto --max-cost 20 --record
   evals/runs/official_brief_live.jsonl`. `--record` writes every completion of the run as a
   recording; `geomind run ... --recording FILE` and `geomind replay .runs/<id>` replay it offline.
   Runs are stored in `.runs/<id>/` (log and `run_manifest.json`).

`geomind run --mode auto` with the real provider and neither `--max-cost` nor `--max-tokens`
refuses to start. A recording needs no cap.

`tests/integration/test_eval_replay.py` runs every task of `evals/recordings/` into a store and
replays it (single agents in the fast tier, the `challenge2` and `compare` loop suites `slow`), so
a recording that stops replaying fails in CI.

What to check in the answer: the verdict is feasible; the assumptions are listed (agent choices
with `confirmed: false` and a reason); costs are in display units, not SI; `geomind show <run>
--format md` shows the token table by agent and step, and the total stays under the cap (a run over
it ends `denied`).

To re-record the challenge2 recordings live: `python -m evals.run --agent <name> --live` for each
agent folder under `evals/tasks/`, and `python -m evals.run --agent challenge2 --live` for the suite
(each writes its recordings anew); then run the same commands without `--live` to confirm they pass. The scripted recordings of the previous section are replaced by `official_brief_live.jsonl`.

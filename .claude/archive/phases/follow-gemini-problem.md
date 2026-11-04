# Task: geomind follows gemini's new API, and the brief becomes gemini's Problem

## 0. Context and rules

- **Goal.** gemini changed a lot since geomind last followed it (geomind `main` at `2964c69` still calls `gm.profiles.get`, `gm.plants.from_template`, `gm.plants.spec_schema`, `gm.checks.Limits`, `gm.kpi`, `gm.economics`, `operating_days`). gemini `refactor` is now at `2453af1` with a new folder layout and one `gm.Problem` object: every gemini call takes `(plant, problem)` and, when it reads a run, `results`. This task makes geomind use only that API and replaces geomind's `Brief` with gemini's `Problem`.
- **The rule (most important).** geomind is general: it must design for any heating and cooling problem. The GEMINI hackathon is only one test problem. No competition number, name or preset lives in the `geomind/` package (code or prompts); it lives as data in test and eval fixtures.
- **gemini is the source of truth.** geomind uses gemini's shapes (`Problem`, `Constraint`, `Assumptions`, the plant dict) as they are and never invents a parallel shape. When gemini cannot express something geomind needs, keep it out of the problem, say so in the report as a gemini request, and do not work around it with geomind math. **geomind computes no physics and no economics**: every number comes from gemini.
- **Workspace.** The `crust-team/` folder that holds `geomind/` and `gemini/`. Change **only** `geomind/`. Read `../gemini/` but never change it. Report what it needs instead.
- **Read first:** `AGENTS.md`, every file in `.claude/docs/` (start with `plan.md`), then in gemini: `.claude/docs/api.md` (its "unreleased changes" list every rename), `conventions.md`, `data.md`, `gemini/__init__.py`, `gemini/run/problem.py`, `constraint.py`, `assumptions.py`, and `inputs/examples/*/`.
- **Pre-check.** `git status` is clean on `main` and `git pull origin main` succeeds. In `../gemini/`: if `git status` is clean, `git fetch origin && git checkout refactor && git pull origin refactor`; it must be at `2453af1` or later. If it is not clean, stop and say so. No other Claude session works inside `geomind/`.
- **Branch.** Work directly on `main`: one commit per section, push `origin main` at the end. No other branch, no PR.
- **Frozen interfaces.** Follow `.claude/docs/api.md#frozen-interfaces`. If a section must change a frozen item, follow the change rule there in the same commit (version raise, `scripts/snapshot_api.py`, CHANGELOG) and list it in the report.
- **Read/write naming (standing rule, shared with gemini).** Every reader is `from_<format>` and every writer `to_<format>` (`from_dict`, `from_json`, `to_dict`, `to_json`, ...). A reader is a classmethod on the class it returns; a writer is a method of the object. No new `read_*`, `write_*`, `load_*`, `save_*` names in Python APIs. (Tool names the model sees may keep verb names such as `read_plant`; say if you rename any.) Add this rule to `conventions.md`.
- **Speed (we are short of time).** Work in parallel wherever it is safe. Target: well under an hour.
  - Alone, in order: section 1, then section 2 (they change the state shape everyone reads). Commit each.
  - Then four subagents on sonnet, each in its own git worktree on a temporary branch from that commit, each owning only its files:
    - **A:** section 3a, owns `geomind/tools/gemini/plants.py`, `catalogue.py` and their tests;
    - **B:** section 3b, owns `runs.py`, `results.py` and their tests;
    - **C:** sections 3c and 4, owns `assessment.py`, `verification.py`, `geomind/verify/` and their tests;
    - **D:** section 5, owns `geomind/prompts/`, `evals/`, `tests/fixtures/`.
    Give each its section text, the rules of section 0 and its file list. Each commits once and runs only the tests of its files.
  - Review each branch, bring them onto `main` in order, fix overlaps, then section 6, `make test-all` and `make lint` once, push, report.
  - Read-only searches use haiku. Remove the worktrees and temporary branches at the end.
- **Tests.** While working, only the tests of changed files and their importers (`make test` / `scripts/test_changed.py`), in parallel. `make test-all` and `make lint` once before the push. A failing test before each bug fix. No network, no live OpenRouter run, no fast test over about 1 s, never delete or weaken a test (rewriting one to the new API is fine). If machine load makes a 1 s budget test fail, rerun it alone and say which.
- **Quality bar** (`.claude/docs/conventions.md`): nesting at most 3, functions about 40 lines, flake8 `max-complexity = 10`, guard clauses, full-word names, explicit `gd.errors`, no dead or speculative code, no comments inside code (docstrings and `NOTE:` only), no new runtime dependency, never import a gemini internal path (only names exported by `gemini/__init__.py` and its folders' `__init__`).
- **Temporary files** go to `.tmp/problem/`.

## 1. Old gemini names → new

Use this map, and `../gemini/.claude/docs/api.md` for anything not in it. Never guess a name.

| geomind uses today | gemini now |
|---|---|
| `gm.profiles.get`, `gm.profiles.names` | removed: gemini ships no profile; demand comes from `problem.demand`, built with `gm.data.from_csv` / `from_values` |
| `gm.plants.from_dict(d)` | `gm.Plant.from_dict(d)` |
| `gm.plants.spec_schema()` | `gm.plants.schema()` |
| `gm.plants.from_template(name)` | removed: templates are plant classes (`gm.plants.get(name)`) |
| `gm.plants.example(name)` | still there; raises `NotImplementedYet` for template classes |
| `apply_inputs` bridge (`boundary[""]["inputs"]`) | the plant dict's own `inputs` key; remove the bridge |
| `gm.schedule(plant, demand, rules)` | `gm.schedule(plant, problem)`; `rules` and `order` are gone, dispatch is by cost from `problem.assumptions.prices` |
| `gm.simulate(plant, plan, ...)` | `gm.simulate(plant, problem, ...)` (schedules inside); `plan=` for a plan without a problem |
| `gm.kpi.totals`, `gm.kpi.compute` | `gm.evaluate.totals(plant, problem, results)` |
| `gm.economics.Assumptions` | `gm.Assumptions`, inside `problem.assumptions`; prices only in `prices` |
| `gm.economics.lcoh/lcoc/lcts/capex/opex/co2` | `gm.evaluate.<same>(plant, problem, results)` (`capex(plant, problem)`) |
| `gm.checks.Limits`, `gm.checks.limits`, `operating_days` | `gm.Constraint` in `problem.constraints`, checked by `gm.evaluate.constraints(plant, problem, results)` |
| `gm.checks.run_all`, `gm.checks.plant_balance` | `gm.evaluate.run_all(...)`, `gm.evaluate.plant_balance(...)` |
| `gm.evaluate(module, ...)` | `gm.call(module, ...)` |
| `gm.testing.check_module` | `gm.modules.check` |
| `gm.optim.minimize`, `sample` | `gm.optim.minimize(plant, problem, ...)`, `sample(plant, problem, ...)` |
| `gm.units`, `gm.errors`, `gm.Results.from_bytes`, `gm.modules.get/names/categories` | unchanged |

Stubs in gemini (raise `NotImplementedYet`, do not call yet): `gm.optim.size`, `gm.optim.sensitivity`, `gm.evaluate.capacities`, `report`, `compare`, `gm.data.synthesize`, `gm.plants.capabilities`.

Record the gemini commit and every geomind file and line that uses an old name in `.tmp/problem/gemini.md`. No commit for this section unless something changed.

## 2. The brief becomes gemini's Problem (alone, before the subagents)

- The problem state keeps a gemini problem: `gm.Problem(...).to_dict()`, with the demand inside in gemini's shape. Remove `Brief`, its records and `PRESETS` from `geomind/context/brief.py`; keep `source` (user or agent) beside the problem in the state if the state needs it.
- `set_brief` becomes `set_problem(problem, changes)`: the input schema is gemini's problem schema (`gm.Problem.schema()` or what api.md names), offered late like `build_plant`'s plant schema. Validation is gemini's (`gm.Problem.from_dict`), its errors returned as a result the model can fix.
- **Brief fields gemini expresses:** reservoir values that are plant parameters → `site` (parameter paths); flow range, brine cooling, operating time, pump efficiency, volume balance, supply temperatures, demand met → `Constraint`s; prices, lifetime, discount rate → `Assumptions`.
- **Brief fields gemini cannot express in a Problem** (today at least: the doublet count range, return temperatures that are only assumptions, brine density, viscosity, gas ratio and composition, which gemini keeps in the plant dict's `fluids`): do not invent a geomind shape. Brine values go where gemini keeps them (the plant's `fluids`); for the rest, list each in the report as a gemini request, and say what the agents now do without it.
- No preset in code. The hackathon problem becomes fixture data: copy `../gemini/inputs/examples/hackathon_2027/problem.json`, its demand CSV and `plant.json` into `tests/fixtures/problems/hackathon_2027/` (and the evals' fixture folder if it is separate), and load them with `gm.Problem.from_json` / `gm.Plant.from_json`. Add `shallow_district` the same way, so every flow is tested on two problems.
- A tool that needs a problem and finds none raises a result that says so (`set_problem` first); there is no fallback problem.
- Tests: `set_problem` round trip, a validation error from gemini, a missing problem.

## 3. The gemini tools

### 3a. Plants and catalogue (subagent A)
- `gm.Plant.from_dict`, `gm.plants.schema()`; remove `apply_inputs`.
- `template/<Name>` refers to a plant class: the tool returns what gemini gives for it (`describe()`, missing parameters); `example/<Name>` stays where `gm.plants.example` works. Never build a plant with numbers geomind chose.
- `evaluate_module` uses `gm.call`.

### 3b. Runs and profiles (subagent B)
- A run is `gm.simulate(plant, problem, on_error="record")` with the state's problem (and a stored plant). Totals from `gm.evaluate.totals`.
- No built-in profiles: `list_profiles` / `read_profile` show the problem's demand and the user's saved profiles. `save_profile` builds the profile with `gm.data.from_values` (gemini validates and converts units), and `set_problem` can take a saved profile as the demand.

### 3c. Assessment and verification (subagent C)
- `compute_kpis` → `gm.evaluate.totals`. `estimate_costs` → `gm.evaluate.capex/opex/lcoh/lcoc/lcts` with the problem's assumptions; remove geomind's own LCTS arithmetic in `assessment.lcts`.
- Verification is gemini's checks only: `gm.evaluate.run_all` (it includes `constraints`) and `gm.evaluate.plant_balance`. Remove `challenge_limits`, `doublet_limits`, `grid_limits`, `operating_days_reason`, the hand-built limits and anything that re-checks what a `Constraint` now checks. Keep a geomind check only if it reads a gemini result and computes nothing (for example, which grids exist), and say which you kept. A constraint with `passed: null` stays "not assessed" with gemini's reason.

## 4. optimize and sample_uncertainty (subagent C)

The two S4 stubs become thin tools over `gm.optim.minimize(plant, problem, ...)` and `gm.optim.sample(plant, problem, ...)`, with gemini's argument names and results. No geomind math. Tests on a small plant of the fixture problems, under the fast budget (use gemini's smallest options). Update `plan.md`.

## 5. Prompts, skills and evals (subagent D)

- Every prompt and skill uses the new tool names and gemini's terms (`Problem`, `Constraint`, `Assumptions`, cost dispatch). No `HackathonPlant`, no `operating_days`, no `gm.kpi` / `gm.checks` / `gm.economics`.
- **No competition numbers in `geomind/prompts/`.** `skills/hackathon-2027.md` leaves the package: its content becomes the fixture problem of section 2 plus, if an eval needs the prose, a file in `evals/`. The general design skill explains how to read any problem.
- Evals and recordings: rewrite every recording and task to the new tool names and arguments (a script under `scripts/` if mechanical), or re-record offline with the scripted fake model. Never weaken an eval. The four challenge-2 variants keep their intent (colder reservoir, more cooling, a user profile).
- A quality test: no file in `geomind/` (Python and prompts) contains `hackathon`, `challenge_rules` or `HackathonPlant` (case-insensitive for `hackathon`).

## 6. Docs and report

- `AGENTS.md`, `plan.md` (what is built, remaining work), `tools.md` (tool list and inputs), `context.md` (the problem state), `conventions.md` (read/write naming, generality rule), `api.md` if a frozen or public item changed, CHANGELOG.
- **Report:** commits and the pushed hash; every old gemini call and what replaced it; every brief field and where it went (site, constraint, assumptions, plant `fluids`, or a gemini request); geomind checks kept or removed; frozen items changed; the gemini requests; what this breaks in `../backend/` (read-only, file and line, for example `backend/src/core/gemini/plant.py` uses `plant_type` and `HackathonPlant`).

# geomind: adapt to gemini `dev` (Case replaces Brief)

You work in the geomind repository (the current folder). gemini is the sibling folder `../gemini`, installed editable from `pyproject.toml` (`path = "../gemini"`). Work directly on `main` of geomind, commit after each section, push `origin main` at the end. Never edit, commit to or push gemini.

This prompt is self-contained: everything you need is below or in the two repositories. Do not look for files outside them.

## 0. Goal and fixed rules

**Goal.** geomind `main` (`2964c69`) was built on an old gemini (`c50cbdd`). gemini `dev` (`cca153b` or newer) refactored its public API: the problem is now a `gm.Case` (`case.json` + a demand CSV) that holds the environment, demand, constraints, choices, assumptions and uncertainty; evaluation, sizing, optimisation and uncertainty are in `gm.evaluate` and `gm.study`. geomind still calls about 25 gemini names that no longer exist, and its own `Brief` (`geomind/context/brief.py`) and `geomind/tools/gemini/verification.py` duplicate what `gm.Case` and `gm.evaluate` now do. Make geomind run on gemini `dev`, with gemini doing every engineering job and geomind doing only agent work.

**gemini is the source of truth.** geomind adapts to gemini, never the other way. Where gemini can do a job (a check, a unit conversion, a cost, a sizing, a constraint), geomind calls it and holds no copy of the logic. Where gemini lacks a general capability that geomind needs, do NOT work around it with private gemini names or a geomind re-implementation: write it to `.tmp/adapt/gemini-requests.md` (what, why, the general form it should take) and make the geomind side raise a clear `ToolError` with code `not_implemented` until gemini has it.

**Decisions already taken (do not reopen):**

1. `gm.Case` replaces geomind's `Brief`. `ProblemState.brief` is removed; `ProblemState.case` holds the case as `gm.Case.to_dict()` (plain JSON). The `hackathon_2027` preset and `PRESETS` leave the package.
2. Everything geomind checks about a design comes from the case through `gm.evaluate.report(plant, case, results)` (and `constraints`, `failures`, `run_all`, `plant_balance`). geomind's own limit building, `not_given`, `not_assessed`, the doublet reservoir check and the operating-days reason are deleted; the reservoir values reach the doublets through the case itself.
3. Plants are gemini plant dicts (`gm.Plant.to_dict(structure=True)` / `gm.Plant.from_dict`), validated by `gm.plants.validate`, with `gm.plants.schema()` as the tool input schema.
4. The new gemini study functions become geomind tools, replacing the `optimize` and `sample_uncertainty` stubs.
5. This is a breaking change of frozen interfaces: raise geomind to `0.2.0`.

**Standing rules (all apply):**

- **General, not the competition.** The hackathon is one sample problem. No hackathon numbers, names or defaults in `geomind/`. The hackathon case is test/eval data only. Test every changed path on at least two problems: gemini's `inputs/examples/hackathon_2026` and `inputs/examples/shallow_district`.
- **No default values** for engineering assumptions anywhere in geomind (prices, limits, backup policy, objective, evaluations count, seeds of a study). Missing means a clear error or an `ask_user`, never a hidden value. `gm.study.size` needs `backup` stated; the tool takes it as a required argument.
- **Units.** Pass every dimensional value to gemini as `gm.units.Quantity(value, unit)` or as gemini's `{"value": ..., "unit": ...}` dict, never as a bare SI float and never as a unit string like `"2500 m"`. A parallel gemini task (`feature/correctness`) will make bare floats an error in `set_params`, `gm.call`, `Stream` and `Fluid`, and will remove module parameter defaults; geomind must already be correct for that.
- **Only gemini's public API.** No `gm._x`, no `gemini.<pkg>._utils`, no private attribute (`_set_inputs`, `frame` set by hand, ...). Add a quality test that fails on any private gemini name in `geomind/`.
- **I/O naming:** `from_<format>` / `to_<format>` (`from_dict`, `from_json`, `to_csv`, ...).
- **Code quality:** simple, readable, just enough code; nesting ≤ 3, functions about ≤ 40 lines, flake8 max-complexity 10, guard clauses, full-word names, no dead or speculative code, no compatibility aliases for removed names. **No comments inside code** except the fixed section headers and tool directives; explanations go in docstrings. Write a failing test before each bug fix.
- **Tests.** Use the development profile while working (`make test`: tests of changed files and of everything that imports them, parallel, budget under 300 s). Run `make test-all` and `make lint` once before the final push, never the slow tier in a loop. New tests go in the right tier, reuse the session fixtures, and no fast test over about 1 s. If the 1 s CLI tests (`test_run_passes_the_model`, `test_run_prints_streamed_text_and_totals`) only fail under load and pass alone, report them, do not loosen them.
- **Docs in the same commit.** Every behaviour or structure change updates `.claude/docs/` (and AGENTS.md "Start here" if needed), so a new session reads the docs and knows the current state.
- **Temporary files** (inventory, baselines, audit lists, gemini requests) go in `.tmp/adapt/` (git-ignored). Lasting docs only in `.claude/docs/`.
- **No live LLM calls.** There is no `OPENROUTER_API_KEY` in this environment; all evals stay offline. Recordings stay hand-written and every recording file says so.
- **Speak up.** If something is missing, risky, or needs Sahand (backend contract, keys, a gemini change), put it in the final report instead of staying silent.

## 0b. How you work: coordinator only

You (the main session) are a pure coordinator: you plan, dispatch subagents, review their diffs and short summaries, merge, and run the tests. You never edit many files or read large files yourself.

- Workers use a lighter model: `sonnet` for implementation, `haiku` for read-only search and inventory.
- Each implementation worker gets its own git worktree (`git worktree add ../geomind-<section> -b adapt-<section>`, local only, never pushed) and an explicit, disjoint list of files it owns. A worker that needs a change in a file it does not own reports it instead of making it.
- Each worker writes details to `.tmp/adapt/<section>.md` and returns a summary of at most 15 lines: what changed, tests run, open points.
- You merge each worker branch into `main` (fast-forward or merge commit), run `make test`, fix conflicts yourself only when small, then delete the worktree and the local branch.
- Phases run in the order of section 9; sections inside one phase run in parallel.

## 1. Setup and inventory (phase 1)

1. In `../gemini`: `git fetch origin && git checkout dev && git pull --ff-only`. Record the hash in `.tmp/adapt/setup.md`. If `dev` is past `cca153b`, read its `CHANGELOG.md` entries since `cca153b` and apply them too (especially `feature/correctness`, if merged: Quantity everywhere, defaults removed, new roles `heat_output`, `cold_output`, `plant`, `gm.plants.validate` accepting a `Plant`).
2. If `.venv` launchers point at an old folder (`make lint` fails with a bad interpreter), recreate geomind's venv and reinstall with gemini editable.
3. Baseline: run `make test` and record which tests fail and why (`.tmp/adapt/baseline.md`).
4. Inventory (haiku worker): every gemini name geomind uses, in `geomind/`, `tests/`, `evals/`, `examples/`, `scripts/`, the prompts and skills (`geomind/prompts/**/*.md`) and `.claude/docs/`. For each: file:line, old name, new name from the appendix table, and whether the new API changes the meaning (not only the name). Also list every use of `Brief`, `brief`, `preset`, `hackathon_2027`, `set_brief`, `apply_inputs`, `limits`, `Limits`. Write `.tmp/adapt/inventory.md`.
5. Read gemini's own docs for the names you will use (`../gemini/docs`, `../gemini/.claude/docs/` if present, docstrings of `gemini/case`, `gemini/evaluate`, `gemini/study`, `gemini/plants`, `gemini/run`), and the two examples `../gemini/examples/quickstart.py` and `../gemini/examples/hackathon.py`, which show the full path: `Case.from_json` → plant → `study.size` → `simulate` → `evaluate.report` → `study.minimize` → `evaluate.compare`.

## 2. Section A: the case in the problem state and the workspace (phase 2, one worker)

Owns: `geomind/context/` (`brief.py` removed, `state.py`, `__init__.py`), `geomind/stores/` (`workspace.py`), `geomind/testing/` (workspace conformance), `geomind/tools/gemini/brief.py` (becomes `case.py`), `geomind/tools/state.py` if the patch rules live there, `geomind/schemas/` (regenerated), their tests.

1. `ProblemState.case: dict | None`, holding `gm.Case.to_dict()`. The state stays frozen and JSON. `case` is a key a patch may change, as `brief` was. A state with a case that `gm.Case.from_dict` rejects is refused with gemini's error message and path.
2. Where the demand file lives. `gm.Case.from_dict(data, folder)` reads `demand.file` relative to `folder`. Give the run one case folder:
   - `Workspace` gets a new protocol method `case(project_id) -> (dict, folder)` (or a better shape you justify), so the backend can hand over a project's `case.json` and demand CSV. `MemoryWorkspace` and `FileWorkspace` implement it; `geomind/testing` conformance checks it.
   - A demand profile the user gives (`save_profile`) is written as a CSV into the run's case folder through gemini (`gm.data.from_values` / `gm.data.from_csv` to read and check it, then a CSV in the same columns and units the case names), and the case's `demand` section is patched to point at it.
   - If a clean general design needs gemini to accept an in-memory demand (a DataFrame or `gm.data` profile) instead of a file, do not set gemini's hidden `frame` field: write the request to `gemini-requests.md` and keep the file route.
3. One helper loads the case of a run: `case_of(context) -> gm.Case`, from the state's `case` and the run's case folder. When the state has no case, it raises a `ToolError` that tells the model to call `set_case` or `ask_user`. There is no fallback case.
4. `set_brief` becomes `set_case(source=None, changes=None)`: `source` names a case of the project (through the workspace) or a stored case; `changes` is a JSON-merge patch on the case dict. The result is validated by `gm.Case.from_dict` and stored on the state; a rejected case comes back as a tool result with gemini's path and message, so the model can fix it. Also a read tool `read_case(section=None)` that returns the case dict (or one section) with `gm.Case.schema()` available as its schema, and `missing_case` that lists what the case lacks for the asked job if gemini exposes it (otherwise a gemini request).
5. Remove `Brief`, its records, `PRESETS`, `preset`, `with_changes` and every import of them. No alias.
6. Tests: state round-trip with a case; patch of `case`; a rejected case; both example cases load through the workspace; `save_profile` on a 30-day user profile produces a case that `gm.Case.from_dict` accepts.

## 3. Section B: plant tools (phase 3, one worker)

Owns: `geomind/tools/gemini/plants.py`, `geomind/tools/gemini/catalogue.py`, their tests.

1. `list_plants`: `gm.plants.names()` with each plant's summary, plus `gm.plants.capabilities()` (what each plant can serve).
2. `read_plant(design=None)`: the run's design, a stored design (`design/<name>`), or a gemini plant class by name (`gm.plants.get(name)`), returned as `to_dict(structure=True)` plus `missing_parameters()` (path, quantity, unit, units, bounds, description). Remove `example/` and `template/` sources (`gm.plants.example` and `from_template` are gone with no alias). A plant class with missing parameters is a valid answer: the model fills them.
3. `build_plant(plant, name)`: input schema `gm.plants.schema()`; check with `gm.plants.validate(plant)` and return validation errors as tool results (path + did-you-mean); store with `gm.Plant.from_dict`.
4. The input bridge `apply_inputs`: gemini's `Plant.set_inputs` is public and `to_dict` stores the inputs. Check whether `Plant.from_dict` restores them. If yes, delete `apply_inputs`, the bridge section of `tools.md` and the related tests. If no, keep one call to the public `Plant.set_inputs` with Quantities and write a gemini request.
5. `list_modules`, `describe_module`, `evaluate_module`: keep `gm.modules.names/get` and `Module.describe()`; `evaluate_module` calls `gm.call` with Quantities and `units=` for readable outputs.
6. Tests on both example cases' plants (`../gemini/inputs/examples/hackathon_2026/plants/*.json`, `../gemini/inputs/examples/shallow_district/plant.json`).

## 4. Section C: run tools (phase 3, one worker)

Owns: `geomind/tools/gemini/runs.py`, `geomind/tools/gemini/results.py`, their tests.

1. `simulate(design, ...)`: `gm.simulate(plant, case)` with the case from `case_of`, plan from `gm.schedule(plant, case)` where the tool needs to expose it. No geomind schedule rules, `ORDER` or `SCHEDULE_RULES`: the schedule comes from gemini and the case.
2. `list_profiles` / `read_profile`: the demand of the case (`case.demand.frame`, services, units), read through public names only; a window by `start`/`end`; values in the case's units.
3. `save_profile`: as in section A (A owns the case folder helper; C calls it).
4. `read_result`: `gm.Results.from_bytes`, `get`, `summary`, `to_dict(units=...)`; readable units, never bare SI in what the model reads.
5. Tests: simulate on both cases; a 30-day user profile simulates; a case without demand gives the `set_case`/`ask_user` tool error.

## 5. Section D: assessment and verification (phase 3, one worker)

Owns: `geomind/tools/gemini/assessment.py` (minus the study tools of section E), `geomind/tools/gemini/verification.py`, `geomind/verify/`, their tests.

1. `check_results(reference)`: `gm.evaluate.report(plant, case, results).to_dict()` (passed, constraint results, failures by module and code, balances) plus `gm.evaluate.failures(results)`. The `limits` argument is removed: a limit is a case constraint, set with `set_case`.
2. `compute_kpis(reference, names=None)`: `gm.evaluate.totals` and the report's metrics, in display units.
3. `estimate_costs(reference)`: `gm.evaluate.capex`, `opex`, `lcoh`, `lcoc`, `lcts`, `npv`, `payback`, `co2`, `annualised_cost` from the case's `assumptions`. The `assumptions` argument is removed: assumptions are part of the case, changed with `set_case`. Missing assumptions come back as gemini's error, never filled.
4. `verify(plant, results, case)` (the `gd.verify` function and the `verify_design` path): pass/fail = gemini's report; `failures` routed by domain for the DesignLoop. Delete `verification.py`'s own limit building, `TOLERANCE`, `RESERVOIR`, `challenge_limits`, `doublet_limits`, `grid_limits`, `reservoir_checks`, `operating_days_reason`, `not_assessed`, `not_given`. Keep only what is agent work: mapping a failure to the domain/agent that should fix it.
5. Rules geomind checked that gemini's report does not cover (the design "may not burn the co-produced gas", "ran on the case's demand and schedule"): if a `gm.case.Constraint` (role, quantity, min/max/equals, over, when) can express it, express it as case data in the eval cases, not code. If it cannot, write a gemini request and keep, at most, a thin geomind check that is clearly named as a geomind process rule (not physics). Report which.
6. `ProblemState.requirements`: a numeric requirement (`metric`, `target`, `tolerance`) becomes a case constraint through `set_case`; `Requirement` stays as the user's text with a link to the constraint. Remove `requirement_limits` if nothing else needs it.
7. Tests: the hackathon design passes on its case; the same design fails under the colder-reservoir variant and the 15 MW cooling variant (section G), with gemini's failure reasons.

## 6. Section E: study tools (phase 3, one worker)

Owns: the study tools (move `optimize` and `sample_uncertainty` out of `assessment.py` into `geomind/tools/gemini/study.py`), `geomind/tools/gemini/__init__.py` registrations of the new tools, their tests.

1. `size_plant(design, backup)`: `gm.study.size(plant, case, backup=...)`, `backup` required (`"peak"` or `"none"`), returns the sized plant dict and `plant.sizing` notes; stores the result as a new design.
2. `optimize(design, objective, variables, evaluations, constraints=None)`: `gm.study.minimize`; `variables` as gemini takes them (`role.param` paths or the case's `choices`); every argument the model must choose is required; result `Best.to_dict()` (includes the plant), stored as a design.
3. `sample_uncertainty(design, metrics, count, seed)`: `gm.study.sample`; distributions come from the case's `uncertainty`, never from the tool. Summary with the `failed` count.
4. `sensitivity(design, metrics)`: `gm.study.sensitivity`, bounds from the case's uncertainty.
5. `compare(references, by)`: `gm.evaluate.compare` over stored reports; values as gemini returns them (Quantity → `to_dict()`).
6. Tests on the shallow case (fast) and one hackathon smoke test with a tiny `evaluations` count; keep each fast test under 1 s or mark it slow.

## 7. Section F: agents, prompts, skills, loops (phase 4, one worker)

Owns: `geomind/agents/`, `geomind/prompts/` (all `.md`, including skills and the `hackathon-2027` note), `geomind/loops/`, their tests.

1. Every prompt and skill uses the new tool names and arguments, talks about "the case" instead of "the brief", and names no gemini function that no longer exists. The `hackathon-2027` note leaves the package (its content is eval data now) or is reduced to a general note with no numbers.
2. Designer: start from `missing_parameters` of a plant class or a stored plant, `size_plant`, `simulate`, and its own `check_results` as a quick self-check. Then `optimize` directly: `gm.study.minimize` already counts only trials that pass every case constraint as feasible, so no Verifier round is needed before it. If `optimize` returns `feasible: False`, the Designer changes the topology or the variables and tries again, still without the Verifier. Verifier: `check_results` only, once, on the Designer's final design (the independent checker of a maker-checker pair). Economist: `estimate_costs`, `compare` (the sized start vs the optimised design, and alternative topologies), `sample_uncertainty`, `sensitivity`. Explainer: reads reports in display units.
3. DesignLoop order: Designer (size, simulate, self-check, optimize) → Verifier on the final design → Economist → Explainer. Only a Verifier failure sends the design back to the Designer, with gemini's failure codes and constraint roles routed by domain. When the state has no case, or the case lacks demand, ask the user (`ask_user`) before designing. Update the loop's tests and the recordings (section G) to this order.
4. The Analyst answers questions over the case and results; the Coordinator routes as before.
5. The designing-a-plant skill stays general and names no answer; the evals keep saying that the base design was found by hand.

## 8. Section G: evals, fixtures, examples (phase 4, one worker)

Owns: `evals/`, `tests/fixtures/`, `examples/`, the e2e tests.

1. Eval cases as data: copy gemini's two example cases (case.json + demand CSV + plants) into `evals/projects/` (or point at `../gemini/inputs/examples/` if the eval runner can take a path; decide and justify). The challenge2 variants become case variants: the hackathon case, a 15 MW cooling peak (scaled demand CSV), a 25 K/km gradient, and a 30-day user profile.
2. Re-write the hand-written recordings to the new tool names and arguments. The numbers in tool results must come from real gemini runs (regenerate them), only the model's decisions are hand-written; each file still says so.
3. `tests/fixtures/hackathon.py`, `test_runs.py`, `test_plants.py` and every fixture that built a brief or used `from_template`/`example` now load the example cases and plants.
4. The offline end-to-end run `geomind run --loop design` passes on the hackathon case and on the shallow case.
5. `examples/`: one short example that runs a case through geomind offline.

## 9. Section H: frozen interfaces, docs, contract (phase 5, coordinator with one worker)

1. Version `0.2.0` in `geomind/__init__.py` and `pyproject.toml`; `python scripts/snapshot_api.py`; `CHANGELOG.md` lists every removed, renamed and added item (tools, state keys, `Workspace.case`, `verify(case=)`, CLI flags if any).
2. Regenerate `geomind/schemas/*.json` and samples from the models.
3. Update `.claude/docs/`: `context.md` (the case replaces the brief), `tools.md` (tool catalogue, no bridge section if removed, verification section rewritten), `api.md`, `contracts.md` (state key `case`, `Workspace.case`, tool error shapes), `evals.md`, `testing.md`, and `plan.md` (done, still open, the gemini requests).
4. Quality tests:
   - no private gemini name in `geomind/`;
   - none of the removed names anywhere in `geomind/`, prompts or docs: `gm.profiles`, `gm.kpi`, `gm.checks`, `gm.economics`, `gm.units.parse`, `from_template`, `spec_schema`, `plants.example`, `Plant.validate`, `from_legacy`, `Brief`, `set_brief`, `hackathon_2027`;
   - no hackathon number or name in `geomind/` (extend the existing generality test if there is one).

Phase order: 1 (setup, inventory) → 2 (A) → 3 (B, C, D, E in parallel) → 4 (F, G in parallel) → 5 (H) → `make test-all`, `make lint`, push `origin main`.

## 10. Done when

- geomind imports and runs on gemini `dev` with no removed gemini name left; `make test-all` and `make lint` pass (CPU-load-only 1 s failures reported, not hidden).
- The offline design loop passes on both example cases, and the hackathon design is rejected under the colder-reservoir and 15 MW cooling variants for gemini's reasons.
- `Brief`, `verification.py`'s duplicated checks and every geomind default for an engineering assumption are gone.
- Docs, schemas, snapshots, changelog are updated; version `0.2.0`; pushed to `origin main`.

## 11. Final report (short, in this order)

1. Commits, one line each.
2. Tests and lint results, with any test that only fails under load.
3. Tool catalogue: old → new (renamed, removed, added).
4. For Sahand (backend): the state key `case` replaces `brief`; the new `Workspace.case` method and what the backend must store (the project's `case.json` and demand CSV); artifact keys that changed.
5. gemini requests (`.tmp/adapt/gemini-requests.md`), one line each, with why.
6. geomind process rules kept as code (section D.5) and why gemini cannot express them.
7. What is still open: the live run (needs `OPENROUTER_API_KEY` in geomind's environment and a spending cap), MakerCheckerLoop and CompareLoop stubs, `test_module` (Docker), anything you could not finish.

## Appendix: old → new gemini API (gemini `dev` cca153b)

| geomind uses (old) | gemini `dev` (new) |
| --- | --- |
| `gm.profiles.get`, `gm.profiles.names` | gone; demand comes from the case: `gm.Case.from_json(...)` (`demand.file`, `time_column`, services `heating`/`cooling` with `column`, `unit`, `supply_temperature`, `return_temperature`), or `gm.data.from_csv(path, columns, unit, time_column)` / `gm.data.from_values(values, unit, start, step, quantity)` |
| `gm.kpi.totals`, `gm.kpi.compute` | `gm.evaluate.totals(plant, case, results)`, `gm.evaluate.report(plant, case, results)` |
| `gm.checks.Limits`, `gm.checks.limits`, `Limits.to_dict/from_dict` | constraints live in the case: `gm.case.Constraint` (`on` role, `quantity`, `min`/`max`/`equals`, `over` each/duration, `when` running); checked by `gm.evaluate.constraints(plant, case, results)` |
| `gm.checks.run_all`, `gm.checks.plant_balance` | `gm.evaluate.run_all`, `gm.evaluate.plant_balance` (both `(plant, case, results)`) |
| `gm.economics.Assumptions` (+ `model_fields`) | `gm.case.Assumptions` inside the case (`assumptions.finance`: currency, discount_rate, lifetime, price_year, capex, opex, revenue; `assumptions.emissions`), no defaults |
| `gm.economics.lcoh`, `gm.economics.lcoc` | `gm.evaluate.lcoh`, `lcoc`, `lcts`, `npv`, `capex`, `opex`, `co2`, `payback`, `annualised_cost` (all take `plant, case, results`) |
| `gm.plants.from_dict` | `gm.Plant.from_dict` / `gm.Plant.from_json` (and `to_dict(structure=...)` / `to_json`) |
| `gm.plants.from_template` | gone; plant classes (`gm.plants.HeatingCoolingPlant`, ...; `gm.plants.get(name)`, `gm.plants.names(category)`) or stored plant JSON |
| `gm.plants.spec_schema` | `gm.plants.schema()` |
| `gm.plants.example` | removed; `gm.Plant.from_json(...)`, or a plant class plus `plant.missing_parameters()` (path, type, quantity, unit, units, minimum, maximum, enum, description) |
| `gm.units.parse` | gone; `gm.units.Quantity(value, unit)` with `gm.units.Unit`; unit strings like `"2500 m"` are rejected; `gm.units.convert(value, from_unit, to_unit, quantity)`, `fits`, `names` remain |
| `gm.schedule(...)`, `gm.simulate(...)` | `gm.schedule(plant, case)`, `gm.simulate(plant, case, plan=None, ...)` |
| `Plant.validate()` | removed; `gm.plants.validate(plant.to_dict(structure=True))` (without `structure=True` the dict can leave out connections) |
| `Plant.from_legacy`, `gm.data` legacy readers | removed, no alias |
| `gm.data.synthesize`, `gm.analysis.injectivity`, `calibrate_pump`, `calibrate_corrosion`, `erosion` | removed (planned in gemini) |
| well `pipe_path` in a plant dict | `section_length`, `section_inclination`, `section_diameter`, `section_roughness` |
| `report.to_dict()` in SI | display units by default (LCTS EUR/MWh, CO2 kt, ...), or `to_dict(units={metric: unit})` |
| `Comparison` values as floats | `Quantity` |
| (new) | `gm.Case.from_json(path)`, `Case.from_dict(data, folder)`, `to_dict`, `to_json`, `Case.schema()`; case sections `time`, `environment` (ground, reservoir, fluid, air), `demand`, `choices` (e.g. doublets min/max, depth min/max), `constraints`, `assumptions`, `uncertainty` declared next to a value (`{"kind": uniform/triangular/normal, ...}`) |
| (new) | `gm.study.size(plant, case, backup)` (`"peak"` or `"none"`, notes in `plant.sizing`); `gm.study.minimize(plant, case, objective, variables, constraints, evaluations, plan)`; `gm.study.sample(plant, case, metrics, count, seed, plan)`; `gm.study.sensitivity(plant, case, metrics, plan)`; `gm.evaluate.compare(reports, by)`; `gm.evaluate.failures(results)`; `gm.plants.capabilities()` |
| (new) | a trial with failed steps is infeasible with metrics `None` and a reason; every study, compare and report result has `to_dict()` that passes `json.dumps`; `Best.to_dict()` includes the plant dict |
| (new) | `gm.runtime.settings(...)` context settings (check gemini's docs for the parallel-trials option before using it) |

Still the same: `gm.modules.get/names`, `Module.describe()`, `gm.plants.validate/names/get`, `gm.errors.*`, `gm.units.convert/fits`, `gm.Results.from_bytes`, `gm.__version__`. `Plant.set_inputs(values)` and `Plant.input_value(path)` are public (values: number in SI or a quantity, never a unit string; `to_dict` stores them).

Example of the full gemini path (read `../gemini/examples/hackathon.py` for the real one):

```python
import gemini as gm

case = gm.Case.from_json("inputs/examples/hackathon_2026/case.json")
plant = gm.Plant.from_json("inputs/examples/hackathon_2026/plants/HeatingCoolingPlant.json")
sized = gm.study.size(plant, case, backup="peak")
results = gm.simulate(sized, case)
report = gm.evaluate.report(sized, case, results)
print(report.to_dict())
```

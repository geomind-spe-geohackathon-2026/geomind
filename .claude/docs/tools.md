# Tools

The primitive actions of an agent, in `geomind/tools/`. Tool names are stable identifiers: a change
is a new version.

## Catalogue

Every tool exists now as a real `Tool`, except `test_module` (a stub, which needs Docker). Names, schemas and effects are
[frozen](api.md#frozen-interfaces). A **stub** raises `NotImplementedYet("<tool> comes in <phase>")`,
so a call is an error result with `code: "not_implemented"`. `gd.tools.gemini.<name>` is the public
path; the package has one file per group. All are idempotent except `set_case` and `save_profile`, which write
the problem state as `update_state` does.

| Tool | File | Effect | Inputs | Returns | Status |
|---|---|---|---|---|---|
| `list_modules` | `catalogue.py` | `read` | `category=None` | `[{name, category, summary}]` | built |
| `describe_module` | `catalogue.py` | `read` | `name` | gemini's module description | built |
| `evaluate_module` | `catalogue.py` | `compute` | `name, parameters, inlets=None, controls=None, state=None, dt=None` | `gm.call(..., units="display")` result (`outlets`, `outputs`, `state`, `errors`) as `{value, unit}` in gemini's display units (MW, degC, m3/h; no geomind unit map); values with a dimension go in as `{value, unit}`, never text; every inlet needs `fluid` (gemini's error otherwise); a module with state needs `state` and `dt` | built |
| `list_plants` | `plants.py` | `read` | none | `{plants: [{name, summary}], capabilities, roles}`; `capabilities` is `gm.plants.capabilities()` (roles, schedulable and `ranges`, the leaves that may state a search range of each class), `roles` is `gm.plants.roles()` | built |
| `read_plant` | `plants.py` | `read` | `design=None, plant_class=None`: neither is the project's plant from `Workspace.plant` (several plant files: a `ToolError` naming them and pointing to a plant class or a stored design), `design/<name>` a stored design, `plant_class` a class name (`gm.plants.get`); both is refused | `{plant, ranges, options, issues, checked_against}`: `plant.to_dict(structure=True)`, `ranges` as `{path: {min, max}}` with `{value, unit}` in display units (plain numbers for a count), `options`, and `issues` (`path, code, message, suggestions, kind, quantity, accepted`) from `gm.check(plant, case)` when the state has a case (`checked_against` `case`) else from `plant.check()` (`plant`), which lists as missing what the case fills (`d0.gradient`); a class lists everything it needs as missing | built |
| `build_plant` | `plants.py` | `write` | `plant` (input schema: `gm.plants.schema()`), `name` | `{design, checked_against, issues}` as `read_plant`; `gm.Plant.from_dict` is stored by `stored.save_design`; a file gemini cannot read raises gemini's `ValidationError` (path, code, message, suggestions) and stores nothing, a file with missing values is stored with its issues | built |
| `set_ranges` | `plants.py` | `write` | `design, ranges, name, options=None`: `ranges` is `{path: {min, max}}` with `{value, unit}` bounds (plain numbers for a count such as `size.doublets`); a path is the plant-file leaf without `params.` (`depth`, `heat_pump.capacity`, `d0.nominal_flow`) | `{design, plant, ranges, options}` as `read_plant`; `plant.set_range` and `plant.set_options` on a copy of the design, stored as `design/<name>`; an unknown path or a refused bound is gemini's error with its path | built (to be registered) |
| `set_case` | `case.py` | `write` | `source=None, changes=None, requirements=None, economics=None`: `source` is `project`, `origin` (the case the user gave, with its files) or none (the state's case); `changes` an RFC 7386 merge patch on the case, without `requirements` and `economics`; `requirements` `{name: requirement or null}` (add, replace or remove by name); `economics` a merge patch on the content of the economics file | `{case, version}`; the state's `case` replaced and its files kept as `case/<file name>`; the project's case or the first case of a chat also becomes `case_origin`; a case `gm.Case.from_dict` or `Case.check` rejects is an error with gemini's `path`, `code` and message and nothing is stored | built |
| `case_changes` | `origin.py` | `read` | none | `[{path, change, given, now}]`: every difference of the state's case from `case_origin` (`changed`, `removed`, `added`; a section key, `requirements.<name>`, `file <name>` for a file's content, the economics file included); `[]` when it is the case the user gave | built |
| `accept_case` | `origin.py` | `write` | none | `{version}`; `case_origin` becomes the state's case. Only the design loop's driver holds it, after the user approved the change | built |
| `read_case` | `case.py` | `read` | `section=None`: a key of the case, `economics` or `schema` | the case, the section, the parsed economics file, or `gm.Case.schema()` with `economics_schema`; no case is `invalid_input` | built |
| `list_profiles` | `runs.py` | `read` | none | `[{service, power, supply_temperature, return_temperature, start, end, steps, peak}]`: the heating and cooling demand of the state's case, `power` the `{unit, file, column}` its series names, temperatures in degC and the peak in MW | built |
| `read_profile` | `runs.py` | `read` | `service` (`heating` or `cooling`), `start=None`, `end=None` (ISO 8601, inclusive) | `{service, time, value, unit}` of the case's demand in MW | built |
| `save_profile` | `case.py` | `write` | `name, values, unit, start, step, service`, all required: `unit` a unit of power, `step` `{value, unit}`, `service` `heating` or `cooling` | `{demand, time, steps, version}`; gemini checks the values (`gm.case.from_values`), they are written in `unit` as the column `name` of `data/<name>.csv` (first column `time`) in the run's case files and the service's `power` becomes `{unit, file, column}`; a profile that does not cover the case's `time` sets it to the profile's span in the same call; gemini rejects a case that does not fit and nothing is stored | built |
| `simulate` | `runs.py` | `compute` | `design=None, changes=None, start=None, end=None` | `{reference, summary}`; the run is stored; the summary gives the plant, the case's time span, the window, `steps`, `failed_steps` and the first `failures`, the `report` totals in display units, gemini's `verdict`, the `unmet` requirements (the checks with `passed` false) and the demand `coverage` | built |
| `read_result` | `results.py` | `read` | `reference, path=None, field=None, start=None, end=None` (ISO 8601, inclusive) | `{time, value, unit}` with `path` and `field`, otherwise `{path: {field: {min, max, mean}}}`, in MW, degC, bar, m3/h and kg/s | built |
| `search_documents` | `results.py` | `read` | `query` | `[{id, title, text, score}]` | built |
| `check_results` | `assessment.py` | `compute` | `reference` | gemini's verdict on the run's own case, in display units: `{feasible, reasons: [{kind, name, message, ...}], requirements: [check], failures: {total, groups}, metrics}` | built |
| `compute_kpis` | `assessment.py` | `compute` | `reference, names=None` | `{name: Value}` in display units: `gm.evaluate.totals` and the metrics of `gm.evaluate.report`; an unknown name is `unknown_name` with a did-you-mean | built |
| `estimate_costs` | `assessment.py` | `compute` | `reference` | `{capex, opex, annualised_cost, lcoh, lcoc, lcts, npv, payback, co2}` as Values in display units, from the case's `economics.json`; a cost whose figure is missing is `{error}` with gemini's `missing_assumption` and its path | built |
| `test_module` | `assessment.py` | `execute` | `path` | gemini's `check_module` report, run in the sandbox | stub, S3 |
| `size_plant` | `study.py` | `compute` | `design, name`: the backup policy is the plant's `params.backup` (the Designer sets it and records the assumption) | `{design, sizing}`; `gm.study.size` on the state's case, the sized plant stored as `design/<name>`, `sizing` gemini's notes (`sized`, `unchanged`, `broken`, `simulation`) with quantities as `{value, unit}` | built |
| `optimize` | `study.py` | `compute` | `design, objective, evaluations, seed, name`, all required: the variables are the design's ranges and options (`set_ranges`), the constraints the case's requirements; a design with none is gemini's error | `{best, feasible, trials, design}`; `best` is `Best.to_dict()` (display units, the plant inside), the best plant stored as `design/<name>`; with no trial that ran there is no `design`; gemini's errors pass through | built |
| `sample_uncertainty` | `study.py` | `compute` | `design, metrics, samples, seed`, all required | `Sample.to_dict()`: `samples` and `summary` per metric (`mean`, `p5`, `p50`, `p95`, `failed`); distributions only from the case's `uncertainty` (none is `missing_value`) | built |
| `sensitivity` | `study.py` | `compute` | `design, metrics` | `Tornado.to_dict()`: `rows` sorted by effect, bounds from the case's `uncertainty` | built |
| `compare` | `study.py` | `compute` | `references, by`: references of runs `simulate` returned | one entry per reference: `reference`, `values` in display units (read from each run's `Report.to_dict()`, since `Comparison.to_dict()` is SI), `ranks`, `pareto`, `feasible`, `reasons` | built |
| `run_study` | `study.py` | `compute` | `designs, method, objective=None, metrics=None, evaluations=None, seed=None, samples=None, prepare=None`: a `gm.Study` over the state's case and the stored designs; a setting the method needs and the call leaves out is gemini's error | `{runs, best}`: per design `plant_name`, `feasible`, `verdict`, `metrics` (display units), `ranks`, `pareto`, `note`, `found`, and the `design` the run ended with (sized or best plant) stored as `design/<plant>_best`; `best` the feasible design ranked first by the objective | built |

### gemini mapping

Every name is public in `gemini/.claude/docs/api.md` at `gm.__version__ = "0.2.0"`. Check again before
filling a stub, because gemini's names change.

| Tool | gemini public names | Status |
|---|---|---|
| `list_modules` | `gm.modules.names(category)`, `gm.modules.get(name).describe()` | real |
| `describe_module` | `gm.modules.get(name).describe()` | real |
| `evaluate_module` | `gm.modules.get`, `gm.call(..., units="display", state=, dt=)` | real |
| `list_plants` | `gm.plants.names`, `gm.plants.get(name).describe()`, `gm.plants.capabilities`, `gm.plants.roles` | real |
| `read_plant` | `stored.load_design`, `gm.plants.get`, `plant.to_dict`, `plant.ranges`, `plant.options`, `plant.check`, `gm.check`, `gm.units.display` | real |
| `build_plant` | `gm.plants.schema`, `gm.Plant.from_dict`, `plant.check`, `gm.check` | real |
| `set_ranges` | `stored.load_design`, `plant.set_range`, `plant.set_options`, `plant.ranges` | real |
| `set_case` | `gm.Case.from_dict`, `Case.check` | real |
| `read_case` | `gm.Case.schema`, `gm.case.Economics.schema` | real |
| `list_profiles` | `gm.Case` (`case.demand.<service>`, `case.to_dict()`), `gm.units.Quantity` | real |
| `read_profile` | `gm.Case` (`case.demand.frame`), `gm.units.convert` | real |
| `save_profile` | `gm.case.from_values`, `gm.units.Quantity`, `gm.Case.from_dict`, `Case.check` | real |
| `simulate` | `gm.schedule`, `gm.simulate` (which runs `gm.check`), `gm.evaluate.report`, `totals`, `failures`, `plant.set_params`, `Results.to_bytes` | real |
| `read_result` | `Results.get`, `Results.summary` through `load_run` | real |
| `search_documents` | none: it reads `Workspace.documents` | built |
| `check_results` | `gm.evaluate.verdict`, `report`, `gm.Results.from_bytes` | real |
| `compute_kpis` | `gm.evaluate.totals`, `gm.evaluate.report` | real |
| `estimate_costs` | `gm.evaluate.capex`, `opex`, `annualised_cost`, `lcoh`, `lcoc`, `lcts`, `npv`, `payback`, `co2`, `report` | real |
| `test_module` | `gm.modules.load_file`, `gm.modules.get`, `gm.testing.check_module` | real |
| `size_plant` | `gm.study.size`, `Plant.sizing`, `Plant.to_dict` | real |
| `optimize` | `gm.study.minimize`, `Best.to_dict` | real |
| `sample_uncertainty` | `gm.study.sample`, `Sample.to_dict` | real |
| `sensitivity` | `gm.study.sensitivity`, `Tornado.to_dict` | real |
| `compare` | `gm.evaluate.report`, `gm.evaluate.compare`, `Report.to_dict` (display units) | real |
| `run_study` | `gm.Study.from_dict`, `Study.run`, `StudyResult.to_dict`, `Run.report` | real |

`size_plant`, `optimize`, `sample_uncertainty`, `sensitivity` and `run_study` have a time limit of
`STUDY_TIMEOUT_S` (900 s): past it the model reads a `timeout` error and asks for fewer
evaluations or draws. The gemini call runs in a worker thread, which Python cannot stop, so it
finishes in the background and its result is dropped.

## References

Both formats are frozen. Each is a key of `RunStore.save_artifact(run_id, key, data)`, so a store must
accept the `/`; `check_run_store` tests it. An artifact belongs to its root run.

- **A design** is a stored, validated plant dict, `gm.Plant.to_dict(structure=True)`, which keeps
  the plant's inputs and which `gm.Plant.from_dict` restores. `load_plant(context, design, where)` in
  `plants.py` is the one function that returns a `gm.Plant` (`None` is the project's plant). `build_plant` saves it under `design/<name>` and
  returns that text. `<name>` is letters, digits, `.`, `_` or `-`.
- **A result** is a run `result/<id>`: the summary `simulate` returned, with `<id>.results`
  (`Results.to_bytes()`), `<id>.plant`, `<id>.case` and `<id>.files` (`{file name: sha256}`)
  beside it, written by `save_run` in `stored.py`. Each case file is also kept once by its content
  as `<sha256>.file`, so a later `save_profile` that overwrites `case/<file name>` never changes
  what an older run reads. `ran_case(context)` reads the state's case and its files once; the run
  is built from that copy and `save_run` stores the same copy, so a `set_case` in a parallel call
  cannot change what a run stores. `<id>` is a hash of the plant, the case, the files' contents
  and the window, so the same run has the same reference. `read_result` loads it with `load_run`
  and reads `Results.get` and `summary`.
- **A case file** is stored under `case/<file name>` as bytes (a series CSV, a profile or
  `economics.json`); the name is a relative path such as `data/demand.csv`. `set_case` and
  `save_profile` write them;
  `case_of` reads them; `list_profiles`, `read_profile` and `simulate` read the case.

`geomind/tools/gemini/stored.py` is the one contract of both: `save_design(context, name, plant)
-> "design/<name>"`, `load_design(context, design, where) -> gm.Plant`, `save_run(context, plant,
results, summary, options, ran) -> "result/<id>"` and `load_run(context, reference, where) -> (plant,
case, results)`. `<id>` also covers the contents of the case's files, so a changed file is a new
run. A reference no run made is `unknown_name` with `path` `reference`.

### How `simulate` runs

The plant is `load_plant` (the project's, or a stored `design/<name>`), `changes` set on it with
`plant.set_params` as `{"value", "unit"}` (a bare number is refused for a parameter with a unit),
the case is `case_of(context)`, then `gm.simulate(plant, case)`: the plan is
`gm.schedule(plant, case)`, which belongs to gemini and the case. A window `start`, `end` cuts that
plan (`gm.simulate(..., plan=...)`) and the run's case: its `time` is cut to the window, since
gemini judges a run against the case's time, and the stored run keeps that case. What `gm.check`
finds wrong (a parameter without a value, a missing capex, a role) is gemini's error with the
issues' `path` and `message`, and nothing runs. A step that fails physically is a failed row
(`failed_steps`, the first `failures`) and the run goes on. A state without a case gives the `set_case` or `ask_user` error of `case_of`. The demand is the
case's: `list_profiles` and `read_profile` read `case.demand`, and a user's profile enters the
case with `save_profile`.

## Verification

`tools/gemini/verification.py` holds the one verification, used by `check_results` and by
`gd.verify.verify(plant, results, case)` (`verify/` may import `tools`, not the other way). Pass
or fail is `gm.evaluate.verdict(plant, case, results)` and nothing else: geomind has no rule, limit,
tolerance or brief of its own. A limit is a requirement of the case (`set_case`), and a numeric
requirement of the problem state is one too: `Requirement.case_requirement` names it by its
`name`.

- `assess` returns `{feasible, reasons, requirements, failures, metrics}`. `feasible` and `reasons`
  are the verdict's (a reason has a `kind`: `requirement`, `failed_step`, `numerical` or `bound`),
  `requirements` the report's checks (`{name, role, unit_path, quantity, passed, value, limit,
  worst_step}`), `failures` `gm.evaluate.failures(results).to_dict()`, and `metrics` the rest of the
  report, all in display units.
- `verify` returns `{passed, checks, failures: [{name, kind, domain, detail}], metrics}`: `passed`
  is `feasible`, `checks` the requirements, and each reason is routed to a domain; a `failed_step`
  reason is listed as the groups of failed rows by module and code.
- The only agent work geomind does is `domain_of`: a requirement by the `on` role (the reason's
  `role`, or the case requirement of that name): `subsurface` (`doublet`), `sizing` (`heating_supply`
  or `cooling_supply`: the topology works, the sizes do not), `surface` (any other role). A failed
  step or a bound goes by the role of the unit its `path` lies in (found from the `unit_path` of the
  report's checks); `numerical`, or a path in no unit of a known role, is `coupled`.
- `verify_design` loads the run with `load_run` (plant, case, results) and adds two geomind
  process rules, not physics: a result whose plant is not the design's is `stale_result`, and one
  that ran on another case than the problem state's (the case dicts differ) is `result_off_case`.
  A missing or unknown result is `verification_missing` or `result_unknown`; all are `coupled`.
- What the case does not require, gemini does not judge.

## Costs

`estimate_costs` calls `gm.evaluate.capex`, `opex`, `annualised_cost`, `lcoh`, `lcoc`, `lcts`,
`npv`, `payback` and `co2` on the run's plant and case and shows them in display units (MEUR,
MEUR/yr, EUR/MWh, kt, yr) through a gemini `Report` of the values. Prices, discount rate, analysis
period and cost factors are the case's `economics.json`; geomind passes none and fills none. A cost
whose figure is missing is `{"error": {path, code: "missing_assumption", message}}` beside the
others, and a case from which no cost can be computed fails the call with gemini's error. The
agent asks the user or sets it in the case's economics.

## Tool

`Tool(name, description, input_schema, function, *, effect, idempotent=True, timeout=None,
max_retries=2, input_model=None, runs_alone=False, reruns_in_replay=False, late_schemas=None)`. `@gd.tool(effect=...)` builds one from a typed function: the
schema comes from the signature through Pydantic and the description from the docstring.

| `effect` | Means | Runs in ask mode |
|---|---|---|
| `read` | reads, changes nothing | without asking |
| `compute` | calculates, changes nothing | without asking |
| `write` | writes inside the run | after approval |
| `execute` | runs sandbox code | after approval |
| `external` | network or anything outside the run | after approval |

`idempotent` says a call may run again after a crash. `is_pure` (`read` or `compute`) says a call
may run beside others and again in a replay. `reruns_in_replay` says a tool that is not pure runs
again in a replay too, because all it changes is the run's own log. `Tool` is shaped like a protocol, so toolsets from
other sources (MCP later) fit: without `input_model`, only the required and known names of
`input_schema` are checked. An agent names a tool by its attribute, on its own copy.
`late_schemas` maps an input to a function that returns its schema when the tool is offered:
`build_plant` gets `gm.plants.schema()` that way, so `import geomind` stays free of gemini.

## Dispatch

`await dispatch(tool, call, context)` is one of the two places with side effects. It validates the input,
runs the function with the tool's timeout, times it and returns a `ToolResult`, or the `Request` or
`Finish` the tool returned. A sync function runs in a worker thread.

A function that needs the run declares a first parameter named `context`, and `dispatch` passes it:
`context.session` is the session of the run. The schema never shows it, and plain tools stay plain
functions.

- A validation error, an `gd.errors` or `gemini.errors` class, or a timeout becomes an
  [error result](#error-results) with `is_error`, so the model can fix its call. gemini errors are
  recognised by module path, so `import geomind` need not import gemini.
- After `max_retries` validation failures of one tool in a row, the engine stops the run with
  `stop_reason="error"`.
- Any other exception is a bug: it is reported through `on_error`, and the model reads only
  `internal error`, with `code: "internal"`.
- A result over `tool_result_limit` is saved with `store.save_artifact` and returned as
  `{reference, summary}`. The key is a hash, so a call id from a model never becomes a path.
- A sync tool that times out keeps running in its thread until it returns; a thread cannot be
  stopped from outside.

### Error results

An error result has gemini's Problem shape, `{"error": {path, code, message, suggestions}}`
(`geomind/types/problems.py`, schema `geomind/schemas/tool_error.json`).

A gemini error passes through its own `to_dict()` unchanged, with its code from `gm.errors.CODES`.
A validation error takes `path` from the first input field that failed. Every other error takes
`code` from this fixed list, and `path` is the input field at fault or `null`:

| `code` | Means |
|---|---|
| `invalid_input` | the input does not fit, or a `gd.errors` class says the call was wrong |
| `unknown_name` | a name that does not exist, such as a tool, a skill or a result path |
| `not_implemented` | the capability has its final signature and is not built yet; do not retry |
| `not_allowed` | the run cannot do this: no sandbox, no project, or a path outside the sandbox |
| `timeout` | the tool passed its time limit |
| `internal` | a bug or a crash; the detail is in the log, never in the result |

A permission denial is no error class: its result is the reason as text, with `is_error` set and
`source="denied"`. `runlog` `tool_call.error` is `true` on an error result, and the Problem is in
`tool_call.output`.

## Built-ins

- `ask_user(question, options=None)` returns a `Request` of kind `question`; the engine pauses.
  `options` is a list of strings or of `{value, label}`, normalised to the latter. An answer to a
  question with options is `{"text": <value>}`, and any other text raises `RequestError`.
- `finish(answer)` ends the run, after `before_finish` hooks and output validation.

Both have effect `read`, so `ask` mode lets them through; `plan` mode runs neither.

## Problem state

`update_state(changes)` (`write`, not idempotent) applies JSON Patch operations to the problem state
and emits `state.changed`; see [context.md](context.md#problem-state). An invalid patch is an error result that
says how to fix it. A path under `/case` or `/case_origin` is `not_allowed`: only `set_case`
writes the case, after gemini validates it. The default rule of [permissions.md](permissions.md) allows it in `ask` mode.

## Skills

`read_skill(name)` (`read`) returns one skill; see [context.md](context.md#skills).

## Code tools

`run_python(code)` (`execute`, not idempotent), `write_file(path, text)` (`write`) and
`read_file(path)` (`execute`, since it needs the sandbox) act inside the run's sandbox. Without a
configured sandbox they return an error result saying so. A lost sandbox is an error result and the
next tool provisions a new one. See [sandbox.md](sandbox.md).

## Delegate

`Delegate(agent, max_summary_tokens=None)` runs the agent in a nested engine run through
`context.session`, with a clean context (the task text only), a child run id, its own sandbox and `parent` set on
every event. The model reads only the final answer, cut to the token limit at four characters per
token (default: the `delegate_summary_tokens` setting). The effect is `compute`, so delegating
needs no approval of its own: each nested tool is decided by the same permissions. It is not pure
and not idempotent: it runs alone, a replay reuses its recorded result, and after a crash it
becomes an error result. A pause in the nested run pauses the parent on the same request. Usage of
the nested run adds to the parent's.

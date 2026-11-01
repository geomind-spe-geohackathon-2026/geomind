# Tools

The primitive actions of an agent, in `geomind/tools/`. Tool names are stable identifiers: a change
is a new version.

## Catalogue

Every tool up to S4 exists now as a real `Tool`. Names, schemas and effects are
[frozen](api.md#frozen-interfaces). A **stub** raises `NotImplementedYet("<tool> comes in <phase>")`,
so a call is an error result with `code: "not_implemented"`. `gd.tools.gemini.<name>` is the public
path; the package has one file per group. All are idempotent except `set_case` and `save_profile`, which write
the problem state as `update_state` does.

| Tool | File | Effect | Inputs | Returns | Status |
|---|---|---|---|---|---|
| `list_modules` | `catalogue.py` | `read` | `category=None` | `[{name, category, summary}]` | built |
| `describe_module` | `catalogue.py` | `read` | `name` | gemini's module description | built |
| `evaluate_module` | `catalogue.py` | `compute` | `name, parameters, inlets=None, controls=None` | gemini's `gm.call` result (`outlets`, `outputs`, `errors`) as `{value, unit}` in readable units (bar, degC, kW, m3/h); values with a dimension are `{value, unit}`, never text | built |
| `list_plants` | `plants.py` | `read` | none | `{plants: [{name, summary}], capabilities}`; `capabilities` is `gm.plants.capabilities()`: roles, schedulable and choices of each class | built |
| `read_plant` | `plants.py` | `read` | `design=None`: `None` is the project's plant from `Workspace.plant`, `design/<name>` a stored design, otherwise a plant class name (`gm.plants.get`) | `{plant, missing_parameters}`: `to_dict(structure=True)` and `missing_parameters()`; a class with missing parameters is a valid answer, the model fills them | built |
| `build_plant` | `plants.py` | `write` | `plant` (input schema: `gm.plants.schema()`), `name` | `{design, problems}`; `gm.plants.validate(plant, on_error="record")` problems keep gemini's path, code and did-you-mean, and a plant with problems stores nothing; otherwise `gm.Plant.from_dict` is stored by `stored.save_design` | built |
| `set_case` | `case.py` | `write` | `source=None, changes=None`: `source` is `project` or none (the state's case); `changes` an RFC 7386 merge patch on the case | `{case, version}`; the state's `case` replaced and its files kept as `case/<file name>`; a case `gm.Case.from_dict` rejects is an error with gemini's `path`, `code` and message | built |
| `read_case` | `case.py` | `read` | `section=None`: a section of the case, or `schema` | the case, the section or `gm.Case.schema()`; no case is `invalid_input` | built |
| `list_profiles` | `runs.py` | `read` | none | `[{name, quantity, unit, start, end}]`: gemini's profiles, then those stored in the run as `profile/<name>` | built |
| `read_profile` | `runs.py` | `read` | `name, start=None, end=None` (ISO 8601); `name` is gemini's or a stored `profile/<name>` | a Value series | built |
| `save_profile` | `case.py` | `write` | `name, values, unit, start, step, service`, all required: `unit` a unit of power, `step` `{value, unit}`, `service` `heating` or `cooling` | `{demand, steps, version}`; gemini checks the values (`gm.data.from_values`), they are written in `unit` as the column `name` of `<name>.csv` in the run's case files, the other service keeps its column, and the case's `demand` points at it; steps other than the case's `time` are gemini's error | built |
| `simulate` | `runs.py` | `compute` | `design=None, changes=None, profile=None, start=None, end=None` | `{reference, summary}`; full results stored; the summary names the `brief`, `demand` and `rules` that ran | built |
| `read_result` | `results.py` | `read` | `reference, path=None, field=None, start=None, end=None` (sample positions) | a Value series with `path` and `field`, otherwise `{path: {field: {min, max, mean}}}` | built |
| `search_documents` | `results.py` | `read` | `query` | `[{id, title, text, score}]` | built |
| `check_results` | `assessment.py` | `compute` | `reference, limits=None` | `{passed, checks: [Check], failures: [{name, domain}], not_assessed, not_given, brief}` | built |
| `compute_kpis` | `assessment.py` | `compute` | `reference, names=None` | `{name: Value}`: `gm.kpi.compute` and `gm.kpi.totals` | built |
| `estimate_costs` | `assessment.py` | `compute` | `reference, assumptions=None` | `{capex, opex, lcoh, lcoc, npv, co2, lcts}` as Values, plus the assumptions used | built |
| `test_module` | `assessment.py` | `execute` | `path` | gemini's `check_module` report, run in the sandbox | stub, S3 |
| `size_plant` | `study.py` | `compute` | `design, backup, name`, all required: `backup` is `peak` or `none` | `{design, sizing}`; `gm.study.size` on the state's case, the sized plant stored as `design/<name>`, `sizing` gemini's notes (`sized`, `unchanged`, `broken`, `simulation`) with quantities as `{value, unit}` | built |
| `optimize` | `study.py` | `compute` | `design, objective, variables, evaluations, name, constraints=None`: `variables` a list of `{path, parameter, lower, upper}` with `{value, unit}` bounds (counts for `size.doublets`); an empty list means the case's choices, there is no other default | `{best, feasible, fixed, trials, design}`; `best` is `Best.to_dict()` (SI values, the plant inside), the best plant stored as `design/<name>`; with no trial that ran there is no `design`; gemini's errors (`unknown_name`, `invalid_design`, `missing_value`) pass through | built |
| `sample_uncertainty` | `study.py` | `compute` | `design, metrics, count, seed`, all required | `Sample.to_dict()`: `samples` and `summary` per metric (`mean`, `p5`, `p50`, `p95`, `failed`); distributions only from the case's `uncertainty` (none is `missing_value`) | built |
| `sensitivity` | `study.py` | `compute` | `design, metrics` | `Tornado.to_dict()`: `rows` sorted by effect, bounds from the case's `uncertainty` | built |
| `compare` | `study.py` | `compute` | `references, by`: references of runs `simulate` returned | one entry per reference: `reference`, `values` as `{value, unit}` in display units, `ranks`, `pareto`, `feasible`, `reasons` | built |

### gemini mapping

Every name is public in `gemini/.claude/docs/api.md` at `gm.__version__ = "0.2.0"`. Check again before
filling a stub, because gemini's names change.

| Tool | gemini public names | Status |
|---|---|---|
| `list_modules` | `gm.modules.names(category)`, `gm.modules.get(name).describe()` | real |
| `describe_module` | `gm.modules.get(name).describe()` | real |
| `evaluate_module` | `gm.modules.get`, `gm.call(..., units=...)` | real |
| `list_plants` | `gm.plants.names`, `gm.plants.get(name).describe()`, `gm.plants.capabilities` | real |
| `read_plant` | `stored.load_design`, `gm.plants.get`, `plant.to_dict(structure=True)`, `plant.missing_parameters()` | real |
| `build_plant` | `gm.plants.validate(plant, on_error="record")`, `gm.plants.schema`, `gm.Plant.from_dict` | real |
| `set_case` | `gm.Case.from_dict` | real |
| `read_case` | `gm.Case.schema` | real |
| `list_profiles` | `gm.profiles.names`, `gm.profiles.get` | real; `quantity` needs `attrs["quantities"]`, which `api.md` does not list |
| `read_profile` | `gm.profiles.get` | real |
| `save_profile` | `gm.data.from_values`, `gm.units.Quantity`, `gm.Case.from_dict` | real |
| `simulate` | `gm.schedule`, `gm.simulate`, `gm.plants.from_dict`, `plant.set_params`, `Results.summary`, `Results.get`, `Results.names`, `Results.to_bytes` | real |
| `read_result` | none: it reads the stored JSON | built |
| `search_documents` | none: it reads `Workspace.documents` | built |
| `check_results` | `gm.checks.run_all`, `gm.checks.limits`, `gm.checks.Limits.from_dict`, `gm.Results.from_bytes` | real |
| `compute_kpis` | `gm.kpi.compute`, `gm.kpi.totals`, `gm.Results.from_bytes` | real |
| `estimate_costs` | `gm.economics.capex`, `opex`, `lcoh`, `lcoc`, `npv`, `co2`, `gm.economics.Assumptions` | real |
| `test_module` | `gm.modules.load_file`, `gm.modules.get`, `gm.testing.check_module` | real |
| `size_plant` | `gm.study.size`, `Plant.sizing`, `Plant.to_dict` | real |
| `optimize` | `gm.study.minimize`, `Best.to_dict`, `gm.units.Quantity` | real |
| `sample_uncertainty` | `gm.study.sample`, `Sample.to_dict` | real |
| `sensitivity` | `gm.study.sensitivity`, `Tornado.to_dict` | real |
| `compare` | `gm.evaluate.report`, `gm.evaluate.compare`, `Comparison.to_frame` (for the display units) | real |

## References

Both formats are frozen. Each is a key of `RunStore.save_artifact(run_id, key, data)`, so a store must
accept the `/`; `check_run_store` tests it. An artifact belongs to its root run.

- **A design** is a stored, validated plant dict, `gm.Plant.to_dict(structure=True)`, which keeps
  the plant's inputs and which `gm.Plant.from_dict` restores. `load_plant(context, design, where)` in
  `plants.py` is the one function that returns a `gm.Plant` (`None` is the project's plant). `build_plant` saves it under `design/<name>` and
  returns that text. `<name>` is letters, digits, `.`, `_` or `-`.
- **A result** is stored under `result/<id>` as JSON: `{path: {field: {unit, values, time?}}}`.
  `values` is the list of samples, `unit` their unit, and `time`, when there is one, the list of ISO
  8601 times. `simulate` leaves `time` out: every series has the same times, which would triple the
  size, and the summary gives `start`, `end` and `steps`. `<id>` is a hash of the plant that ran,
  the profiles, the window and the schedule rules, so a replay finds the same result and a run
  under another brief never overwrites it. Beside it, `simulate` keeps
  `<id>.results` (`Results.to_bytes()`), `<id>.plant` (the spec that ran) and `<id>.run` (the
  demand, rules and window it ran on), which `verify_design` compares with the brief.
- **A case file** is stored under `case/<file name>` as bytes (the CSV of the demand or of a
  profile), one name and no folder. `set_case(source="project")` and `save_profile` write them;
  `case_of` reads them. The older `profile/<name>` artifact remains for `list_profiles` and
  `simulate` until they read the case.

### How `simulate` runs

`gm.schedule(plant, demand, rules)`, then `gm.simulate(plant, plan, on_error="record")`: a day
that fails is one of gemini's problems in the summary (`failed_steps`, the first five `errors`)
and the year still runs. The rules come from the problem state's [brief](context.md#the-case)
through `schedule_rules` in `tools/gemini/brief.py`: its `doublet_flow` and `max_brine_cooling`,
the source order `geothermal, heat_pump, boiler`, and `operating_days` `None` (gemini raises
`NotImplementedYet` for any other value). A brief without the flow range or the brine cooling is
an `invalid_input` error on `brief`, since `gm.schedule` needs both. `profile` and the brief's demand name
gemini's profiles or stored `profile/<name>` ones, which `gm.schedule` takes as any UTC frame in W.
Without `profile` the run takes the brief's demand, and a brief without one is an error that says to ask the user. A state with no
brief runs on the `hackathon_2027` preset, as before briefs were data; the summary always names
the `brief`, the `demand` and the `rules` that ran, and adds `gm.kpi.totals`.

## Verification

`tools/gemini/verification.py` holds the one verification, used by `check_results` and by
`gd.verify.verify` (`verify/` may import `tools`, not the other way). It checks the limits of the
problem state's [brief](context.md#the-case) (`check_results` and `verify_design` read it; `verify`
takes `brief=`), and without one those of the `hackathon_2027` preset, as before briefs were data.
It returns `{passed, checks, failures, not_assessed, not_given, brief}`:

- `checks` are gemini Checks, unchanged in shape: `gm.checks.run_all`, `gm.checks.plant_balance`
  and `gm.checks.limits` over the brief's limits, built for the plant's own doublets and grids:
  each doublet's `flow` within the brief's `doublet_flow` while it runs and `brine_cooling` at most
  its `max_brine_cooling`; each heating or cooling grid's `supply_in.temperature` at the brief's
  supply; and, whatever the brief gives, `unmet_demand` (heating) or `unmet_sensible` and
  `unmet_latent` (cooling) at 0 on every day. More checks count what gemini gives: `doublets`
  (the brief's range), `heating_grid` and `cooling_grid` (for the demand the brief names),
  `failed_days` (0) and `co_produced_gas_burned` (0): the base design meets the demand without the
  co-produced methane, so a degasser's `gas_out` may not feed a `GasMakeup`, `Boiler` or `CHP`;
  burning it is a separate scenario. When the brief gives reservoir values, each doublet's
  `gradient`, `surface_temperature`, `permeability` and `thickness` must equal them
  (`<doublet>.<parameter>`, subsurface); the depth is the design's choice. For the hackathon
  preset these are the checks before briefs were data, plus those reservoir checks, which the base
  design passes.
  Extra `limits` and requirements are checked beside the brief's, never instead.
- `not_given` names each limit the brief does not give (`demand`, `doublets`, `doublet_flow`,
  `max_brine_cooling`, `heating.supply`, `cooling.supply`, `operating_days`, `pump_efficiency`,
  `volume_balance`): none of them is checked, or passed. `brief` says which brief was used.
- `tools/gemini/brief.py` holds no number of a brief: it turns one into gemini's rules and SI
  amounts through `gm.units`, and holds the one numerical tolerance (`TOLERANCE`, by quantity, for
  floating-point noise only).
- `failures` names the domain of each failed check: `subsurface` (a doublet, its wells, the doublet
  count), `surface` (any other module, a supply temperature, a missing grid), `sizing` (unmet
  demand: the topology works, the sizes do not) or `coupled` (the whole plant: its balance, the
  ledger checks, failed days). The domain stays outside the Check.
- `not_assessed` lists what the brief gives and gemini cannot judge yet, never as passed:
  `operating_days` (`BLOCKED`, with gemini's `NotImplementedYet` message), `volume_balance` and
  `pump_efficiency` (`NOT_ASSESSED`, with the design's value), a return temperature (a design input
  of the grid, not an output gemini's limits check), and any requirement that names no
  `<path>.<output>`.
- A limit the run cannot judge (no column) is a check with `passed: null` and its reason, as gemini
  does; a run where every day failed is judged by `failed_days` only.

## Costs

`estimate_costs` calls `gm.economics` with `on_error="record"`, so an assumption nobody gave is a
null value with gemini's reason, and returns every field of `gm.economics.Assumptions` it used.
`heat_cost_share = "energy"` splits the cost by the heat and cold delivered (`gm.kpi.totals`).
`lcts`, the levelised cost of thermal service, is annualised total system cost / (annual heat +
annual cold). Its numbers are gemini's: with `heat_cost_share = 1`, `lcoh × energy` is the
annualised total cost `capex / A + opex`, and `energy` of `lcoh` and `lcoc` the annual heat and
cold; geomind only divides. Five cost factors have no sourced default in gemini (`pump_cost`,
`chiller_cost`, `exchanger_cost`, `flare_cost`, `makeup_cost`): an agent records the value it uses
as an unconfirmed assumption.

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
says how to fix it. The default rule of [permissions.md](permissions.md) allows it in `ask` mode.

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

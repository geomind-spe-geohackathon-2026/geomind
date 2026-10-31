# Tools

The primitive actions of an agent, in `geomind/tools/`. Tool names are stable identifiers: a change
is a new version.

## Catalogue

Every tool up to S4 exists now as a real `Tool`. Names, schemas and effects are
[frozen](api.md#frozen-interfaces). A **stub** raises `NotImplementedYet("<tool> comes in <phase>")`,
so a call is an error result with `code: "not_implemented"`. `gd.tools.gemini.<name>` is the public
path; the package has one file per group. All are idempotent.

| Tool | File | Effect | Inputs | Returns | Status |
|---|---|---|---|---|---|
| `list_modules` | `catalogue.py` | `read` | `category=None` | `[{name, category, summary}]` | built |
| `describe_module` | `catalogue.py` | `read` | `name` | gemini's module description | built |
| `evaluate_module` | `catalogue.py` | `compute` | `name, parameters, inlets=None, controls=None` | gemini's evaluate result, of Values | built |
| `list_plants` | `plants.py` | `read` | none | `[{name, summary}]` of the registered plants | built |
| `read_plant` | `plants.py` | `read` | `design=None`: `None` is the project's plant from `Workspace.plant`, otherwise a design reference | the description with current values | built |
| `build_plant` | `plants.py` | `write` | `plant` (input schema: gemini's plant schema), `name` | `{design, problems}`; a plant that fails validation returns the problems and stores nothing | built |
| `list_profiles` | `runs.py` | `read` | none | `[{name, quantity, unit, start, end}]` | built |
| `read_profile` | `runs.py` | `read` | `name, start=None, end=None` (ISO 8601) | a Value series | built |
| `simulate` | `runs.py` | `compute` | `design=None, changes=None, profile=None, start=None, end=None` | `{reference, summary}`; full results stored | built |
| `read_result` | `results.py` | `read` | `reference, path=None, field=None, start=None, end=None` (sample positions) | a Value series with `path` and `field`, otherwise `{path: {field: {min, max, mean}}}` | built |
| `search_documents` | `results.py` | `read` | `query` | `[{id, title, text, score}]` | built |
| `check_results` | `assessment.py` | `compute` | `reference, limits=None` | `{passed, checks: [Check]}` | stub, S3 |
| `compute_kpis` | `assessment.py` | `compute` | `reference, names=None` | `{name: Value}` | stub, S3 |
| `estimate_costs` | `assessment.py` | `compute` | `reference, assumptions=None` | `{capex, opex, lcoh, lcoc, npv, co2}` as Values, plus the assumptions used | stub, S3 |
| `test_module` | `assessment.py` | `execute` | `path` | gemini's `check_module` report, run in the sandbox | stub, S3 |
| `optimize` | `assessment.py` | `compute` | `design, variables, objective, constraints=None, budget=None` | `{design, objective, history}` | stub, S4 (bonus) |
| `sample_uncertainty` | `assessment.py` | `compute` | `design, distributions, samples, metrics` | `{metric: {p10, p50, p90}}` as Values | stub, S4 (bonus) |

### gemini mapping

Every name is public in `gemini/.claude/docs/api.md` at `gm.__version__ = "0.2.0"`. Check again before
filling a stub, because gemini's names change.

| Tool | gemini public names | Status |
|---|---|---|
| `list_modules` | `gm.modules.names(category)`, `gm.modules.get(name).describe()` | real |
| `describe_module` | `gm.modules.get(name).describe()` | real |
| `evaluate_module` | `gm.modules.get`, `gm.evaluate` | real |
| `list_plants` | `gm.plants.names`, `gm.plants.get(name).describe()` | real |
| `read_plant` | `gm.plants.from_dict`, `plant.describe()` | real |
| `build_plant` | `gm.plants.validate(plant, on_error="record")`, `gm.plants.spec_schema` | real |
| `list_profiles` | `gm.profiles.names`, `gm.profiles.get` | real; `quantity` needs `attrs["quantities"]`, which `api.md` does not list |
| `read_profile` | `gm.profiles.get` | real |
| `simulate` | `gm.simulate`, `gm.plants.from_dict`, `plant.set_params`, `Results.summary`, `Results.get`, `Results.names`, `Results.to_bytes` | real |
| `read_result` | none: it reads the stored JSON | built |
| `search_documents` | none: it reads `Workspace.documents` | built |
| `check_results` | `gm.checks.run_all`, `gm.checks.limits`, `gm.checks.Limits.from_dict`, `gm.Results.from_bytes` | real |
| `compute_kpis` | `gm.kpi.compute`, `gm.kpi.totals`, `gm.Results.from_bytes` | real |
| `estimate_costs` | `gm.economics.capex`, `opex`, `lcoh`, `lcoc`, `npv`, `co2`, `gm.economics.Assumptions` | real |
| `test_module` | `gm.modules.load_file`, `gm.modules.get`, `gm.testing.check_module` | real |
| `optimize` | `gm.optim.minimize` | **gap**: `later` in gemini, and it needs a `profile` this tool does not take |
| `sample_uncertainty` | `gm.optim.sample` | **gap**: `later` in gemini, and it needs a `profile` this tool does not take |

## References

Both formats are frozen. Each is a key of `RunStore.save_artifact(run_id, key, data)`, so a store must
accept the `/`; `check_run_store` tests it. An artifact belongs to its root run.

- **A design** is a stored, validated plant dict. `build_plant` saves it under `design/<name>` and
  returns that text. `<name>` is letters, digits, `.`, `_` or `-`.
- **A result** is stored under `result/<id>` as JSON: `{path: {field: {unit, values, time?}}}`.
  `values` is the list of samples, `unit` their unit, and `time`, when there is one, the list of ISO
  8601 times. `simulate` leaves `time` out: every series has the same times, which would triple the
  size, and the summary gives `start`, `end` and `steps`. `<id>` is a hash of the plant that ran,
  the profiles and the window, so a replay finds the same result. Beside it, `simulate` keeps
  `<id>.results` (`Results.to_bytes()`) and `<id>.plant` (the spec that ran).

### How `simulate` runs

`gm.schedule(plant, demand, SCHEDULE_RULES)`, then `gm.simulate(plant, plan, on_error="record")`:
a day that fails is one of gemini's problems in the summary (`failed_steps`, the first five
`errors`) and the year still runs. `SCHEDULE_RULES` in `tools/gemini/brief.py` holds the brief's
numbers in one place. Without `profile` the run takes every gemini demand profile. The summary
adds `gm.kpi.totals`.

**The input bridge.** A design keeps its setpoints and other inputs (a heat pump's
`temperature_setpoint`, the air temperature) in its spec under `boundary[""]["inputs"]`,
`{module path: {name: value}}`, which gemini validates and round-trips. `apply_inputs` in
`tools/gemini/plants.py` sets them with `plant.set_inputs` whenever a plant is loaded. This is the
one call outside gemini's `api.md`; it stays until gemini reads these inputs itself.

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
`build_plant` gets gemini's plant schema that way, so `import geomind` stays free of gemini.

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

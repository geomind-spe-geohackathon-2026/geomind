# Tools

The primitive actions of an agent, in `geomind/tools/`. Tool names are stable identifiers: a change
is a new version.

## Catalogue

Every tool exists now as a real `Tool`. Names, schemas and effects are
[frozen](api.md#frozen-interfaces). A **stub** raises `NotImplementedYet("<tool> comes in <phase>")`,
so a call is an error result with `code: "not_implemented"`. `gd.tools.gemini.<name>` is the public
path; the package has one file per group. All are idempotent except `set_case` and `save_profile`, which write
the problem state as `update_state` does.

| Tool | File | Effect | Inputs | Returns | Status |
|---|---|---|---|---|---|
| `list_modules` | `catalogue.py` | `read` | `category=None` | `[{name, category, summary}]` | built |
| `describe_module` | `catalogue.py` | `read` | `name` | gemini's module description | built |
| `evaluate_module` | `catalogue.py` | `compute` | `name, parameters, inlets=None, controls=None, state=None, dt=None` | `gm.call(..., units="display")` result (`outlets`, `outputs`, `state`, `errors`) as `{value, unit}` in gemini's display units (MW, degC, m3/h; no geomind unit map); values with a dimension go in as `{value, unit}`, never text; every inlet needs `fluid` (gemini's error otherwise); a module with state needs `state` and `dt` | built |
| `list_plants` | `plants.py` | `read` | `plant_class` (optional), `with_schema` (optional) | `{project_plants, plants: [{name, summary}]}`; `project_plants` are the sorted file names of the run's project (`Workspace.plants`), `[]` without a project. With `plant_class`: also `plant_class`, `capabilities` (`gm.plants.capabilities()[class]`: roles, schedulable and `ranges`, the leaves that may state a search range) and `roles` (`gm.plants.roles()` of the class's roles); an unknown class is an `unknown_name` error with the close match. With `with_schema`: also `schema`, `gm.plants.schema()`. Before this change it returned every class's `capabilities` and all `roles`, over the result limit | built |
| `read_plant` | `plants.py` | `read` | `design=None, plant_class=None, project_plant=None`: none is the project's plant when `Workspace.plants` holds exactly one file (several: a `ToolError` `unknown_name`, path `project_plant`, naming the files and the other two ways); `project_plant` a plant file of the project by name (its file stem); `design/<name>` a stored design, `plant_class` a class name (`gm.plants.get`); two of them is refused | `{plant, ranges, options, issues, checked_against}`: `plant.to_dict(structure=True)`, `ranges` as `{path: {min, max}}` with `{value, unit}` in display units (plain numbers for a count), `options`, and `issues` (`path, code, message, suggestions, kind, quantity, accepted`) from `gm.check(plant, case)` when the state has a case (`checked_against` `case`) else from `plant.check()` (`plant`), which lists as missing what the case fills (`d0.gradient`); a class lists everything it needs as missing | built |
| `build_plant` | `plants.py` | `write` | `plant` (offered as a short object schema with gemini's two shapes; the full `gm.plants.schema()` is `list_plants` `with_schema`; validation is gemini's, so every earlier input is still valid), `name` | `{design, checked_against, issues}` as `read_plant`; `gm.Plant.from_dict` is stored by `stored.save_design`; a file gemini cannot read raises gemini's `ValidationError` (path, code, message, suggestions) and stores nothing, a file with missing values is stored with its issues | built |
| `patch_plant` | `plants.py` | `write` | `design, changes, name` | `{design, checked_against, issues, missing}`: a JSON merge patch on a stored design, built by gemini and stored as `design/<name>`, with what is still missing; a refused patch stores nothing; an engineer of the design team (an agent with a `discipline`) may patch only the part `design.owners` gives it, and a path it names no prefix of by its module's gemini type (`OWNED_MODULES`, then the category), else `not_allowed` (`ownership.py`); a module's parameters written at the top (`d0`, `d0.well`) or inside `modules` are taken as under `params` | built |
| `merge_designs` | `plants.py` | `write` | `base, designs, name` | `{design, checked_against, issues, missing}`: what each design changed from `base`, applied in order and built by gemini as `design/<name>`; two designs setting one value differently are an `invalid_input` conflict naming the path and both designs, and nothing is stored | built |
| `set_ranges` | `plants.py` | `write` | `design, ranges, name, options=None`: `ranges` is `{path: {min, max}}` with `{value, unit}` bounds (plain numbers for a count such as `size.doublets`); a path is the plant-file leaf without `params.` (`depth`, `heat_pump.capacity`, `d0.nominal_flow`) | `{design, plant, ranges, options}` as `read_plant`; `plant.set_range` and `plant.set_options` on a copy of the design, stored as `design/<name>`; an unknown path or a refused bound is gemini's error with its path | built (to be registered) |
| `set_case` | `case.py` | `write` | `source=None, changes=None, requirements=None, economics=None`: `source` is `project`, `origin` (the case the user gave, with its files) or none (the state's case); `changes` an RFC 7386 merge patch on the case, without `requirements` and `economics`; `requirements` `{name: requirement or null}` (add, replace or remove by name); `economics` a merge patch on the content of the economics file | `{case, version}`; the state's `case` replaced and its files kept as `case/<file name>`; the project's case or the first case of a chat also becomes `case_origin`; a case `gm.Case.from_dict` or `Case.check` rejects is an error with gemini's `path`, `code` and message and nothing is stored | built |
| `case_changes` | `origin.py` | `read` | none | `[{path, change, given, now}]`: every difference of the state's case from `case_origin` (`changed`, `removed`, `added`; a section key, `requirements.<name>`, `file <name>` for a file's content, the economics file included); `[]` when it is the case the user gave | built |
| `ask_economics` | `economics.py` | `read` | `values`: each economics key with `value`, `unit`, its catalogue `row`, `source`, `year`, `url`, `status` and `others` (the rows not recommended), `currency`, `price_year` and `discount_rate` among them or in `open`; `open`, `note` | a `Request` with the one economics question and options approve all, change some, stop; on approve all (`on_answer`) every value is set with `set_case`, each row kept in `economics.about.sources` and recorded as a confirmed assumption `economics.<key>` with its citation; the result is `{answer, economics, keys, open, assumptions, version}` | built |
| `accept_case` | `origin.py` | `write` | none | `{version}`; `case_origin` becomes the state's case. Only the design loop's driver holds it, after the user approved the change | built |
| `read_case` | `case.py` | `read` | `section=None`: a key of the case, `economics` or `schema` | the case, the section, the parsed economics file, or `gm.Case.schema()` with `economics_schema`; no case is `invalid_input` | built |
| `describe_case` | `case.py` | `read` | `path`: a dotted key or a part of one (`site.air`, `requirements`, `economics.capex`) | `keys`: each key under it with its units, meaning and source, and for `requirements` what each option means; an unknown path is `unknown_name` | built |
| `list_profiles` | `runs.py` | `read` | none | `[{service, power, supply_temperature, return_temperature, start, end, steps, peak}]`: the heating and cooling demand of the state's case, `power` the `{unit, file, column}` its series names, temperatures in degC and the peak in MW | built |
| `read_profile` | `runs.py` | `read` | `service` (`heating` or `cooling`), `start=None`, `end=None` (ISO 8601, inclusive) | `{service, time, value, unit}` of the case's demand in MW | built |
| `save_profile` | `case.py` | `write` | `name, values, unit, start, step, service`, all required: `unit` a unit of power, `step` `{value, unit}`, `service` `heating` or `cooling` | `{demand, time, steps, version}`; gemini checks the values (`gm.case.from_values`), they are written in `unit` as the column `name` of `data/<name>.csv` (first column `time`) in the run's case files and the service's `power` becomes `{unit, file, column}`; a profile that does not cover the case's `time` sets it to the profile's span in the same call; gemini rejects a case that does not fit and nothing is stored | built |
| `simulate` | `runs.py` | `compute` | `design=None, changes=None, start=None, end=None` | `{reference, summary}`; the run is stored; the summary gives the plant, the case's time span, the window, `steps`, `failed_steps` and the first `failures`, the `report` totals in display units, gemini's `verdict`, the `unmet` requirements (the checks with `passed` false) and the demand `coverage` | built |
| `read_result` | `results.py` | `read` | `reference, path=None, field=None, start=None, end=None` (ISO 8601, inclusive) | `{time, value, unit}` with `path` and `field`, otherwise `{path: {field: {min, max, mean}}}`, in MW, degC, bar, m3/h and kg/s | built |
| `search_rag` | `results.py` | `read` | `query` | `{matches, note}`: documents `{id, title, text, score}` and passages of the project's files `{name, start, text, score}`, best first, at most 8; `note` when nothing matches (the project does not state it: an assumption or `ask_user`) or the run tree searched the same words | built |
| `list_files` | `files.py` (`geomind/tools/`) | `read` | none | `{files: [{name, size, media_type}]}` | built |
| `read_rag` | `files.py` (`geomind/tools/`) | `read` | `name, start=0, length=None` | `{name, start, total, text, next, table?}` | built |
| `check_results` | `assessment.py` | `compute` | `reference` | gemini's verdict on the run's own case, in display units: `{feasible, reasons: [{kind, name, message, ...}], requirements: [check], failures: {total, groups}, metrics}` | built |
| `compute_kpis` | `assessment.py` | `compute` | `reference, names=None` | `{name: Value}` in display units: `gm.evaluate.totals` and the metrics of `gm.evaluate.report`; an unknown name is `unknown_name` with a did-you-mean | built |
| `estimate_costs` | `assessment.py` | `compute` | `reference` | `{capex, opex, annualised_cost, lcoh, lcoc, lcts, npv, payback, co2}` as Values in display units, from the case's `economics.json`; a cost whose figure is missing is `{error}` with gemini's `missing_assumption` and its path | built |
| `size_plant` | `study.py` | `compute` | `design, name`: the backup policy is the plant's `params.backup` (the DesignLead sets it and records the assumption); `name` names the design and `study/<name>` | `{design, study, sizing}`; `gm.study.size` on the state's case, the sized plant stored as `design/<name>`, `sizing` gemini's notes (`sized`, `unchanged`, `broken`, `simulation`) with quantities as `{value, unit}` | built |
| `optimize` | `study.py` | `compute` | `design, objective, evaluations, seed, name`, all required: the variables are the design's ranges and options (`set_ranges`), the constraints the case's requirements; a design with none is gemini's error | `{best, feasible, trials, design, study}`; `best` is `Best.to_dict()` (display units, the plant inside), the best plant stored as `design/<name>` (the study is `study/<name>`); with no trial that ran there is no `design`; gemini's errors pass through | built |
| `evolve_structure` | `study.py` | `compute` | `design, objectives, name` | `{front, best, evaluations, invalid, study}`: `gm.study.evolve` over a superstructure (`optional`, `choices`) and its ranges, with the required settings `evolve_evaluations`, `evolve_population`, `evolve_seed`, `evolve_polish`; each front design stored as `design/<name>_<n>` and listed with `structure`, `metrics`, `feasible`, `reason`; the study as `study/<name>` | built |
| `sample_uncertainty` | `study.py` | `compute` | `design, metrics, samples, seed, name`, all required | `{study}` and `Sample.to_dict()`: `samples` and `summary` per metric (`mean`, `p5`, `p50`, `p95`, `failed`); distributions only from the case's `uncertainty` (none is `missing_value`) | built |
| `sensitivity` | `study.py` | `compute` | `design, metrics, name` | `{study}` and `Tornado.to_dict()`: `rows` sorted by effect, bounds from the case's `uncertainty` | built |
| `compare` | `study.py` | `compute` | `references, by`: references of runs `simulate` returned | one entry per reference: `reference`, `values` in display units (read from each run's `Report.to_dict()`, since `Comparison.to_dict()` is SI), `ranks`, `pareto`, `feasible`, `reasons` | built |
| `run_study` | `study.py` | `compute` | `designs, method, name, objective=None, metrics=None, evaluations=None, seed=None, samples=None, prepare=None`: a `gm.Study` over the state's case and the stored designs; a setting the method needs and the call leaves out is gemini's error | `{study, runs, best}`: per design `plant_name`, `feasible`, `verdict`, `metrics` (display units), `ranks`, `pareto`, `note`, `found`, and the `design` the run ended with (sized or best plant) stored as `design/<name>_<plant>` (the study's `name` first, so two studies over one design never clash); `best` the feasible design ranked first by the objective | built |

| `list_studies` | `studies.py` | `read` | none | one item per stored study of the chat: `study` (`study/<name>`), `tool`, `method`, `designs` (plant names), `best` (design reference or `null`) and `current` (the state's case is still the one it ran on) | built |
| `read_study` | `studies.py` | `read` | `study` | the stored artifact `study/<name>` (see [Stored studies](#stored-studies)); an unknown key is `unknown_name` | built |

### gemini mapping

Every name is public in `gemini/.claude/docs/api.md`. geomind 0.4.0 supports gemini `>=0.5,<0.6`
(the pin in `pyproject.toml`; `tests/unit/test_gemini_names.py` fails on another installed version).
gemini's API is frozen from 0.5.0; a breaking gemini release needs a new geomind minor version.

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
| `search_rag` | none: it reads `Workspace.rag` and the text of `Workspace.files` | built |
| `list_files`, `read_rag` | none: they read the optional `Workspace.files` and `Workspace.file` | built |
| `check_results` | `gm.evaluate.verdict`, `report`, `gm.Results.from_bytes` | real |
| `compute_kpis` | `gm.evaluate.totals`, `gm.evaluate.report` | real |
| `estimate_costs` | `gm.evaluate.capex`, `opex`, `annualised_cost`, `lcoh`, `lcoc`, `lcts`, `npv`, `payback`, `co2`, `report` | real |
| `size_plant` | `gm.study.size`, `Plant.sizing`, `Plant.to_dict` | real |
| `optimize` | `gm.study.minimize`, `Best.to_dict` | real |
| `sample_uncertainty` | `gm.study.sample`, `Sample.to_dict` | real |
| `sensitivity` | `gm.study.sensitivity`, `Tornado.to_dict` | real |
| `compare` | `gm.evaluate.report`, `gm.evaluate.compare`, `Report.to_dict` (display units) | real |
| `run_study` | `gm.Study.from_dict`, `Study.run`, `StudyResult.to_dict`, `Run.report` | real |

### Stored studies

Every study tool (`size_plant`, `optimize`, `sample_uncertainty`, `sensitivity`, `run_study`) takes a
required `name` and stores the chat artifact `study/<name>`, written once like `design/` (the same
study on the same case again is accepted, any other content under a taken name is a `ToolError`
with path `name`, refused before the study runs). The artifact holds:

- `study`: gemini's `study.json` (`gm.Study.to_dict()`, format 1, kind `study`) that ran: `name`,
  `cases` (`["case/case.json"]`, standing for the state's case), `plants` (the references of the
  stored designs it read, `design/<name>`), `method` and the settings.
- `result`: gemini's plain form of what came back: `StudyResult.to_dict()` for `run_study`;
  for `optimize` the search as `Study` runs keep it (`best` with `plant` left `null`, `feasible`,
  `evaluations`; the history is not kept); `Sample.to_dict()` and `Tornado.to_dict()` (display
  units) for the other two; `{sizing}` for `size_plant`.
- `designs`: `{read: [design references], wrote: [design references]}`.
- `case`: the id of the case it ran on, a hash of the case dict and of its files' digests;
  `list_studies` compares it with the state's case to give `current`.
- `tool` and `versions` (`geomind`, `gemini`, `python` of the process).

Forms: `optimize` is method `minimize`, `sample_uncertainty` is `sample` and `sensitivity` is
`sensitivity`, each over one plant. `size_plant` is method `run` with `prepare: ["size"]`, the
closest form gemini has: its method list has no sizing alone, so a reader must not take the study
for a simulation; the request is in the gemini requests. The recommended `best` of a study is the
feasible design ranked first for `run_study`, the feasible best for `optimize`, the sized design for
`size_plant` and `null` for sampling and sensitivity.

Each save adds the study to `studies.index` (a chat artifact without a `/`:
`{studies: [{study, tool, method, designs, best, case}]}`), which is how `list_studies` finds the
chat's studies: `RunStore` cannot list artifacts by prefix and its protocol is the backend's, so
geomind keeps the list itself. The study tools declare `runs_alone`, so two saves never race on the
index. After the artifact and the index are saved, the tool sends the public event `study.recorded`
([events.md](events.md)). `run_study` stores each run's plant as `design/<name>_<plant name>`.

`size_plant`, `optimize`, `sample_uncertainty`, `sensitivity` and `run_study` have a time limit of
`STUDY_TIMEOUT_S` (900 s): past it the model reads a `timeout` error and asks for fewer
evaluations or draws. The gemini call runs in a worker thread, which Python cannot stop, so it
finishes in the background and its result is dropped.

## References

Both formats are frozen. Each is a key of `RunStore.save_chat_artifact(chat_id, key, data)`, so a
store must accept the `/`; `check_run_store` tests it. An artifact belongs to its chat, so a later
message of the same chat reads it; a run without a chat uses its root run id as its chat id.

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
-> "design/<name>"`, `save_study(...) -> "study/<name>"`, `load_study`, `load_design(context, design, where) -> gm.Plant`, `save_run(context, plant,
results, summary, options, ran) -> "result/<id>"` and `load_run(context, reference, where) -> (plant,
case, results)`. `<id>` also covers the contents of the case's files, so a changed file is a new
run. A reference no run made is `unknown_name` with `path` `reference`.

### Stored references

Every argument that takes a stored reference (`design` and `designs`, `reference` and
`references`, `study`) has a JSON Schema `pattern` (`^design/[A-Za-z0-9._-]+$`, `^result/...$`,
`^study/...$`) and a description with one example, built by `references.reference_schema` through
the tool's `late_schemas`. The pattern is a hint to the model and is not enforced by the input
model, so a wrong reference reaches the tool and gets `unknown_name` with the form, an example, the
stored references of that kind in the chat and, for a name given without its prefix, the reference
meant. `stored.save_design` and `save_run` keep the chat artifacts `designs.index` and
`results.index` (`{references: [...]}`, oldest first) for that listing, as `studies.index` does
for studies; a chat from before the indexes lists the designs its studies read and wrote, and no
earlier result.

### What a gemini error adds

`dispatch.error_output` passes a gemini error through its own `to_dict()`, extended by
`tools/gemini/explain.py`:

- A rejected unit (`invalid_unit`, `unit = '...'`, no accepted units in gemini's message) keeps
  gemini's message and adds the unit it probably meant and every unit of that dimension, read
  from `gm.units.names()` and `gm.units.si_unit`. No alias is accepted: the model must call again
  with a unit gemini lists. `save_profile` knows its step is a duration and lists
  `gm.units.names("duration")`.
- A study gemini rejects for a missing search range (`size_plant`, `optimize`, `run_study` with
  `prepare: ["size"]` or `minimize`) keeps gemini's message, path and code and adds, per design
  that lacks the range, the `set_ranges(design=..., ranges={path: ...}, name=...)` call that adds
  it. The unit is the leaf's unit in the plant file; the bounds are the placeholders `<min>` and
  `<max>`, never a number. The text says the range is not in the case: ask the user with `ask_user`, propose values
  with a reason, and call `set_ranges` only after the user confirms (ranges, and uncertainty
  ranges, come only from the user or the case). A search over a plant with no range and no options lists the first
  twelve leaves that can state a range, with their units.

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
whose figure is missing is `{"error": {path, code: "case_incomplete", message, suggestions}}` beside the
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
| `execute` | runs code (no shipped tool does) | after approval |
| `external` | network or anything outside the run | after approval |

`idempotent` says a call may run again after a crash. `is_pure` (`read` or `compute`) says a call
may run beside others and again in a replay. `reruns_in_replay` says a tool that is not pure runs
again in a replay too, because all it changes is the run's own log. `Tool` is shaped like a protocol, so toolsets from
other sources (MCP later) fit: without `input_model`, only the required and known names of
`input_schema` are checked. An agent names a tool by its attribute, on its own copy.
`late_schemas` maps an input to a function that returns its schema when the tool is offered:
`build_plant` gets a short schema that way (the full one is `list_plants` `with_schema`), so `import geomind` stays free of gemini.
A tool that asks may set `on_answer(context, input, text)`: the engine calls it with the user's
answer and its return is the call's result (`ask_economics` sets what the user approved). It keeps
the text under `answer`, and a replay calls it again from there, so the state it writes follows.

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
  `stop_reason="error"`; one tool counts once per step, since the calls of a step are sent before
  the model saw any of their errors. The same call (tool and whole input) failing again in more
  than `max_retries` later steps stops it too; calls with other arguments and one error are
  others. An argument the tool does not have is an error result that names the
  tool's arguments and is no validation failure (#126); a tool the run does not offer (a memory
  tool or the curator with the memory off) is answered `not_allowed` without running (#127).
- A call whose input is `{"shortened": ...}`, the outline an old history showed of an earlier call,
  is an error result naming the tool's arguments; the history now shows an old long call with an
  empty input and its outline in the message's text (`shortened_message`).
- Any other exception is a bug: it is reported through `on_error`, and the model reads only
  `internal error`, with `code: "internal"`.
- A result over 2000 characters is saved as the chat artifact `result-<hash of the call id>` and its
  `tool.result` carries the `reference`; the key is a hash, so a call id never becomes a path
  (`geomind/tools/stored.py`). Up to `tool_result_limit` the model reads it whole in the step after
  the call; from the next step on, `Context` shows `stored_form` instead (the reference, the small
  top-level values, an outline of the rest, see [context.md](context.md#long-conversations)). Over
  the limit it gets `stored_form` at once. `read_stored(reference, path=None)` returns the whole or
  one part (dotted keys and indexes); agents that read gemini results have it. Logs of 0.4.x hold
  `{reference, summary}` only above the limit and no reference below it, so they replay as before.
- `Tool.schema()` leaves out the `title` and `default` annotations of the input schema, late
  schemas included.
- A sync tool that times out keeps running in its thread until it returns; a thread cannot be
  stopped from outside.

### Error results

An error result has gemini's Problem shape, `{"error": {path, code, message, suggestions}}`
(`geomind/types/problems.py`, schema `geomind/schemas/tool_error.json`).

A gemini error passes through its own `to_dict()` unchanged, with its code from `gm.errors.CODES`,
except that a missing value of the case (`missing_value`, `missing_assumption` on a path of a case
section) becomes `case_incomplete`; a missing search range keeps gemini's code.
A validation error takes `path` from the first input field that failed. Every other error takes
`code` from this fixed list, and `path` is the input field at fault or `null`:

| `code` | Means |
|---|---|
| `invalid_input` | the input does not fit, or a `gd.errors` class says the call was wrong |
| `unknown_name` | a name that does not exist, such as a tool, a skill or a result path |
| `not_implemented` | the capability has its final signature and is not built yet; do not retry |
| `not_allowed` | the run cannot do this: no project, the memory is off, or a path outside the project |
| `no_case` | the chat has no case: call `set_case` or ask the user |
| `case_incomplete` | the case misses values gemini needs, to read it or for this plant; `path` is the first and `suggestions` lists every missing path, from `gm.case.missing` or gemini's check; the message stays gemini's |
| `files_unavailable` | the workspace has no `files` and `file`: an older backend; the run goes on without them |
| `knowledge_unavailable` | the workspace has no `knowledge_search`, `knowledge_files` and `knowledge_file`, or no document: the run goes on without a knowledge base |
| `not_text` | `read_rag`: the file gives no text (binary, encrypted, a scan) |
| `timeout` | the tool passed its time limit |
| `budget` | a budget or time limit stopped a delegate's nested run; the message names it with what was spent and the cap |
| `nested_stopped` | a delegate's nested run stopped without an answer (a step limit, a refusal, invalid calls); the message says why |
| `context_exceeded` | a delegate's nested run asked the provider for more than the model's window; the message has the provider's numbers |
| `internal` | a bug or a crash; the detail is in the log, never in the result |

A permission denial is no error class: its result is the reason as text, with `is_error` set and
`source="denied"`. `runlog` `tool_call.error` is `true` on an error result, and the Problem is in
`tool_call.output`.

## Built-ins

- `ask_user(question, options=None)` returns a `Request` of kind `question`; the engine pauses.
  `options` is a list of strings or of `{value, label}`, normalised to the latter. An answer to a
  question with options is `{"text": <value>}` or typed text: text that is no option's value is
  the user's own answer, and the model reads it marked as typed (`typed_answer`). Only the step
  limit's question (`continue`, `stop`) takes its options alone.
- A question whose case paths (`site.air.pressure`) an earlier answered question of the same run
  tree named exactly is not asked: its result is the earlier answer (`engine/questions.py`, from
  the root's log, so across resumes too; the run's bug 7).
- `finish(answer)` ends the run, after `before_finish` hooks, the agent's own
  `answer_problem(context)` (a required step code checks, refused once per run, such as the case
  lead's economics, #124) and output validation.

Both have effect `read`, so `ask` mode lets them through; `plan` mode runs neither.

## Problem state

`update_state(changes)` (`write`, not idempotent) applies JSON Patch operations to the problem state
and emits `state.changed`; see [context.md](context.md#problem-state). An invalid patch is an error result that
says how to fix it. A path under `/case` or `/case_origin` is `not_allowed`: only `set_case`
writes the case, after gemini validates it. The offered schema types `changes`: `op` an enum, `path` a pattern over the allowed roots and
`value` described in words with the item shape of each list (no `$defs`, no `anyOf`: that cost
twice the tokens; the error of a wrong value repeats the shape expected). The input model is still
`list[dict]`, so what was valid stays valid; before the patch is applied the tool checks the path
form and the value against the model of the list (`/results/-` for an add, `/results/<id>` for a
replace or remove, `/results/<id>/<field>` for a field, `/results` with a list, never a position),
and a refused change names the shape expected there. The shape of a key of `design` or `verification` comes from `ProblemState` alone
(`state.annotation_at`): once the state types it, a value of another shape is refused with the
expected one; an open `dict[str, Any]` is not checked. The default rule of [permissions.md](permissions.md) allows it in `ask` mode.

## Skills

`read_skill(name)` (`read`) returns one skill; see [context.md](context.md#skills).

## No code tools

geomind runs no code: `run_python`, `write_file`, `read_file`, `write_module`, `test_module` and the
sandbox they ran in were removed in 0.4.22. A model gemini lacks makes a family `blocked`.

## Delegate

`Delegate(agent, max_summary_tokens=None)` runs the agent in a nested engine run through
`context.session`, with a clean context (the task text only), a child run id and `parent` set on
every event. The model reads only the final answer, cut to the token limit at four characters per
token (default: the `delegate_summary_tokens` setting). The effect is `compute`, so delegating
needs no approval of its own: each nested tool is decided by the same permissions. It is not pure
and not idempotent: it runs alone, a replay reuses its recorded result, and after a crash it
becomes an error result. A pause in the nested run pauses the parent on the same request. Usage of
the nested run adds to the parent's.

## Project files

`read_rag` returns the text by pages of at most 20,000 characters (`PAGE_CHARACTERS`, under
`tool_result_limit`). A PDF goes through pypdf, each page after a `[page n]` marker; a long result is
stored by reference like any other, so old reads shrink to their outline. `set_case(files=[...])`
gives project files to the case: `set_case` passes their bytes to gemini under the same name, and
`changes` names them as the `file` of a series. gemini validates, and geomind adds no unit alias.
`save_profile` keeps taking values: a file goes through `set_case`.

When a case misses values, `set_case` answers `case_incomplete` with every path in `suggestions`,
from `gm.case.missing`, for one question to the user. The design loop asks for a missing case at
its start only when the project has no files; with files the design lead reads them first.

`compute_kpis` keeps gemini's report entries as they are, in the shape of 0.4.11: a cost gemini
gives no value for is `{value: null, unit, reason}` or left out, as the report gives it. Beside them,
`errors` maps each such cost (`capex`, `opex`, `annualised_cost`, `lcoh`, `lcoc`, `lcts`, `npv`,
`payback`, `co2`) to gemini's error for it, a missing case value being `case_incomplete` with the
path in `suggestions`; without any, `errors` is left out. `names` keeps the errors of those names.

## From the first live run

The live run of 0.4.15 (`tests/fixtures/live/recording.jsonl`, model moves only) showed five gaps,
each pinned in `tests/integration/test_live_regressions.py`:

- A CSV whose time column has another name: `set_case(columns={file: {old: "time"}})` renames the
  header before gemini reads the bytes (gemini has no public way to name the time column), and
  gemini's `invalid_value` about the first column comes back with the exact retry call.
- A case without its header: `case_incomplete` adds a minimal case from `gm.Case.schema()` as JSON
  to `suggestions`, and the description of `set_case`'s `changes` shows it (`case_skeleton`).
- `read_stored` with a wrong path lists the keys (or first indexes) there in `suggestions`; on a
  text, it says to read it without a path.

From the second live run (`tests/integration/test_live_regressions_b.py`, recording
`tests/fixtures/live/recording_b.jsonl`):

- A series in `changes` naming a file not passed: the suggestion is the `set_case` call with
  `files=[...]` naming them.
- `invalid_unit` in `set_case`: `suggestions` holds the field as sent with the accepted unit its
  letters spell and its value a number (`time.step = {'value': 1, 'unit': 'd'}`), and
  `accepted units: ...` from `gm.units.names`.
- `requirements` (or `economics`) inside `changes`: the suggestion is the call with
  `requirements={name: requirement}`.
- `build_plant` without a header: `old_format`, with the smallest plant file of
  `gm.plants.schema()` last in `suggestions` (`plant_skeleton`, `geomind/tools/gemini/skeleton.py`).
- A nested run that passed the model's window: the delegate answers `context_exceeded`.

From live segment 7 (`tests/integration/test_live_regressions_g.py`):

- A run waiting on a nested run's request reports that run's usage in its result.
- Every next design round carries the last round's answer (`handover_text`), after a question
  and after a failed verification (`routed_task_of`).
- Rounds that recorded no design are no `repeated_failure` (`should_stop_repeated`).
- A step that asked the user gives its step back (`RunState.questions` in the step limit).
- An object sent as JSON text gets the suggestion to send the object (`_validation_problem`).
- A PDF reads in layout order (`laid_out`): a table drawn word by word keeps its rows.

From the fifth live run (`tests/integration/test_live_regressions_e.py`, recording
`tests/fixtures/live/recording_e.jsonl`):

- The run searched 147 times, mostly for values the brief does not hold. `search_rag` now
  returns `{matches, note}`: no match says the project does not state it (choose an assumption
  with its reason, or `ask_user`), and the same words again in the run's conversation, in call
  order, are noted (so a resume and a replay give the same note, #131). A file's
  name alone matches nothing.
- A series naming a column by the name `columns` renamed gets the new name in `suggestions`.

From the fourth live run (`tests/integration/test_live_regressions_d.py`, recording
`tests/fixtures/live/recording_d.jsonl`):

- `search_rag` searched only `documents/`, so a brief attached as a project file (a PDF) was
  never found: it now also searches passages of 1,500 characters of every project file that reads
  as text, each with its `name` and `start` for `read_rag`.
- `read_stored` (`Tool.stored_input`): a long part of a stored result keeps the reference it was
  read from and is not stored again, so no chain of copies is read over and over.
- The CLI asks again for an answer a question does not accept (`--answer-retries`) and stops as
  `waiting` otherwise; `geomind resume` answers it.

From the third live run (`tests/integration/test_live_regressions_c.py`, recording
`tests/fixtures/live/recording_c.jsonl`):

- A rejected unit beside missing values stays `invalid_unit` with gemini's path and the corrected
  field; the missing paths follow as one `case_incomplete: also missing ...` suggestion. Only an
  error about missing values (or a missing header) becomes `case_incomplete`.
- Requirements of another shape: the `requirements[i].on` and `.quantity` paths are one suggestion,
  `requirements={'<name>': {...}}`, the fields and their options from `gm.Case.schema()`
  (`requirement_shape`).
- `shown_message` (`geomind/tools/gemini/explain.py`) shows a gemini error's problems with each path
  once, and the same problem on many rows of a file as one line: the first row's message, the
  number of rows and the first and last row. gemini's codes, paths and text are unchanged.
- `read_rag`: the reads of a run tree are one memory (`reads_of`, on the root session), so a
  later design lead round sees what an earlier one read; a read of another run counts only when its
  result was stored. Once the whole document was read, every page is `already_read`, `force` too.
- A CSV time without an offset stays gemini's error; geomind rewrites no value. A series takes
  gemini's `time_zone` (gemini 0.5.13) through `set_case`, and the error suggests the retry with
  `time_zone: <IANA zone of time.start>` on each series (`zone_retry`): the model chooses the zone
  and records it as an assumption; geomind has no zone.
- `read_rag` remembers what the run read, with the step of each read: a page read again is
  `already_read`, `force` too. Its text is still in the run's conversation
  (`keeps_result="run"`), so the note is "already read at step N; its text is in your context;
  call set_case next" (an agent without `set_case`: "work from it") and shows no `reference`
  (#122); only after a compaction since the read (more turns in `problem.compaction` than at the
  read) does it name `read_stored` and the stored earlier result's `reference` (#120), and
  `force` reads the page again.
- A tool input sent as JSON text (`parsed_inputs`, `parsed_json`) is read with its missing closing
  brackets added, its stray ones after the value dropped, and up to three stray closing brackets
  in the middle deleted where `json` stops (`}}}}, "next"` or `}}]}`), only when no closing
  bracket is made up (#117).
- `set_case` maps unit names as sources print them to gemini's name of the same unit, no factor
  (`unit_bridge.gemini_unit_name`): `³` is `3`, `·` is `.`, `MWth` and `MWcool` are `MW`, only
  where the key's units (`x-units` or the `unit` enum of its schema) hold the name; a
  requirement's unit where gemini knows it. Each is in `converted` with the reason `unit name`
  (#118).
- `geomind run --loop design` takes a project with files and no `case.json`.

## Memory and knowledge tools

The case, design and analysis teams have `search_memory()` and `read_memory(id)` over the
memory's experience: past designs alike to the case and the lessons of the caller's role; the
curator alone has `write_lesson(id, kind, role, text, source)` (`geomind/tools/memory.py`). With
the memory off they are not offered and answer `not_allowed`. Every model agent but the
coordinator, the summarizer and the curator has `search_rag(query)`, one search over the
project's documents and files and the knowledge base: each match has its `scope` (`project` or
`knowledge`) and its `citation` (a file and page, or a document, title and page), the best of each
scope in turn (`geomind/tools/gemini/results.py`); `read_rag` reads a project file or a whole
document as `knowledge/<name>`. Reading from a workspace without a knowledge base answers
`knowledge_unavailable`. `search_knowledge`, `rag_search` and `rag_read` are the old names
(`RENAMED_TOOLS`). See [memory.md](memory.md).

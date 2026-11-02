# Changelog

`gd.__version__` follows semver below 1.0, the same rule as gemini: a breaking change to a frozen
interface raises the minor version, and an addition or a fix raises the patch version. The rule and
the list of frozen interfaces are in [.claude/docs/api.md](.claude/docs/api.md#frozen-interfaces).

## [Unreleased]

- Designer: search ranges come only from the user or the case. A missing one is recorded in `questions` and asked with `ask_user` (values proposed with a reason); `set_ranges` only after confirmation. The Designer prompt is cut from about 2,800 to about 1,500 tokens (tool detail stays in the tool descriptions and the `designing-a-plant` skill). New offline recording `designer/missing_range`.

Additive: geomind holds no model id (Sahand, 2026-11-02: no Anthropic model anywhere).

- `FIXED_DEFAULT_MODEL` and `FIXED_CHEAP_MODEL` are removed. `default_model`, `coordinator_model`
  and `summarizer_model` are `None` unless `GEOMIND_MODEL` / `GEOMIND_CHEAP_MODEL` set them;
  A run on a real provider (`needs_models`) is refused before `run.started` with a `RunError`
  naming each role's missing setting (`designer: set GEOMIND_MODEL or designer_model`);
  `OpenRouter` also refuses a call without a model. Fake runs need no model.
- `run.started` records `models` (the model of every role; optional, old logs load) and the export
  header lists them.
- Context window: new setting `context_window` (`GEOMIND_CONTEXT_WINDOW`), else the provider's
  `context_length`, read once per process off the event loop at the start of a run on a real
  provider (a fake run never fetches); unknown raises `RunError` at the start (before, an unknown model got a guessed 128 000, and
  `CONTEXT_WINDOWS` / `DEFAULT_CONTEXT_WINDOW` held three Anthropic models).
- Caching: `CACHED_MODELS` is removed; new setting `cache_marked_models` (`GEOMIND_CACHE_MARKED_MODELS`)
  lists the model id prefixes that get cache breakpoints, none by default; DeepSeek caches on its own.
- `geomind check-live` lists every role with its model and fails on a role without a model or an
  Anthropic model id. A test greps the package, evals and docs for Anthropic model ids.

Additive: tool schemas and error texts tell the model what the call needs, so it does not learn
reference forms, sizing ranges, units and state shapes from failures.

- Every argument that takes a stored reference has a JSON Schema `pattern` and a description with
  an example (not enforced by the input model). A wrong reference gets `unknown_name` listing the
  stored references of its kind; `designs.index` and `results.index` are new chat artifacts.
- `size_plant`, `optimize` and `run_study` name each missing search range and give the
  `set_ranges` call that adds it, with the unit of the leaf and no number. `size_plant`'s
  description says sizing reads the ranges and `params.backup`.
- A unit gemini rejects (`save_profile` step `day`, any tool) gets gemini's message plus the units
  gemini accepts, read from `gm.units`.
- `update_state` offers a typed `changes` schema (`op` enum, `path` pattern, `value` over the
  state's models) and a refused change returns the shape expected for its path. The input model
  is unchanged, so every input valid before stays valid.
- Fix: `save_profile` read the case and its files on the event loop; it now reads them in a worker
  thread (`asyncio.to_thread`), as the docs said.

- Fix: the Economist task no longer crashes on a `design.start_result` or `alternatives[].result` that
  is an object. The problem state's design section is typed (`DesignState`); `update_state` refuses an
  object for a reference, and a stored state with one loads converted or under `design.unreadable`.

- The Designer starts from the project's plants: `read_plant(project_plant=...)`, then `build_plant`
  before sizing or searching; a new plant only when none fits, with the reason as an assumption.
  The `DesignLoop`'s first task names the project's plants (none when there are none). The prompt
  shows the size-then-optimise sequence. New offline recording `designer/project_plant`.

## [0.4.1] - 2026-11-02

Additive: models and OpenRouter providers can be chosen by deployment configuration.

- `GEOMIND_CHEAP_MODEL` sets `coordinator_model` and `summarizer_model` (else `FIXED_CHEAP_MODEL`),
  as `GEOMIND_MODEL` already sets `default_model`.
- New setting `provider`, from `GEOMIND_PROVIDER` (comma-separated OpenRouter provider slugs, for
  example `relace/fp4`): `OpenRouter` sends it as `provider: {"order": [...]}`. `None` sends nothing.
- `runtime.load_state` accepts a state stored before a setting was added (`ADDED_SETTINGS`); the new
  setting takes its default, so older runs still resume.

## [0.4.0] - 2026-11-02

Breaking (minor): `name` is now required on `run_study`, `sample_uncertainty` and `sensitivity`.
Additive otherwise: new tools, a new public event, a new hook and protocol; nothing renamed or
removed. Supports gemini `>=0.5,<0.6` (tested on 0.5.1).

- Every study tool (`size_plant`, `optimize`, `sample_uncertainty`, `sensitivity`, `run_study`)
  stores the chat artifact `study/<name>`, written once like `design/`: gemini's `study.json` that
  ran, its result, the designs read and written, the case id, the tool and the versions. `name` is
  now required on `run_study`, `sample_uncertainty` and `sensitivity`, and every study tool returns
  `study: "study/<name>"`. `studies.index` lists the chat's studies without listing artifacts by
  prefix, so `RunStore` is unchanged; `study` is a reference kind of `FileRunStore`.
- Fix: `run_study` stored every run as `design/<plant>_best`, so a second study over a design was
  refused as a changed design. A run is now stored as `design/<study name>_<plant name>`. A taken
  `name` of `optimize`, `size_plant` or a study is refused before the study runs, naming the taken
  design or study.
- New public event `study.recorded` `{run, index, call_id, study, tool, method, designs, best?}`,
  sent once after the artifact is saved; callbacks get `on_study_recorded`.
- New read tools `list_studies` (with `current`: the state's case is still the one the study ran
  on) and `read_study`, given to the Designer, Economist, Analyst and Explainer.
- Unknown event types: `events_from_dicts` skips a type this version lacks and
  `FileRunStore.load_events` uses it, so a newer log opens in an older reader. Every consumer,
  the backend included, must ignore unknown event types. `event_from_dict` still raises.
- `Context.call_id` and `Context.for_call`: a tool knows the call it serves.
- Replay of a log of another geomind version (or with none recorded) keeps the recorded results
  of pure tools, and still compares completions, calls, steps and
  answers: a 0.3.1 log with study calls (no `name`, other outputs) replays. Tools that write the
  state still run.
- A log of 0.3.1 without `study.recorded` loads, replays and exports. Recorded model calls of
  `run_study`, `sample_uncertainty` and `sensitivity` from 0.3.1 lack the new `name`, so the
  recordings of this repository carry one (`families`, `draws`).
- Fix: `Engine.replay` matches a run's recorded results by step and call id, not by call id alone.
  A model that reuses an id in a later step (`explainer/unverified`, `analyst/module_lookup`) no
  longer gets the input of the later call at the earlier step. New test replaying every eval
  recording.
- `UsageLedger` (`spent(project_id) -> Usage`), `MemoryUsageLedger` and `FileUsageLedger` in
  `gd.stores`; `gd.hooks.ProjectBudget(ledger, project_id, max_tokens=None, max_cost=None)` denies
  an LLM call once the project's finished runs plus this run reach a cap. No cap is
  `gd.errors.BudgetError`. Pass it in `gd.Run(hooks=[...])`.
- `geomind run --project-max-tokens` and `--project-max-cost`, valid with `--project`; a live
  `--mode auto` run still needs `--max-cost` or `--max-tokens`.

## [0.3.1] - 2026-11-02

Additive: a new optional event field and a stronger replay; nothing renamed or removed.

- `Engine.replay` replays every nested run of a loop run, not only the root: each nested run runs
  again with a `FakeLLM` of its own recorded completions, and its calls and answer are compared,
  so a difference names the run and its agent. The replayed log has the same runs, steps, LLM
  calls and tool calls. New keywords `replayed=` (a list that receives the replayed events) and
  `workspace=` (and `geomind replay --project`); a run with a project replayed without a workspace
  reuses its nested runs as before. 0.3.0 logs replay unchanged.
- `run.started` records `versions` (`geomind`, `gemini`, `python`) on every run, nested ones
  included; it is not streamed and `public_fields` is unchanged. A 0.3.0 log has none and still
  loads, recovers, replays and exports (the export falls back to `run_manifest.json`).
- The export header reads the versions from the log, so runs of the backend, chats, `gd.Run` and
  evals no longer show "not recorded".
- Fix: the export header showed the first user message of the run, a chat's oldest; it shows the
  last, the run's own request.
- `geomind replay` prints `nested runs reused: ...` when a run with a project is replayed without
  `--project`; a run that starts in a replay with no recorded run to follow raises `ReplayError`.
- `geomind replay` prints one line `versions differ: ...` when a version differs from the recorded
  one; `version_differences(events)` in `geomind.engine.replay` returns the difference.

## [0.3.0] - 2026-11-02

Breaking: geomind runs on gemini `>=0.5,<0.6` (pinned in `pyproject.toml`; a test fails on another
installed version). gemini's problem is a project folder (`case.json`, `economics.json`, `data/`,
`plants/`), pass or fail is `gm.evaluate.verdict`, and a plant is a file with ranges. geomind keeps
no copy of gemini's logic. `gm.evaluate.run_all`, `gm.physics.control`, `gm.data`, `gm.case.roles`
and `gm.plants.validate` are not used anywhere.

Problem state and backend contract:

- `Requirement.case_requirement` (the name of a requirement of the case, `str | null`) replaces
  `Requirement.constraint`; `ConstraintKey` is removed (schema `problem_state.json` and its sample).
- `case_origin` now compares the case's requirements by name (added, removed, changed) and its
  files, `economics.json` included.
- `Workspace.case(project_id)` returns `(case dict, {file name: bytes})` (was `(case dict,
  folder)`); the files are the ones `case.json` names, `economics.json` included, by relative
  name such as `data/demand.csv`.
- `Workspace.plant(project_id)` is removed. `Workspace.plants(project_id)` returns `{file stem:
  plant file dict}` from the project's `plants/*.json`, `{}` without plants. `MemoryWorkspace`
  takes `plants={project: {name: dict}}`; `FileWorkspace` reads the folder; `check_workspace`
  checks both. The backend implements `plants` and the new `case`.
- `RunStore.save_chat_artifact(chat_id, key, data)` and `RunStore.load_chat_artifact(chat_id,
  key)` are new (`FileRunStore` keeps `<root>/chats/<chat id>/artifacts/`; `check_run_store`
  tests them). Artifacts live in the chat, not in the root run: the case files (`case/<path>`), the
  designs, the results, the modules and the cut tool outputs are read by every later message of the
  chat. A run without a chat uses its root run id as the chat id. The per-run methods remain in the
  protocol. `FileRunStore` accepts the key kind `module/<file name>`.
- A design is written once: `design/<name>` with the same content is accepted, other content is a
  `ToolError` that asks for a new name.
- Replay falls back to the recorded chat's artifact space.

Tools:

- Added: `set_ranges(design, ranges, name, options=None)` (search ranges and options on a copy of a
  design, stored as `design/<name>`), `run_study(designs, method, objective=None, evaluations=None,
  seed=None, samples=None, metrics=None, prepare=None)` (one `gm.Study` over several designs,
  `method` is `run`, `minimize`, `sample` or `sensitivity`; each run's plant is stored as
  `design/<name>_best`), `write_module(name, code)`.
- `set_case(source, changes, requirements, economics)`: `requirements` and `economics` are new
  arguments; `save_profile` writes the demand file in one step.
- `read_case` sections `economics` and `schema` are new (the case, its economics or gemini's
  schema).
- `read_plant(design, plant_class, project_plant)`: `plant_class` and `project_plant` are new (at
  most one of the three; none reads the project's only plant file, several plant files need
  `project_plant`). It returns `{plant, ranges, options, issues, checked_against}`; `issues` is
  `gm.check(plant, case)` against the state's case (`checked_against: "case"`) or `plant.check()`
  (`"plant"`), and `missing_parameters` is gone. `ranges` are in display units.
- `build_plant(plant file, name)` builds with `gm.Plant.from_dict` (no `gm.plants.validate`),
  returns `{design, checked_against, issues}`, and a bad file is gemini's error.
- `list_plants` gains `roles` (`gm.plants.roles()`) and `project_plants` (the project's plant file
  names); `capabilities` carries `ranges`.
- `evaluate_module` returns display units (`units="display"`: MW, Pa for pressure) and takes
  `state` and `dt`; every inlet needs a `fluid`.
- `simulate` summary: `report`, `verdict` and `unmet` (requirement checks that failed); `constraints`
  and `violated` are gone. A window cuts the case's time too.
- `check_results` returns `{feasible, reasons, requirements, failures, metrics}`; `passed`,
  `constraints` and `balances` are gone. `feasible` and `reasons` are `gm.evaluate.verdict`.
  `gd.verify.verify(plant, results, case)` returns `{passed, checks, failures, metrics}`; a
  failure carries `kind`.
- `size_plant(design, name)` loses `backup` (the policy is `params.backup` of the plant).
- `optimize(design, objective, evaluations, seed, name)` loses `variables` and `constraints`:
  variables are the design's ranges (`set_ranges`), constraints are the case's requirements; `seed`
  is required.
- `sample_uncertainty(design, metrics, samples, seed)`: `count` is renamed `samples`.
- `compare` reads display values from each run's `Report.to_dict()`; no column labels are parsed.
- `test_module(name, example=None)` moved to `modules.py` and checks the stored `module/<name>.py`
  with `gm.modules.check` in the gemini sandbox (`gemini-sandbox:<gm.__version__>`, no network);
  it was `test_module(path)` over a file, a stub. A local sandbox is `not_allowed`. New skill
  `writing-a-gemini-module` flow: `write_module`, then `test_module`.
- Study tools: `shown_value`, `shown_values`, `to_quantities` and `check_plant_variables` are
  removed; the study tools time out after 900 s.

Agents and loops:

- `CompareLoop` is added (`geomind/loops/compare.py`, name `compare`): the Designer builds one
  design per plant family, `run_study` ranks them, then the design loop's Verifier, Economist and
  Explainer. `Route.loop` and `LOOPS` hold `tool`, `design` and `compare`; `geomind run --loop`
  takes `compare`.
- `MakerCheckerLoop` is removed.
- The Designer gains `set_ranges`, `run_study`, `write_module` and `test_module`; the Economist
  gains `run_study`; the Analyst gains `write_module` and `test_module`. The agent chooses a
  setting the request does not give (backup, objective, evaluations, seed, samples, ranges) and
  records it as an unconfirmed `agent` assumption.

Command line and evals:

- New `geomind check-live [--max-tokens N] [--max-cost USD]`: checks the role models against
  OpenRouter's public list and what a first live run needs.
- `geomind run --mode auto` with OpenRouter and no spending cap is refused; a recording is exempt.
- `geomind show --format md` is the competition export (`geomind/export.py`): the request, the
  versions and models, every LLM call with the messages added since the last call, each agent's
  prompt once, and the token tables by agent and step. Two runs of one recording export the same
  text.
- Eval task field `max_steps` (caps the steps of every agent, for a tight-budget task); new suite
  `compare`; `python -m evals.run --report` writes `evals/reports/summary.md` (a table per loop),
  and `--agent X` writes `evals/reports/X.md`.
- The eval projects are copies of gemini's examples in gemini's layout (`case.json`,
  `economics.json`, `data/`, `plants/`): `hackathon`, `hackathon_plant`, `shallow_district` and the
  variants `more_cooling`, `colder_reservoir`, `higher_gas`, `user_profile`. The old `doublet`
  project is removed.

## 0.2.0 (unreleased)

Breaking: geomind runs on gemini `dev` (cca153b8), whose problem is a `gm.Case` (`case.json` and a
demand CSV). gemini does every engineering job (checks, costs, sizing, search, uncertainty);
geomind keeps no copy of that logic and no default for an engineering assumption.

Problem state and backend contract:

- `ProblemState.case` (a case dict as `case.json` holds it, or `null`) replaces `ProblemState.brief`;
  `case` replaces `brief` among the keys a patch may change. gemini's `Case.from_dict` validates it.
- `Requirement` is `{id, text, constraint, status}`: a numeric requirement is a constraint of the
  case, and `constraint` names it by `{on, quantity, over, when}` (`ConstraintKey`), never by its
  place in the list. `metric`, `target` and `tolerance` are gone.
- `ProblemState.case_origin` (`{case, files}` or `null`): the case the user or the project gave,
  and `case_origin` among the keys a patch may change. `update_state` refuses `/case` and
  `/case_origin` (`not_allowed`); only the case tools write them.
- New protocol method `Workspace.case(project_id) -> (case dict, folder) | None`, implemented by
  `MemoryWorkspace` (`cases=`) and `FileWorkspace` (`<root>/<project>/case.json`), checked by
  `check_workspace`.
- Run-store artifact keys: `case/<file name>` (bytes, the files a case names) is added and
  `profile/<name>` is removed. A run keeps `<id>.results`, `<id>.plant` (the plant dict) and
  `<id>.case` (the case dict it ran on) and `<id>.files` (`{file name: sha256}`) beside
  `result/<id>`, and each case file once by its content as `<sha256>.file`; `<id>.run` is gone. An
  older run reads the files it ran on, not a file overwritten later under the same name, and the
  case and files it stores are the ones it read (`ran_case`), not the state's after a parallel
  `set_case`.
- Removed from `geomind.context`: `Brief`, `PRESETS`, `preset`, `with_changes`. No preset of any
  case is left in the package.

Tools:

- Removed: `set_brief`.
- Added: `case_changes()` and `accept_case()` (the design loop's driver only); `set_case` takes
  `source="origin"`.
- Added: `set_case(source=None, changes=None)` (a JSON merge patch on the case, `source="project"`
  for the project's case), `read_case(section=None)`, `size_plant(design, backup, name)`,
  `sensitivity(design, metrics)`, `compare(references, by)`.
- `save_profile(name, values, unit, start, step, service)` writes the profile into the case's demand
  file (`quantity` became `service`).
- `optimize(design, objective, variables, evaluations, name, constraints=None)` and
  `sample_uncertainty(design, metrics, count, seed)` are real (`gm.study.minimize`, `sample`), no
  longer stubs; `budget`, `samples` and `distributions` are gone (distributions are the case's).
- `simulate` loses `profile`: the demand is the case's. `read_profile(service, start, end)` reads
  the case's demand (`name` became `service`); `list_profiles` lists the case's services.
- `check_results` loses `limits` (a limit is a case constraint) and returns gemini's report;
  `estimate_costs` loses `assumptions` (they are the case's).
- `read_plant` returns `{plant, missing_parameters}` and reads a stored design, the project's plant
  or a gemini plant class; the `example/` and `template/` sources are gone. `build_plant` validates
  with `gm.plants.validate`. The input bridge `apply_inputs` is gone: `Plant.from_dict` restores
  inputs.
- `read_result` takes ISO times for `start` and `end`.

Verification: `gd.verify.verify(plant, results, case)` (was `requirements`, `limits`, `brief`);
pass or fail is gemini's report, and each failure carries the domain that should fix it.
`not_given`, `not_assessed`, the reservoir check and the operating-days reason are gone.
`verify_design` fails a result whose case differs from the state's (`result_off_case`), and a case
that differs from the one the user gave (`case_changed`, with the changes) until the user approves
it: the design loop asks, then accepts the case or sends the designer back to it. The Verifier
reports case changes, a stale result and unconfirmed assumptions, and the Explainer reads that
report and the case. The Designer and the Economist choose a study setting the request does not
give (backup, objective, variables, evaluations; count, seed) and record it as an unconfirmed
`agent` assumption with its reason, instead of stalling; the Designer records
`design.start_result` and `design.alternatives`, and the Economist compares only those.

Routing: `Route` loses `brief` (nothing read it; the loop reads the user's message), and
`Route.loop` and `LOOPS` hold only the built loops, `tool` and `design`, so a live request is never
routed to a stub; `geomind run --loop` takes the same two.

Agents and loops: the design loop's request is the run's own message (the last user message), not
the first message of the chat, and `Run.load` keeps a design loop's `max_rounds`. The hackathon
skill note is gone. The DesignLoop runs Designer (size, simulate,
self-check, optimise) → Verifier (once, on the final design) → Economist → Explainer, and asks the
user for a case before designing when the state has none or it has no demand.

Tools: `optimize` refuses a `case` variable (the case is the user's); the study tools time out
after 900 s with a `timeout` result; `compare` keeps gemini's own value when a column label is not
`name [unit]`, instead of failing. A file the project's case names but does not have is an `unknown_name` error that names
it, and an empty case file is a file, not a missing one.

Tests: no fast test of a gemini tool runs a year in its body; module fixtures run each year,
window and tool call once and cache it, so the 1 s budget holds under parallel load.

Evals: eval projects are copies of gemini's example cases (`evals/projects/`); `challenge2` tasks
are case variants. The eval schema and recordings follow the new tools.

## 0.1.1 (unreleased, superseded by 0.2.0)

Additive changes only: a new key of the problem state, a new tool and new output fields. Nothing the backend uses
changes shape, and an existing caller sees the same behaviour.

- `ProblemState.brief`: a `Brief` (or `null`), the brief as data, and `brief` among the keys a
  patch may change. The backend stores it with the state; an older state without it loads as
  `null`. `geomind.context` exports `Brief`, `PRESETS`, `preset` and `with_changes`; the one preset
  is `hackathon_2027`.
- New tool `set_brief(preset=None, changes=None)` (effect `write`).
- `simulate` and `check_results` use the state's brief; without one they keep the hackathon numbers
  as before. `simulate`'s summary adds `brief`, `demand` and `rules`, and its result id now covers
  the rules. `check_results` and `gd.verify.verify` add `not_given` and `brief`; `verify` takes
  `brief=None`.
- New tool `save_profile` (effect `write`): a demand profile the user gave, stored as
  `profile/<name>` in W. `list_profiles` and `read_profile` include stored profiles, and
  `simulate` and the brief's demand take them. A store must accept the key `profile/<name>`;
  `check_run_store` tests it.
- Verification checks each doublet against the reservoir values the brief gives, and
  `verify_design` fails a result that ran on another demand or rules than the brief's
  (`result_off_brief`); `simulate` keeps `<id>.run`.
- The eval format adds the `verified` criterion and `equals` on the `state` criterion; the suite
  `challenge2` runs through the design loop.
- `Usage.cached_tokens`: input tokens read from OpenRouter's prompt cache, which an Anthropic
  model now gets on the agent's system prompt (setting `prompt_caching`, on by default). The
  public usage JSON of `step.finished` and the run log keeps its three fields; the schemas list
  the new one as optional.
- `geomind run --max-tokens N --max-cost USD`: a spending cap over the whole run. `TokenBudget`
  and `CostBudget` now count the runs above a nested run too (a fix: before, a delegate saw only
  its own usage, so a long delegate could pass the cap).
- `RunResult.usage` includes the routing call's tokens, as the run's log always did.

- `geomind run` takes `--loop`, `--project`, `--recording` and `--record`: `--loop` chooses the loop
  and skips the routing, `--recording` runs from recorded completions and `--record` writes them.
- `gd.Run.start` asks the `Coordinator` first when no agent or loop is given; the routing call is a
  nested run of the run, logged before it starts. The backend still names no loop and no agent.
- `read_plant` reads `example/<Name>` and `template/<name>` and returns the plant's spec beside its
  description; `check_results` returns `failures` and `not_assessed` beside `passed` and `checks`;
  `estimate_costs` returns `lcts`.

## 0.1.0 (2026-10-31)

The first frozen state.

- Every interface the backend and the agent developer depend on is pinned by snapshots in
  `tests/unit/snapshots/`, and the exchanged documents have JSON schemas and samples in
  `geomind/schemas/`.
- The full tool catalogue up to S4 exists; tools not built yet raise `gd.errors.NotImplementedYet`
  and give an error result with `code: "not_implemented"`.
- Tool error results take gemini's Problem shape, `{"error": {path, code, message, suggestions}}`.
  The former `{"error": {class, message}}` is gone.
- `read_result` returns gemini's Value shape, and a summary without `path` or `field`.
- `LOOPS` holds `tool`, `design`, `makerchecker` and `compare`; a route to a loop not built yet ends
  the run with `stop_reason="not_implemented"`.
- `gd.verify.verify` and `gd.hooks.Verified` have their final signatures.
- `FileWorkspace.plant` loads through `gm.plants.from_dict`, and `FileRunStore` accepts the artifact
  keys `design/<name>` and `result/<id>`. `gd.testing.check_run_store` now checks them.

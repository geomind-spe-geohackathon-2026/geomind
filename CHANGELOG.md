# Changelog

`gd.__version__` follows semver below 1.0, the same rule as gemini: a breaking change to a frozen
interface raises the minor version, and an addition or a fix raises the patch version. The rule and
the list of frozen interfaces are in [.claude/docs/api.md](.claude/docs/api.md#frozen-interfaces).

## 0.2.0 (unreleased)

Breaking: geomind runs on gemini `dev` (cca153b8), whose problem is a `gm.Case` (`case.json` and a
demand CSV). gemini does every engineering job (checks, costs, sizing, search, uncertainty);
geomind keeps no copy of that logic and no default for an engineering assumption.

Problem state and backend contract:

- `ProblemState.case` (a case dict as `case.json` holds it, or `null`) replaces `ProblemState.brief`;
  `case` replaces `brief` among the keys a patch may change. gemini's `Case.from_dict` validates it.
- `Requirement` is `{id, text, constraint, status}`: a numeric requirement is a constraint of the
  case, and `constraint` is its index in `case.constraints`. `metric`, `target` and `tolerance` are
  gone.
- New protocol method `Workspace.case(project_id) -> (case dict, folder) | None`, implemented by
  `MemoryWorkspace` (`cases=`) and `FileWorkspace` (`<root>/<project>/case.json`), checked by
  `check_workspace`.
- Run-store artifact keys: `case/<file name>` (bytes, the files a case names) is added and
  `profile/<name>` is removed. A run keeps `<id>.results`, `<id>.plant` (the plant dict) and
  `<id>.case` (the case dict it ran on) beside `result/<id>`; `<id>.run` is gone.
- Removed from `geomind.context`: `Brief`, `PRESETS`, `preset`, `with_changes`. No preset of any
  case is left in the package.

Tools:

- Removed: `set_brief`.
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
`verify_design` fails a result whose case differs from the state's (`result_off_case`).

Agents and loops: the hackathon skill note is gone. The DesignLoop runs Designer (size, simulate,
self-check, optimise) → Verifier (once, on the final design) → Economist → Explainer, and asks the
user for a case before designing when the state has none or it has no demand.

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

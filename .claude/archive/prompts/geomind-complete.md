# geomind: finish it on gemini 0.5 (the frozen API)

You work in the geomind repository (the current folder). gemini is the sibling folder `../gemini`, installed editable from `pyproject.toml` (`path = "../gemini"`). Work directly on `main` of geomind, commit after each section, push `origin main` at the end. Never edit, commit to or push gemini.

This prompt is self-contained apart from the two repositories. Read what it points at in `../gemini`; do not look for files anywhere else.

## 0. Goal and fixed rules

**Goal.** geomind `main` (`eeb80d9`, version 0.2.x) runs on gemini `b1db49f`. gemini then changed its inputs and public API in 0.3.0, 0.4.0 and 0.5.0, and froze its API at 0.5.0: from 0.5.0 on, gemini stays backward compatible. On gemini 0.4.0, geomind has 80 failing tests and 101 errors. Make geomind run on gemini 0.5.x, using gemini's new pieces in place of geomind's workarounds, and finish everything geomind still lacks for the competition: comparing alternatives, agent-written modules, chat-scoped artifacts, the competition export, the evals report, and a ready live run. This is the last big geomind prompt.

**gemini is the source of truth.** geomind adapts to gemini, never the other way. Where gemini does a job, geomind calls it and keeps no copy. Where gemini lacks a general capability, do not work around it with private names or a re-implementation: write it to `.tmp/adapt05/gemini-requests.md` (what, why, the general form) and make geomind raise a clear `ToolError` (code `not_implemented`) until gemini has it.

**What gemini 0.3 to 0.5 changed (read these first, in full):**

- `../gemini/CHANGELOG.md`: the sections `[0.3.0]`, `[0.4.0]` and `[0.5.0]` (or `[Unreleased]` if 0.5.0 is not tagged in the file yet). The 0.3.0 tables "Every changed name, old and new" are the mapping you work from.
- `../gemini/.claude/docs/inputs.md`, sections 1 to 4 and 10: the four project files and where every value lives.
- `../gemini/examples/hackathon_2026/` and `../gemini/examples/shallow_district/` (`case.json`, `economics.json`, `data/*.csv`, `plants/*.json`, `study*.json`), and `../gemini/examples/hackathon.py`, `quickstart.py`, `uncertainty.py`.

In short:

- A project is four kinds of file: `case.json` (`format`, `kind`, `name`, `time`, `site`, `demand`, `utilities`, `economics` as a file name, `requirements`, optional `initial_state`), `economics.json`, plant files (`kind: plant`, `format: 1`, `type`, `size`, `params`), and an optional `study.json`. A series is a CSV whose first column is `time`, named from a leaf as `{"unit", "file", "column"}`. Every leaf is `{"value", "unit"}`, with an optional `range`, `options` or `uncertainty`.
- `gm.Case.from_dict(data, files={name: bytes})` reads the series and economics from memory. No folder is needed.
- Requirements have a `name` (`gm.case.Requirement`). There are no `Choices`, `Constraint` or `Assumptions` any more.
- The search variables are the `range` and `options` leaves of the plant file (`plant.set_range`, `plant.set_options`). `gm.study.minimize(plant, case, objective, evaluations, seed)` has no `variables` or `constraints` argument and no default. `gm.study.size(plant, case)` reads `params.backup` of the plant. `gm.study.sample(plant, case, metrics, samples, seed)`.
- `gm.evaluate.verdict(plant, case, results)` is the one answer to feasibility: requirements, failed steps, numerical balances and module bounds. `report`, `compare` and the study all use it.
- `gm.check(plant, case)` runs first in `simulate` and every study function. `plant.check()` lists a plant's issues and never raises. `gm.plants.validate` and `missing_parameters` are gone.
- `gm.Study` (`study.json`): cases × plants × a method (`minimize`, `sample`, `sensitivity`), with `prepare: ["size"]`, `objective`, `metrics`, `evaluations` and `seed`, returning a ranked `StudyResult`.
- `gm.call(..., units="si" | "display")` requires `units`. `gm.Stream` requires `fluid`, since the runtime default fluid is gone. `gm.case.roles` is now `gm.plants.roles`. `gm.data.*` is now `gm.case.from_csv` / `from_values`. `gm.plants.capabilities()[cls]["ranges"]` replaces `choices`.
- `Best`, `Sample`, the search history and the sizing notes are in display units.
- The examples moved from `inputs/examples/<name>/` to `examples/<name>/`.
- In 0.5.0: `gm.evaluate.run_all` is merged into `verdict`; `gm.physics.control` and `gm.physics.diagnostics` move out of `physics`; the `gm.evaluate.call_*` names may change. Check the 0.5.0 changelog for exactly what moved.

**Standing rules (all apply):**

- **General, not the competition.** The hackathon is one sample. No hackathon numbers, names or defaults in `geomind/`. Test every changed path on both example projects.
- **No default values in package code** for engineering settings. Agent decisions are different: when the request or the project does not give a value the agent must choose (backup policy, objective, evaluations, seed, samples, ranges), the agent chooses it and records it as an assumption (`source: agent`, `confirmed: false`, one-line reason). This rule is already in geomind's prompts; keep it.
- **Units.** Every dimensional value goes to gemini as a `Quantity` or `{"value", "unit"}`, never a bare number, and never a unit string such as `"2500 m"`.
- **Only gemini's public API** (`gm.__all__` and the documented namespaces). Keep the quality test that fails on a private gemini name.
- **I/O naming:** `from_<format>` / `to_<format>`.
- **Code quality:** simple and readable, nesting ≤ 3, functions about ≤ 40 lines, flake8 max-complexity 10, guard clauses, full-word names, no dead code, no compatibility aliases. **No comments inside code** except the fixed section headers and tool directives; explanations go in docstrings. Write a failing test before each bug fix.
- **Tests.** Use the development profile while working (`make test`: changed files and their importers, parallel, under 300 s). Run `make test-all` and `make lint` once before the final push. Never run the slow tier in a loop. No fast test over about 1 s: simulate in session fixtures, never inside a timed test call.
- **Docs in the same commit.** Every change updates `.claude/docs/` (and AGENTS.md "Start here" if needed).
- **Temporary files** go in `.tmp/adapt05/` (git-ignored).
- **No live LLM calls.** Evals stay offline. Recordings stay hand-written, and each file says so. The numbers in their tool results come from real gemini runs.
- **Speak up.** Put anything missing, risky or needing Sahand in the final report.

## 0b. How you work: coordinator only

You (the main session) only plan, dispatch subagents, review their diffs and short summaries, merge, and run the tests. You never edit many files or read large files yourself.

- Workers use a lighter model: `sonnet` for implementation, `haiku` for read-only search.
- Each implementation worker gets its own worktree (`git worktree add ../geomind-<section> -b adapt05-<section>`, local only, never pushed) and a disjoint list of files it owns. A change it needs in a file it does not own goes into its report instead.
- Each worker writes details to `.tmp/adapt05/<section>.md` and returns at most 15 lines: what changed, tests run, open points.
- You merge each branch into `main`, run `make test`, then remove the worktree and the branch.

## 1. Setup and inventory (phase 1)

1. In `../gemini`: `git fetch origin && git checkout dev && git pull --ff-only`. Check `python -c "import gemini as gm; print(gm.__version__)"`. **If it is below 0.5.0, stop and report**: the API is not frozen yet. Record the hash and the version in `.tmp/adapt05/setup.md`.
2. Recreate the venv if its launchers point at an old folder, then `make install`.
3. Baseline: `make test`, grouping the failures by cause in `.tmp/adapt05/baseline.md`.
4. Inventory (haiku): every gemini name, file path and return key geomind uses, in `geomind/`, `tests/`, `evals/`, `examples/`, `scripts/`, the prompts and skills, and `.claude/docs/`. For each: file:line, old, new (from the changelog), and whether the meaning changed. List every workaround geomind keeps for a gemini gap that 0.3 to 0.5 closed: the temporary case folder in `build_case`, `READ_UNITS` and the unit map for `gm.call`, `shown_values` parsing column labels in `compare`, the "store the case as given" rule because of `Case.to_dict`, the three-step short-demand route in `save_profile`, geomind's own pass rule (`sound` in `verification.py`), and `minimize`'s `constraints` and `variables`. Write `.tmp/adapt05/inventory.md`.

## 2. Section A: the project files in the state and the workspace (phase 2, one worker)

Owns `geomind/context/`, `geomind/stores/`, `geomind/testing/`, `geomind/tools/gemini/case.py`, `geomind/tools/gemini/origin.py`, `geomind/tools/gemini/stored.py`, `geomind/schemas/`, and their tests.

1. `ProblemState.case` holds the `case.json` dict as given (header included). The files it names (series CSVs and `economics.json`) are run artifacts stored by content (keep `<sha256>.file`), and the case built with `gm.Case.from_dict(data, files={name: bytes})`. Delete the temporary folder.
2. `Workspace.case(project_id)` returns `(case dict, {name: bytes})` for every file the case names, `economics.json` included, or `None`. This replaces the folder. Update the protocol, the memory and file implementations, and the conformance checks. Add `Workspace.plants(project_id)` (plant file dicts by name) only if the backend contract needs it; otherwise keep `Workspace.plant`, now returning a gemini plant from a plant file.
3. `set_case(source=None, changes=None, requirements=None, economics=None)`:
   - `changes` is a JSON merge patch on the case dict, except `requirements` and `economics`.
   - `requirements` is `{name: requirement dict | null}`: add or replace by name, or remove with `null`. This closes review item 13 (one requirement no longer resends the list).
   - `economics` is a JSON merge patch on the content of `economics.json`, stored as a new content file.
   - gemini validates the result with `Case.from_dict` and `case.check()`. A rejected case comes back with gemini's path and message, and nothing is stored.
4. `case_origin` and the approve/restore flow stay, and now also compare the content of every file the case names (economics and series), not only the dict. A change of economics is a change of the case.
5. `Requirement` in the problem state names a case requirement by its `name`. Replace the `{on, quantity, over, when}` match.
6. `save_profile` writes a CSV whose first column is `time` and points the service's `power` leaf at it (`{"unit", "file", "column"}`), through `gm.case.from_values`. If the case's `time` must follow the profile, do that in the same call (one step), using what gemini offers. Delete the three-step route. If gemini cannot do it, write a request.
7. `read_case(section=None)`: the case dict, one section, `economics` (the economics content), or `schema` (`gm.Case.schema()`, plus `gm.case.Economics.schema()` under `economics_schema`).
8. Tests: both example projects load through the workspace. Add or remove a requirement by name. An economics change trips `case_origin`. A 30-day user profile is one `save_profile` call.

## 3. Section B: plant tools (phase 3, one worker)

Owns `geomind/tools/gemini/plants.py`, `catalogue.py`, and their tests.

1. `read_plant(design=None)`: a stored design, the project's plant, or a plant class by name. Returns the plant file dict (`to_dict(structure=...)` as gemini's docs say for a file), `ranges` (`plant.ranges`) and `options`, and `issues`. With a case in the state, the issues come from `gm.check(plant, case)`: `plant.check()` alone lists values such as `d0.gradient` as missing even though the case fills them. Without a case, they come from `plant.check()`, marked as such. Both replace `missing_parameters`.
2. `build_plant(plant, name)`: the input schema is `gm.plants.schema()` (the plant file form). Build it with `gm.Plant.from_dict`, return its issues as tool results, and store it as `design/<name>`.
3. New `set_ranges(design, ranges, options=None, name)`: put a search range on plant leaves (`size.doublets`, `params.depth`, `params.<unit>.capacity`, ...) with `plant.set_range` / `set_options`, and store it as a new design. The Designer uses it before `optimize`. Check each leaf against `gm.plants.capabilities()[cls]["ranges"]` so the model gets gemini's error.
4. `list_plants`: names, summaries, and `capabilities()` (now with `ranges`) and `gm.plants.roles()`.
5. `evaluate_module`: `gm.call(..., units="display")`. Delete the unit map. An inlet without a fluid gets gemini's `missing_value`, and the tool description says that every inlet needs `fluid`.
6. Tests on the plant files of both examples.

## 4. Section C: run tools (phase 3, one worker)

Owns `geomind/tools/gemini/runs.py`, `results.py`, and their tests.

1. `simulate`: `gm.simulate(plant, case, ...)`. gemini's `check` issues before the run come back as a tool result, not an internal error. Failed steps are rows, so the run always finishes.
2. `list_profiles` / `read_profile` read the case's `demand` services from their `power` series, through public names only.
3. `read_result`: on 0.4.0, `Results.get` and `summary` take only a `{quantity: unit}` map, not `"display"` (checked). Keep geomind's small map for these two calls, unless 0.5.0 added `"display"` there. Write the gemini request: `units="display"` on `Results.get`/`summary`, as on `gm.call` (an addition, so allowed after the freeze).
4. Tests: simulate on both projects, a window, a user profile, and a case with a missing file.

## 5. Section D: verification and assessment (phase 3, one worker)

Owns `geomind/tools/gemini/assessment.py`, `verification.py`, `geomind/verify/`, and their tests.

1. Pass or fail is `gm.evaluate.verdict(plant, case, results)` and nothing else. Delete geomind's own rule (`sound`, the balance combination, `balances()`); review item 17 is closed by gemini. `check_results` returns the verdict, its reasons (by `kind`: requirement, failed_step, numerical, bound), `report["requirements"]` and the metrics, in display units.
2. Failure routing by domain reads the verdict's reasons: a requirement by its `on` role (doublet → subsurface, a service supply → sizing, other → surface), a failed step or bound by the unit it lies in, numerical → coupled.
3. `estimate_costs` and `compute_kpis` call the costs without `discount_rate` or `lifetime` (economics owns them). The cost part `lifetime_years` is now `analysis_period`.
4. Keep the geomind process checks in `verify/design.py` (stale result, result off the case, case changed against `case_origin`).
5. Tests: the passing design of the hackathon project passes; the 15 MW cooling variant fails on a requirement; a failed step fails as `failed_step`.

## 6. Section E: study tools (phase 3, one worker)

Owns `geomind/tools/gemini/study.py`, the tool registrations in `geomind/tools/gemini/__init__.py`, and their tests.

1. `size_plant(design, name)`: `gm.study.size(plant, case)`. The backup policy is `params.backup` of the plant, so the `backup` argument is removed. The Designer sets it in the plant and records it as an assumption.
2. `optimize(design, objective, evaluations, seed, name)`: `gm.study.minimize`. The variables are the design's ranges, so the `variables` and `constraints` arguments are removed (requirements are the case's). Return `best` (display units, with the plant), `feasible`, the number of trials, and the stored design.
3. `sample_uncertainty(design, metrics, samples, seed)` and `sensitivity(design, metrics)`: rename `count` to `samples`.
4. New `run_study(designs, method, objective=None, metrics=None, evaluations=None, seed=None, samples=None, prepare=None)`: builds a `gm.Study` from the state's case and the stored designs (as `Study.from_dict` with `files`), runs it, and returns gemini's ranked result in display units. Each plant's best is stored as a design. This is how alternatives are compared: one study over several topologies. A method setting the method needs and the model left out is gemini's error.
5. `compare(references, by)`: `gm.evaluate.compare` over reports. Use `Comparison.to_dict()` in display units if gemini gives them, and delete the column-label parsing.
6. Keep the 15-minute time limit on the study tools.
7. Tests on the shallow project (fast) and one hackathon smoke test with a tiny budget, all in session fixtures.

## 7. Section F: agents, prompts, skills and loops (phase 4, one worker)

Owns `geomind/agents/`, `geomind/prompts/`, `geomind/loops/`, `geomind/run.py`, and their tests.

1. Every prompt and skill uses the new tools and arguments, and the words of the new files: requirements, economics, ranges, backup in the plant.
2. Designer: `read_case`, then for each family `read_plant` of a class, `build_plant` (with `params.backup`), `set_ranges`, `size_plant`, `simulate`, `check_results` (self-check), `optimize`, `simulate` the best. With two or more buildable families, compare them with `run_study` (method `minimize`, `prepare: ["size"]`) and keep the best feasible one. Record the sized start, the alternatives and the study result in the state. Each setting it chose is an assumption.
3. Economist: costs from economics, `compare` or the `run_study` ranking for the alternatives the Designer recorded, `sample_uncertainty` (`samples`, `seed`), `sensitivity`.
4. Verifier: `check_results` once on the final design, plus the process checks (case changes, a stale result, unconfirmed assumptions).
5. Loop order stays: Designer → Verifier once → Economist → Explainer, and only a Verifier failure goes back.
6. **CompareLoop (Challenge 1 "compare alternatives").** With `run_study`, build it as a thin loop: a `DesignLoop` whose Designer is asked for several families and compares them with one study. The ranked table goes to the answer. Re-add `compare` to `LOOPS` and `Route` only when it works end to end offline. MakerCheckerLoop: delete it (the DesignLoop is already maker and checker), with its tests and docs.

## 8. Section G: evals, fixtures, examples (phase 4, one worker)

Owns `evals/`, `tests/fixtures/`, `examples/`, and the e2e tests.

1. Eval projects are the two gemini examples copied as files (case, economics, data, plants) into `evals/projects/`, and the variants are new case or economics files: a 15 MW cooling peak, a 25 K/km gradient, a 30-day user profile, and one economics variant (a higher gas price). Paths come from `../gemini/examples/`, never `inputs/examples/`.
2. Re-record the hand-written recordings with the new tool arguments. The numbers come from real gemini 0.5 runs.
3. Bring back eval tasks for the Verifier and the Economist, run through the loop, and one tight-budget variant. Add one compare task (two or three topologies, one study).
4. The offline `geomind run --loop design` passes on both projects. The example under `examples/` runs.

## 9. Section H: version, contract, docs (phase 6, last)

1. geomind `0.3.0` (breaking): `scripts/snapshot_api.py`, schemas and samples regenerated, and `CHANGELOG.md` listing every removed, renamed and added tool, argument, state key and `Workspace` method.
2. Pin the gemini range geomind supports: `gemini-geothermal-suite-open>=0.5,<0.6` in `pyproject.toml` (the path source stays), and a test that fails on an unsupported `gm.__version__`. Update any sandbox image or Docker file that names a gemini version.
3. Update `.claude/docs/` (`context.md`, `tools.md`, `api.md`, `contracts.md`, `evals.md`, `testing.md`, `plan.md`), and remove from `plan.md` every gemini request that 0.3 to 0.5 closed.
4. Quality tests: no private gemini name; none of the removed names (`gm.data`, `gm.case.roles`, `gm.plants.validate`, `missing_parameters`, `Constraint`, `Choices`, `Assumptions`, `inputs/examples`, `run_all`, `backup=` on size, `variables=` on minimize); no hackathon figure in `geomind/`.

## 10. Section I: chat-scoped artifacts (phase 5, one worker)

Owns `geomind/stores/run.py`, `geomind/engine/session.py` (the artifact calls only), `geomind/testing/conformance.py`, and their tests.

Problem (found and reproduced in the last round): the problem state is kept per chat, but artifacts (`<sha256>.file`, `design/<name>`, `result/<id>`, `<id>.*`) are kept per root run. A second message of the same chat holds the case in its state, but cannot read its demand file, nor a design or result the state names.

Design (approved by Sahand on 2026-11-02; it is an addition to the backend contract, so list it for the backend in the report):

1. Add `RunStore.save_chat_artifact(chat_id, key, data)` and `load_chat_artifact(chat_id, key)`. Keep the run-scoped methods for what is really per run (logs).
2. Every artifact the problem state can name lives in the chat's space: case files by content (`<sha256>.file`), designs, results and their parts. A run without a chat (CLI `run`, tests) uses its root run id as its chat id, so nothing changes for it.
3. Content-addressed keys never collide. `design/<name>` is written once per name: a second write of the same name with other content is a `ToolError` that asks for a new name, so an old result never points at a changed design.
4. The memory and file stores and the conformance checks implement it. Test: two runs of one chat; the second reads the first's case files, design and result.

## 11. Section J: agent-written modules, `test_module` (phase 5, one worker)

Owns `geomind/tools/gemini/modules.py` (new; move `test_module` there), `geomind/sandbox/`, the `writing-a-gemini-module` skill, and their tests.

Challenge 1 asks the agent to fill missing models. gemini gives the pieces: `gm.modules.check` (the former `gm.testing.check_module`), the module author contract (`forward(self, inputs, inlets, state)`, `update(...)`, a class with a `category` registers itself), and `docker/sandbox.Dockerfile` with `make sandbox-image` (image `gemini-sandbox:<version>`).

1. `write_module(name, code)` stores an agent-written module file as an artifact `module/<name>.py`. `test_module(name)` runs `gm.modules.check` on it inside `DockerSandbox` with the `gemini-sandbox:<gemini version>` image, never in the harness process, and returns gemini's report (passed, problems with path and message).
2. The `writing-a-gemini-module` skill is written from gemini's module guide (`../gemini/.claude/docs/` module and contract pages), and is general: contract, categories, ports, units, no defaults, the check.
3. The Analyst and the Designer get `write_module` and `test_module`. When a family needs a model gemini lacks, the Designer writes it, tests it, and records the family as `blocked: module written and tested, not usable in a plant run yet`. Running a plant with an agent-written module would need simulate in the sandbox, which is out of scope. Say so in the report.
4. Tests: the docker tier runs one real check of a small, correct module and one broken one. The fast tier uses a fake sandbox.
5. The local sandbox stays refused for agent code.

## 12. Section K: the competition export and the evals report (phase 5, one worker)

Owns `geomind/cli.py` (`show` only), `evals/run.py`, `evals/reports/`, and their tests.

1. The competition asks for the agent log: prompts, answers and token usage. `geomind show <run> --format md` must give, in this order:
   - a header: the request, the loop, the gemini and geomind versions, and the models by role;
   - every LLM call in order: the agent, the model, the messages the call added (task, tool results in short), the assistant text and tool calls, and the tokens (in, cached, out) with the cost;
   - every agent's system prompt once, in an appendix;
   - the token tables by agent and by step, and the totals.
   A test runs the scripted hackathon design and checks every part. The export of a replayed run equals the original.
2. `evals/reports/summary.md` compares `ToolLoop`, `DesignLoop` and `CompareLoop` on every task: criteria met, steps, tool calls, tokens, cost and time. MakerCheckerLoop is deleted (section 7). It is regenerated by `python -m evals.run --report` and checked in.

## 13. Section L: live run readiness (phase 5, coordinator)

No live call is made here (there is no key). Make the first live run one command:

1. `geomind check-live` (or a flag of `run`): it checks that `OPENROUTER_API_KEY` is set, that every model id of every role is in OpenRouter's model list (one free list call; skip it with a clear message when there is no network), and that a cap (`--max-cost` or `--max-tokens`) is given. It prints what is missing. Without a cap, `run --mode auto` with a real provider refuses to start.
2. `.claude/docs/evals.md` gets a "First live run" section: the exact commands (a cheap Analyst question with `--max-cost 1`, then the design loop with `--max-cost 20 --record evals/runs/official_brief_live.jsonl`), what to check in the answer, and how to re-record the challenge2 recordings live.

Phase order: 1 → 2 (A) → 3 (B, C, D, E in parallel) → 4 (F, G in parallel) → 5 (I, J, K, L in parallel; I touches the stores, so merge it first) → 6 (H: version, snapshots, docs over everything) → `make test-all`, `make lint`, push `origin main`.

## 14. Out of scope (do not do)

- The live run itself (no key). Running a plant with an agent-written module (needs simulate in the sandbox). Any change to gemini or the backend.

## 15. Done when

- geomind runs on gemini 0.5.x with no removed gemini name, and `make test-all` and `make lint` pass.
- Verification is `gm.evaluate.verdict` only. The workarounds listed in phase 1 are gone or have a written gemini request.
- The offline design loop passes on both projects, the variants fail for gemini's reasons, and the compare task ranks two or more topologies with one study.
- A second message of a chat reads the first message's case files, designs and results.
- `test_module` checks a module in the gemini sandbox image (docker tier), and the skill is general.
- `show --format md` gives the full agent log of the competition, and `summary.md` compares the loops.
- `geomind check-live` says what a live run still needs.
- The tools of sections I and J (`write_module`, `test_module`, the chat-artifact store) are in the snapshots and the changelog.
- Version 0.3.0, docs, schemas, snapshots and the changelog are updated, and the branch is pushed.

## 16. Final report (short, in this order)

1. Commits, one line each.
2. Tests and lint, with any test that fails only under load.
3. Tools old → new (renamed, removed, added, changed arguments).
4. For Sahand (backend): `Workspace.case` now returns files, not a folder; the new `RunStore` chat-artifact methods; the state's `case`, `case_origin` and `Requirement` shapes; the artifact keys; the supported gemini range; the sandbox image the backend's worker needs.
5. Workarounds deleted, and gemini requests still open (`.tmp/adapt05/gemini-requests.md`).
6. What is still open: the live run, and plant runs with agent-written modules.

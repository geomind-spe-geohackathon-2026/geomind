# Plan

This file is the roadmap. Update it in the same commit that finishes or changes a task.

Everything decided, built and still to do. A new session or a new team member reads this first, then
the other files of `.claude/docs/`. Where a fact has its own document, this file links to it. Where
this file and the code differ, the code wins: correct this file.

## 1. The goal and the inputs

The project is the SPE Europe Energy GeoHackathon Express, built on the GEMINI geothermal digital
twin.

- **Challenge 1 (50 %):** an agentic AI workflow. It analyses the problem, drives GEMINI, chooses and
  runs models, fills in missing models, compares alternatives and explains the configuration.
- **Challenge 2 (50 %):** an integrated deep-geothermal heating and cooling design. Report the
  capacities, the design and the agent log: prompts, answers and token usage.
- **Bonus:** multi-agent work, optimisation, uncertainty, techno-economics and automatic
  verification.
- **Deliverables:** a report of at most 5 pages or 10 slides, a video of at most 5 minutes, and
  everything committed and pushed to GitHub.

### Official inputs (released 2026-10-29)

The files are `GEMINI_Heating_Demand_Daily_2027.csv`, `GEMINI_Cooling_Demand_Daily_2027.csv` and
`GEMINI_Hackathon_Challenge_Requirements.pdf`. gemini ships both CSV files as package data and
serves them as `gm.profiles.get("heating_demand")` and `gm.profiles.get("cooling_demand")`, so an
agent reads them through a tool and never through a path.

| Item | Value |
|---|---|
| Heating demand | 365 daily values; peak 30.0 MWth (28 Jan), minimum 2.67, 111.7 GWh per year |
| Cooling demand | peak 10.0 MW (19 Jul), 23.7 GWh per year, above 0 on 219 days; heating + cooling ≤ 30 on any day |
| Reservoir | mid depth 2500 m TVD, 100 m thick, gradient 30 °C/km, surface 12 °C (so 87 °C at 2500 m), 250 barg, 200 mD; the depth may be chosen |
| Brine | 1030 kg/m³ and 0.40 mPa·s; gas-liquid ratio 0.8 Nm³/m³; gas is 80 % CH₄ and 20 % CO₂ |
| Hard limits | 1 to 3 doublets; 50 to 300 m³/h per doublet while active; brine cooling ≤ 40 K; pump efficiency 70 %; production volume = injection volume; 330 operating days |
| Supply temperatures | 100 °C for heating, 20 °C for cooling (return temperatures are not given) |

What this implies: 87 °C is below the 100 °C supply, so the design needs a heat pump, a gas boiler
burning the co-produced gas, or deeper wells (about 3000 m gives about 102 °C). One doublet gives at
most about 14 MW at 40 K, so the peak needs 2 to 3 doublets or top-up heat.

## 2. Repositories

The local workspace `crust-team/` holds `gemini/`, `geomind/`, `backend/`, `frontend/`,
`infrastructure/` and `docs/`.

```text
frontend (React + Vite) -> backend (FastAPI, Celery) -> geomind (agents) -> gemini (physics)
```

- **gemini** (`import gemini as gm`) is the physics library and engine: modules, plants, units,
  simulation, results, economics and checks. It is the only place where physics and numbers live.
  Sahand develops it on the branch `refactor`.
- **geomind** (`import geomind as gd`, `git@github.com:crust-team/geomind.git`) is this repository.
  **geomind computes no physics.** Every number comes from a gemini tool.
- **backend** stores chats, runs, events and plants, queues runs on Celery and streams events by SSE.
  It implements geomind's `RunStore` and `Workspace` and never chooses agents or loops.
- **docs/** holds the shared documents. `contracts.md` is the one every repository follows; its
  geomind part is mapped in [contracts.md](contracts.md).
- The product and the infrastructure have their own name, in the shared
  [contracts](../../../docs/contracts.md) section 3. The only Python packages are the ones above.

## 3. Design decisions

Each decision is settled; change one only with Sahand. The layers are prompt ⊂ context ⊂ harness ⊂
loop: the prompt is one agent's instructions, the context everything sent in one LLM call, the
harness the engine, tools, permissions, hooks, sandbox and log, and a loop decides which run comes
next and when the goal is met. geomind copies gemini's structure on purpose, so one mental model
covers both: see [the gemini parallels](../../AGENTS.md#the-gemini-parallels).

| # | Decision | Why | Detail |
|---|---|---|---|
| 1 | The event log is the only source of truth, with no checkpoints; resume, crash recovery and replay are one mechanism | Three mechanisms would drift apart; any process can continue a run | [engine.md](engine.md#recovery-and-resume) |
| 2 | The core is async and the facade is sync | Parallel tool calls and delegates need it, and changing it later would touch every layer | [conventions.md](conventions.md#departures-from-gemini) |
| 3 | LLM calls and tool calls are the only side effects | Everything else is deterministic over the log, so a durable executor could wrap them later | [engine.md](engine.md#harness-principles) |
| 4 | Context is explicit: a tool whose first parameter is `context` gets the run; `runtime.py` holds settings only | No hidden active-run variable | [tools.md](tools.md#dispatch) |
| 5 | Hooks and permissions are separate; every tool declares an effect; every decision is a `permission` event | Hooks are code, rules are data, and both must be auditable | [hooks.md](hooks.md), [permissions.md](permissions.md) |
| 6 | Model-written code runs only in a sandbox, never in the harness process | Credentials and the harness stay out of its reach | [sandbox.md](sandbox.md) |
| 7 | Few generic tools, not one per gemini module; errors are results | About 45 modules as 45 tools is the bloated-tool-set failure; a model can fix its call from a result | [tools.md](tools.md) |
| 8 | The problem state lives outside the messages, is written only through `update_state`, and is rendered last | The cached prefix stays stable and compaction never touches it | [context.md](context.md#problem-state) |
| 9 | Past 60 % of the model window, older turns become one summary; skills load on demand | The context stays small, and a chat compacts once | [context.md](context.md#long-conversations) |
| 10 | An agent's constructor declares `# Agents`, `# Prompt`, `# Tools`, `# Output`, `# Model`; there is no `Team` class | The order of agents is a policy, and policies are loops. An agent says which model, the run which provider | [agents.md](agents.md) |
| 11 | `run.py` holds the tables `LOOPS` and `AGENTS`; later the `Coordinator` returns a typed `Route`. **The backend never chooses the loop or the agent.** `gd.Run(agent=...)` exists only for manual testing | Routing is one cheap, logged LLM call, and a new agent is one table row | [agents.md](agents.md#shipped-agents) |
| 12 | Public events go to the browser, internal ones stay in the log; `text.delta` is never stored; nested runs share the root log | One stream, one log | [events.md](events.md) |
| 13 | geomind uses only gemini's public API, `import gemini as gm`, and never an internal path | gemini's internals change; `gemini/.claude/docs/api.md` is the reference for every gemini tool | [conventions.md](conventions.md#dependencies) |

## 4. gemini's conventions that geomind's tools follow

These were agreed in the gemini threads on 2026-10-30. `gemini/.claude/docs/api.md` is the reference;
check it before writing a tool, because gemini's names change.

- **Versioning.** `gm.__version__`, semver below 1.0: a breaking change raises the minor version.
  Adding or removing modules in the catalogue is not an API change.
- **Three return shapes only:**
  - **Value** `{value, unit}`, where `value` is a number, an array or `null` (with a `reason` when it
    is `null`). A series adds `time`, and statistics are `{min, max, mean}`, each a Value.
  - **Problem** `{path, code, message, suggestions}`, for every error and validation result. `path`
    may be `null`.
  - **Check** `{name, passed, value, limit}`.
- **Errors.** `on_error="raise" | "record"`, `raise` by default. Seven classes: `GeminiError`,
  `ValidationError`, `DefinitionError`, `PhysicsError`, `RunError`, `Cancelled` and
  `NotImplementedYet`. The detail is in `code`.
- **Running.** `gm.simulate`, `gm.replay` and `gm.live(plant, ...)` are thin functions over
  `gm.Engine`, which stays public. `gm.evaluate` runs one module.
- **Plants.** `gm.plants.from_dict`, `plant.to_dict`, `gm.plants.validate` and
  `gm.plants.spec_schema`. Well-known plants are registered `gm.Plant` subclasses (`Doublet` takes
  design parameters such as depth and gradient). `gm.plants.templates()` and `from_template` remain
  for the backend's template route.
- **Wiring.** Every port is named `<role>_in` or `<role>_out`, and no port may be left unconnected.
  Everything in the energy flow is a module. Grids (`ElectricityGrid`, `GasGrid`, `HeatingGrid`,
  `CoolingGrid`, `WasteGrid`, `ChemicalGrid`) and `Atmosphere` are the plant's boundaries, and plant
  totals come from the boundary ports.
- **Other names.** `gm.profiles` holds the official demand profiles. `gm.schedule(plant, demand,
  rules)` builds a run input. `gm.checks.Limits().add(path, min, max)` with `gm.checks.limits(...)`
  checks limits. `gm.kpi.compute`, `gm.kpi.names` and `gm.kpi.totals` give the KPIs. Economics
  functions take `(plant, results, ...)`, and `capex` takes no results. `gm.testing.check_module(cls)`
  returns a report.

## 5. What is built

| Phase | What | Commits | State |
|---|---|---|---|
| S1 | Engine, run facade, events, stores, providers (`OpenRouter`, `FakeLLM`), hooks, permissions, sandbox, CLI, replay | `faa2990`…`94d0f57` | done |
| S1b | Rename to geomind, top-level packages, contract alignment | `079b04a`, `f1b320a`, `a9ec1cf` | done |
| S1c | Simplification: explicit context, no checkpoints, stores out of the engine, delegation in one place | `6b4ee23`…`9dccd85` | done |
| S2 | `step.finished.text`; `text.delta` not stored | `51a8f9b` | done |
| S2 | `ProblemState` and `update_state` | `ad60954` | done |
| S2 | Compaction and skills; the 50-turn test compacts once and still answers turn 3 | `b0ec535` | done |
| S2 | `read_result`, `search_documents` | `aa4b01e` | done |
| S2 | `Analyst` (complete sample, the default agent without a sandbox), `Summarizer`; skeletons of `Coordinator`, `Designer`, `Verifier`, `Economist`, `Explainer`, each with a six-heading prompt file | `ad01b96` | done |
| S2 | `geomind chat` and the eval runner | `55296c1` | done |
| S2b | `FileWorkspace.plant` through `gm.plants.from_dict` | `957c119` | done |
| Freeze | Every interface below, pinned by snapshots; the tool catalogue and the loops as stubs; see [CHANGELOG.md](../../CHANGELOG.md) | `fab5524`, `09096d8` | done |
| S2b.1 | `list_modules`, `describe_module`, `evaluate_module` over `gm.modules` and `gm.evaluate` | `599a660` | done |
| S2b.2 | `list_plants`, `read_plant`, `build_plant` over `gm.plants`; a design is stored only when `gm.plants.validate` finds no problem | `2d3efa1` | done |
| S2b.3 | `list_profiles`, `read_profile`, `simulate` (schedule with the brief's rules, record failed days); the input bridge for setpoints | `f4732aa` | done |
| S2b.4 | the `Analyst` with the gemini tools, its prompt, and the `gemini-units` skill checked against `gm.units.names()` | this commit | done |
| S2 gemini tools | the assessment tools of the catalogue | none | **stubs**: see section 7 |

No live OpenRouter run has been made yet. It needs `OPENROUTER_API_KEY` in geomind's own
environment, never the backend's key.

## 6. Frozen interfaces

Sahand's rule: **the interfaces are fixed now, so the backend never breaks later.** What is frozen,
where it is pinned and the rule for changing it are in
[api.md](api.md#frozen-interfaces). The tools are in [tools.md](tools.md#catalogue), and the
contract map in [contracts.md](contracts.md).

## 7. Remaining work

The tasks are in order. Each one replaces a stub whose name, schema and effect are frozen: fill the
body, and remove its `stub` status in the table of [tools.md](tools.md#catalogue). A task that needs
a different signature follows the [change rule](api.md#frozen-interfaces). Task tests go in the
mirrored `tests/unit/...` file that already exists for the stub.

### S2b: gemini tools (the first job)

Return gemini's three shapes unchanged, and let gemini's errors through to dispatch, which turns them
into results. Use only `import gemini as gm`, inside the function, so `import geomind` stays free of
gemini.

1. **Module tools.** Done. Replaced the stubs `list_modules`, `describe_module` and `evaluate_module` in
   `geomind/tools/gemini/catalogue.py`.
   - Tests: `tests/unit/tools/gemini/test_catalogue.py`, against real gemini modules.
   - Done when: the three tools return gemini's shapes, and an unknown name is a result with
     `unknown_name` and suggestions.
2. **Plant tools.** Done. Replaced the stubs `list_plants`, `read_plant` and `build_plant` in
   `geomind/tools/gemini/plants.py`.
   - Tests: `tests/unit/tools/gemini/test_plants.py`.
   - Done when: `read_plant()` describes `Workspace.plant`, a plant that fails
     `gm.plants.validate(plant, on_error="record")` returns its problems and stores nothing, and a
     valid one is read back through its `design/<name>` reference.
3. **Profiles and simulation.** Done. The numbers are checked on `HackathonPlant`, because
   gemini's example doublet fails every day of the demand year (`out_of_range`); its failures are
   checked instead. Replaced the stubs `list_profiles`, `read_profile` and `simulate` in
   `geomind/tools/gemini/runs.py`.
   - `simulate` stores the [result format](tools.md#references) under `result/<id>`, and beside it
     what the S3 tools need: `Results.to_bytes()` and the plant. The keys of those two are free.
   - `read_result` in `geomind/tools/gemini/results.py` is already built and reads that format.
   - Tests: `tests/unit/tools/gemini/test_runs.py`, on the example doublet.
   - Done when: a `simulate` of `gm.plants.example("DoubletHeatPlant")` stores a result that
     `read_result` reads, with the numbers equal to gemini's own run.
4. **The Analyst.** Done. Added the tools to `geomind/agents/analysis/analyst.py` and its prompt, and update
   the `gemini-units` skill to the units gemini accepts.
   - Tests: `tests/unit/agents/analysis/test_analyst.py`.
   - Done when: `test_its_prompt_names_only_tools_it_has` passes with the new tools.
5. **First eval tasks** on the example doublet, in `evals/tasks/analyst/`: the operating point, heat
   delivered at 150 m³/h, a missing parameter that needs `ask_user`, a module lookup, and the ESP at
   another frequency.
   - Done when: `python -m evals.run --agent analyst` passes offline from recordings.
6. **One live run.** `geomind chat --agent analyst --live`, recorded, with the token cost reported.

### S3: design agents and verified loops (Challenge 2)

1. **Verification.** Replaces the stub `gd.verify.verify` in `geomind/verify/verify.py` and the stubs
   `check_results`, `compute_kpis` in `geomind/tools/gemini/assessment.py`.
   - The checks are gemini's and never an LLM: energy and mass balances, demand coverage per day,
     bounds and limits including the hard limits of section 1, and unit consistency.
   - Tests: `tests/unit/verify/test_verify.py`, `tests/unit/tools/gemini/test_assessment.py`.
   - Done when: a design that breaks a hard limit fails with a `Check` that names it.
2. **The `Verified` hook.** Replaces the stub in `geomind/engine/hooks.py`.
   - Tests: `tests/unit/engine/test_hooks.py`.
   - Done when: `before_finish` refuses to finish while the last verification failed, so **no design
     reaches the user without passing every verifier**.
3. **Costs.** Replaces the stub `estimate_costs` in `geomind/tools/gemini/assessment.py`.
   - Done when: capex, opex, LCOH, LCOC, NPV and CO₂ come back as Values with the assumptions used.
4. **Fill the skeleton agents** of [agents.md](agents.md#shipped-agents): prompts, tools and eval
   tasks. `Designer` proposes configurations and sizes, `Verifier` runs the checks and reviews,
   `Economist` gives the costs, `Explainer` writes the explanation, and `Coordinator` routes.
   - Done when: each agent's status in the table is complete, with its tasks passing offline.
5. **`DesignLoop`.** Replaces the stub in `geomind/loops/design.py`: propose, simulate, verify, write
   the failures to the problem state, and repeat until everything passes, the budget runs out, the
   round limit is reached, the same check fails repeatedly, or a question goes to the user. Every
   stop reason is explicit and logged.
   - Tests: `tests/unit/loops/test_design.py`.
   - Done when: `geomind run --loop design <brief>` returns a verified design with capacities, a
     description of the schematic, the numbers and an explanation, for the official brief. The
     option `--loop` does not exist yet; adding it is an additive change of the CLI snapshot.
6. **`MakerCheckerLoop`.** Replaces the stub in `geomind/loops/makerchecker.py`: the designer proposes
   and the verifier checks.
   - Tests: `tests/unit/loops/test_makerchecker.py`.
   - Done when: a refused proposal goes back to the maker, up to `max_rounds`.
7. **Routing.** `Run.astart` calls the `Coordinator` and follows its `Route` with `loop_of` in
   `geomind/run.py`. A stub loop already gives `stop_reason="not_implemented"`.
   - Tests: `tests/unit/test_run.py`.
   - Done when: the backend starts a design run without naming a loop or an agent.
8. **Agent-written modules (Challenge 1).** Replaces the stub `test_module` in
   `geomind/tools/gemini/assessment.py`: it runs `gm.testing.check_module` in the sandbox. The
   `writing-a-gemini-module` skill comes from gemini's module guide, and `DockerSandbox` needs an
   image with gemini's dependencies ([sandbox.md](sandbox.md#dockersandbox)).
   - Done when: a module the model wrote passes `test_module` without running in the harness process.

### S4: compare, uncertainty, evals and export

1. **`CompareLoop`.** Replaces the stub in `geomind/loops/compare.py`: it runs `DesignLoop` on
   alternatives in parallel and ranks them on cost, CO₂ and coverage. Example alternatives: cooling by
   heat pump, absorption chiller or compression chiller; with or without storage; 2 or 3 doublets.
   - Tests: `tests/unit/loops/test_compare.py`.
   - Done when: one brief gives a ranked table of verified designs.
2. **Optimisation (bonus).** Replaces the stub `optimize` in
   `geomind/tools/gemini/assessment.py`, once `gm.optim.minimize` is real; it is `later` in gemini.
   - Done when: it returns the design, the objective and the history.
3. **Uncertainty (bonus).** Replaces the stub `sample_uncertainty` in
   `geomind/tools/gemini/assessment.py`, once `gm.optim.sample` is real; it is `later` in gemini. Run
   the chosen design over P10, P50 and P90 reservoir and demand cases.
   - Done when: it returns `{metric: {p10, p50, p90}}` as Values.
4. **Evals.** `evals/tasks/challenge2/`: the official brief plus variants (more cooling, a colder
   reservoir, a tighter budget). `evals/reports/summary.md` compares `ToolLoop`, `DesignLoop`,
   `MakerCheckerLoop` and `CompareLoop` on criteria met, steps, tokens, cost and time.
   - Done when: the report holds all four for every task.
5. **Export.** `geomind show <run> --format md` exists; extend it to the form the competition asks
   for: prompts, answers and token usage.
   - Tests: `tests/unit/test_cli.py`.
   - Done when: the export of the final run goes into the report as it is.

## 8. How to work in this repository

- **Read first:** `AGENTS.md` and every file in `.claude/docs/`.
- **Branch, tests and quality:** see [AGENTS.md](../../AGENTS.md#branching),
  [testing.md](testing.md) and [conventions.md](conventions.md#code-quality).
- **Docs:** a commit that changes behaviour updates `AGENTS.md` or `.claude/docs/` in the same commit.
- **Temporary files** go to `.tmp/`.
- **Subagents** use lighter models.
- **Stop and say so** when something is missing or risky. Never guess a gemini name.
- **Never change** `gemini/`, `backend/`, `frontend/`, `infrastructure/` or `docs/contracts.md` from
  this repository. Report what they need to Sahand.
- **Credentials** never go into prompts, events, logs, the sandbox or memory.
- **Testing an agent:** by hand with `geomind chat` ([api.md](api.md#command-line)), by tasks with
  `python -m evals.run` ([evals.md](evals.md)).
- **Adding or filling an agent:** follow [agents.md](agents.md#how-to-add-or-fill-an-agent). The
  `Analyst` is the worked example.

## 9. Open questions (ask Sahand)

- The OpenRouter model ids per role. The default `anthropic/claude-sonnet-5.5` has not been checked
  against OpenRouter yet.
- Return temperatures of the heating and cooling networks (assumed 60 °C and 25 °C until Sahand
  confirms).
- Whether outage days are chosen automatically (lowest demand) or by date. `gm.schedule` raises
  `NotImplementedYet` for `operating_days` until the meaning of the organisers' "330 daily steps" is
  decided.
- Cost data sources for economics (ThermoGIS, DoubletCalc or GEOPHIRES-X defaults).

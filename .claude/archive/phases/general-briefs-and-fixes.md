# Task: any brief, not only the hackathon's; fix replay and token totals; catch up with gemini

## 0. Context and rules

- **Goal.** geomind must answer any geothermal heating and cooling question and design for any
  brief, not only the GEMINI hackathon brief with its two demand profiles. Today the hackathon brief
  is code: `geomind/tools/gemini/brief.py` holds its limits, `simulate` always schedules with
  `SCHEDULE_RULES`, verification always checks the brief's limits, only gemini's two named profiles
  exist, and the `designing-a-plant` skill is the brief plus its answer. This task makes the brief
  data, with the hackathon brief as one preset. It also fixes two bugs found in review, catches up
  with gemini's latest pushed `refactor`, and checks the rest of the plan for small gaps.
- **Workspace.** The `crust-team/` folder that holds `geomind/` and `gemini/`. Change **only**
  `geomind/`. Read `../gemini/` (and `../docs/` if present) but never change them, including
  `../docs/contracts.md`. Report what they need instead (section 11).
- **Read first:** `AGENTS.md`, every file in `.claude/docs/` (start with `plan.md`), then
  `../gemini/.claude/docs/api.md` and `../gemini/gemini/__init__.py`.
- **Pre-check.** `git status` is clean on `main` and `git pull origin main` succeeds. No other
  Claude session works inside `geomind/`. If machine load makes a 1 s budget test fail, rerun it
  alone before treating it as a failure, and say which ones you retimed.
- **Branch.** Work directly on `main`: commit after each section, push `origin main` at the end. No
  other branch, no PR.
- **Frozen interfaces.** Everything in `.claude/docs/api.md#frozen-interfaces` stays compatible. A
  change to a frozen item is **additive only** and follows the change rule there in the same commit
  (version bump, `scripts/snapshot_api.py`, CHANGELOG). Never remove or rename a frozen name, never
  change a frozen default in a way that changes behaviour for an existing caller.
- **Tests.**
  - While working, run only the tests of the changed files and of everything that imports them, in
    parallel (`make test` / `scripts/test_changed.py`).
  - Before each commit, `make test-all` and `make lint`.
  - Write a failing test before each bug fix.
  - No test calls the network; no fast test runs over about 1 s; never delete or weaken a test.
  - Do not make a live OpenRouter run in this task (there is still no key).
- **Quality bar** (`.claude/docs/conventions.md`): nesting at most 3 levels, functions about 40
  lines at most, flake8 `max-complexity = 10`, guard clauses, full-word names, explicit `gd.errors`
  classes, no dead, speculative or golfed code, **no comments inside code** (docstrings and `NOTE:`
  only), no new runtime dependency.
- **Docs.** Every commit that changes behaviour or structure updates `AGENTS.md` or `.claude/docs/`
  in the same commit; `plan.md` "What is built" and "Remaining work" stay true.
- **Temporary files** go to `.tmp/briefs/`.
- **Subagents** use lighter models: sonnet for code, haiku for read-only searches.
- **Stop and say so** when something is missing or risky. Never guess a gemini name, and never
  import a gemini internal path. **geomind computes no physics**: every number comes from gemini.
- **Credentials** never go into code, tests, docs, events or logs.

## 1. Catch up with gemini's pushed `refactor`

1. In `../gemini/`: if `git status` is clean, `git fetch origin` and `git pull origin refactor`. If
   it is not clean, or is on another branch, do **not** touch it: write down its branch and commit,
   continue against it, and say so in the report.
2. Record the gemini commit before and after in `.tmp/briefs/gemini.md`, with the list of changed
   public names (`gemini/__init__.py`, `api.md`, `tests/fixtures/public_api.json` if present).
3. Run `make test-all`. Fix every break in geomind caused by a changed gemini name or shape, using
   only exported names. Known state: on gemini `c50cbdd` (module layout moves) geomind passes
   everything except the replay bug of section 2.
4. Do **not** adapt to the coming Module/Plant redesign yet (`set_inputs` private, `from_template`
   removed, templates as classes): it is not pushed. Keep every gemini call behind the existing
   tool modules, so that adaptation later touches as few files as possible, and list in the report
   every place that uses `set_inputs`, `from_template` or template names.

Commit (only if something changed): `gemini: follow refactor <short hash>`.

## 2. Bug: replay compares parallel tool calls in completion order

`tests/unit/engine/test_replay.py::test_replay_passes_without_network` fails in about 4 of 6 runs
(`pytest -n 0` on that file, repeated). Cause: `_compare_calls` in `geomind/engine/replay.py` zips
the recorded and replayed `tool.recorded` events in log order, and two calls of one step finish in
any order. The failure reads `step 1: tool lookup: recorded (... 'lookup' ...), replayed (... 'add' ...)`.

- Compare calls by their place in the step (step index, then the call's position in the model's
  `tool_calls`, or `call_id` if that is stable across a replay), not by finishing order. Keep every
  real difference an error: a different tool, input, output or `is_error` still raises.
- Check the other replay helpers (`_results`, the nested state-change matching) for the same
  order assumption.
- Test: a step with two or three parallel calls whose finishing order is forced to differ between
  record and replay (for example with `asyncio.sleep` in a test tool) replays; a changed output
  still fails. Run the file 20 times in a loop to show it is no longer flaky.

Commit: `replay: match parallel calls by their place in the step, not by finishing order`.

## 3. Bug: routing tokens are missing from `RunResult.usage`

The `Coordinator`'s routing call is logged, but its tokens are not in `RunResult.usage`. Challenge 2
asks for the token usage of the agent log, so the totals must be complete.

- `RunResult.usage` includes every nested run of the run: the routing call, delegates and loops,
  and the summarizer when it compacts. Check each one with a test on `FakeLLM` with set usage.
- `geomind show --format md` totals, by agent and by step, equal `RunResult.usage`.
- `run_manifest.json` keeps the models per agent; add the routing model if missing.

Commit: `run: usage counts every nested run, routing included`.

## 4. The brief as data

1. **A `Brief` record**, in `geomind/context/` beside `ProblemState`. It holds only what a brief
   can state, each field optional with `None` meaning "not given":
   - demand: the names or references of the heating and cooling profiles;
   - number of doublets `{min, max}`, flow per doublet `{min, max}`, maximum brine cooling,
     operating days, pump efficiency, production volume equal to injection volume (bool);
   - supply and return temperatures of the heating and cooling networks;
   - the reservoir and brine values, when the brief gives them (depth, thickness, gradient, surface
     temperature, pressure, permeability, density, viscosity, gas-liquid ratio, gas composition);
   - `source`: a preset name, `user`, or `agent`.
   Values are `{value, unit}` strings or Values as gemini takes them; geomind converts nothing
   itself, it uses `gm.units` where a number is needed.
2. **Presets.** `brief.py` becomes the preset `hackathon_2027` (same numbers, same docstring
   source). A small registry lists presets by name; it is the only place the hackathon numbers
   live.
3. **In the problem state.** Add `brief: Brief | None = None` to `ProblemState` (additive; follow the
   change rule, since the backend stores the state). `update_state` can set it by patch; add a
   small tool `set_brief(preset=None, changes=None)` that loads a preset and applies changes, if a
   patch on `/brief` is not enough for a model to use reliably. `render` shows the brief.
4. **Who fills it.** The `Coordinator`'s `Route.brief` text stays. The first agent of a design run
   (Designer, or the DesignLoop driver before round 1) sets the state's brief from the user's
   message: the preset when the message is about the hackathon, otherwise the values the user
   gave. Anything a design needs that is not given (demand above all) goes to `ask_user`, or, where
   a default is reasonable, an `Assumption` with `source="default"` and `confirmed=False`. Never
   silently fall back to the hackathon numbers.
5. **`simulate`** builds `gm.schedule`'s `rules` from the state's brief (flow limits, brine cooling,
   operating days) and the order default; without a brief it keeps today's behaviour so existing
   callers and recordings still pass, and says in its summary which rules it used.
6. **Verification** (`geomind/tools/gemini/verification.py`, `gd.verify`) checks the limits of the
   state's brief. A limit the brief does not give is not checked and is listed as `not given`, not
   as passed. The hackathon preset gives exactly today's checks, so today's tests keep their results.
7. **The `Analyst`** reads the brief from the state when it has one, and does not need one.

Tests: the hackathon preset reproduces today's verification of the base design; a brief with other
limits (for example 1 doublet, 30 K, supply 80 °C) changes which checks pass, with real gemini
numbers; a brief without demand makes the design run ask the user; a state with a brief round-trips
through `save_state`.

Commits: `context: the brief as data, the hackathon brief a preset`, then
`tools, verify: schedule and check against the state's brief`.

## 5. Demand profiles from the user

`gm.schedule(plant, demand, rules)` takes any DataFrame with a UTC index and `heating_demand`
(and optionally `cooling_demand`) in W, so this needs no gemini change.

- `list_profiles` and `read_profile` list and read gemini's named profiles **and** profiles stored
  in the run as artifacts `profile/<name>`.
- A tool `save_profile(name, values, unit, start, step="1D", quantity="heating_demand")` stores a
  profile the user gave in the chat (a list of values), converted to W through `gm.units`, and
  checks its shape (length, no gaps, non-negative). A profile from a project file: if `Workspace`
  already gives documents, read a CSV through it; if that needs a new `Workspace` method, it is a
  backend contract change, so do not add it, and report it (section 11).
- `simulate(profile=...)` and the brief's demand accept both kinds of names.
- Test: a 30-day user profile simulates on the example plant, and its result is read back.

Commit: `tools: demand profiles from the user`.

## 6. A general design skill

- Split `designing-a-plant` into a general skill (how to read a brief, choose families, size
  doublets against peak demand and brine cooling, when a heat pump, boiler or deeper wells are
  needed, what gemini can and cannot run today) and a short `hackathon-2027` note with the
  hackathon's numbers. The general skill names **no** answer topology for a specific brief.
- Do the same for the Designer prompt: it shows how to reason, not the hackathon answer. Keep what
  gemini cannot run (one heat pump, absorption chiller only, no water loops) as facts about gemini.
- In `.claude/docs/` (and the report), say plainly that the base design of the scripted recording
  was found by hand, and that the general skill no longer points to it.

Commit: `prompts: a general design skill; the hackathon numbers in a note`.

## 7. Evals for other briefs

Add to `evals/tasks/challenge2/` (create it if missing) the hackathon brief and three variants: more
cooling (cooling peak 15 MW), a colder reservoir (gradient 25 K/km), and a user profile of 30 days.
Each task names its criteria (verified, demand met, the brief's limits checked). Recordings are
hand-written until the live run, as today; mark each as such in its file. Each task passes offline.
The variants must fail if the agents ignored the brief: for example the colder reservoir must not
pass with the hackathon's depth if the brief's limits make that design fail.

Commit: `evals: the hackathon brief and three variants`.

## 8. Prompt caching (cost)

The system prompt and tool schemas repeat in every call (about 3 to 10 thousand tokens per call;
one scripted design run is about 135 thousand input tokens). If `geomind/providers/openrouter.py`
sends no cache hints, add OpenRouter's prompt caching for models that support it (for Anthropic
models, `cache_control` on the system prompt and the last tool schema), behind a setting that is on
by default. Report cached tokens in `usage` if OpenRouter returns them. Test the request payload
offline; no network.

Commit: `providers: prompt caching on OpenRouter`.

## 9. Model ids

Check the model ids of `geomind/runtime.py` (`anthropic/claude-sonnet-5.5`,
`anthropic/claude-haiku-5.5`) against OpenRouter's public model list
(`GET https://openrouter.ai/api/v1/models`, no key needed) once, by hand, outside the tests. Correct
any id that does not exist, write the list you checked to `.tmp/briefs/models.md`, and remove the
open question in `plan.md` if it is settled.

## 10. A second look at the plan

Go through `plan.md` sections 5 and 7 against the code and the tests:

- Every row marked done has its "done when" met by a test. List any that is not, and fix it if it
  is small (under about an hour); otherwise list it.
- Every stub still raises `NotImplementedYet` with the phase that fills it, and the tool table says
  `stub`.
- Anything else you find missing for an end-to-end live run of the official brief (for example a
  spending cap: a hook that stops a run above a token or cost budget, if none exists).

Write the list to `.tmp/briefs/audit.md`; fix the small items in their own commits.

## 11. Report

End with a short report:

- the commits, the test count and the lint result;
- the gemini commit before and after, and what broke;
- every frozen-interface change with its version bump;
- the places that use `set_inputs`, `from_template` or template names (for the redesign);
- what gemini, the backend or `contracts.md` need from Sahand (for example a `Workspace` method for
  project files, the `brief` key in the stored state);
- the audit list, split into fixed and still open;
- what the live run still needs (the key, a spending cap).

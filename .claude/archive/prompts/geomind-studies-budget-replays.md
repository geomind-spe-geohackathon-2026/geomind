# geomind: studies the app can list, a per-project budget, and the two broken replays

Repository: geomind (`crust-team/geomind`). Work on `main`. You start at `a38bad6` (geomind 0.3.1, gemini 0.5.x at `../gemini`).
This prompt is self-contained: everything you need is here.

## 0. Goal

Three requests are open. Two come from the app build (frontend and backend), and one comes from our own replay check.

1. **Studies run from chat are invisible to the app.** The app has a Study page that lists a project's studies. When an agent runs a study in chat, nothing records it as a study, so the page stays empty. The tools involved are `run_study`, `optimize`, `size_plant`, `sample_uncertainty` and `sensitivity` in `geomind/tools/gemini/study.py`. Today they only save designs (`design/<name>`) and return JSON to the model. There is also a likely bug here: `run_study` saves each run's plant as `design/<plant_name>_best` (`study.py:216`). Since 0.3.0, a design name can be written only once. So a second `run_study` over the same plant with a different result is probably refused. Check this with a test first.
2. **No budget per project.** `TokenBudget` and `CostBudget` (`geomind/engine/hooks.py`) cap one run, nested runs included. The app needs a cap over all runs of a project, such as "this project may spend 20 USD in total". The backend knows what earlier runs spent; geomind does not.
3. **Two single-agent eval recordings do not replay.** These are `explainer/unverified`, which fails on `read_plant`, and `analyst/module_lookup`, which fails on `update_state`. They failed the same way before 0.3.1 and are recorded in `plan.md`.

## 0b. Rules (all of them apply)

- **Coordinator.** The main session only plans, dispatches, reviews diffs and merges. Workers run as subagents: sonnet for code, haiku for read-only search. Each worker has its own git worktree (`../geomind-<name>`, branch `sbr-<name>`) and owns a disjoint set of files. Workers write details to `.tmp/sbr/<name>.md` and report back in at most 15 lines. Remove the worktrees and branches after their merge.
- **gemini is the source of truth and is read-only.** Change nothing in `../gemini`. Store a study in gemini's own `study.json` form (format 1, kind `study`) and its result in gemini's `StudyResult.to_dict()` form. Never invent a parallel format. Missing gemini features go to `.tmp/sbr/gemini-requests.md`.
- **Backward compatible.** Logs and stores from 0.3.0 and 0.3.1 still load, recover, replay and export. New event types and fields are additive. No public name or field is renamed or removed.
- **General.** Nothing is specific to the hackathon, one loop or one tool. Every tool that runs a gemini study records it the same way.
- **No defaults in package code.** In particular, the project budget has no default cap: with no cap set, no project hook is added.
- **No comments in code.** Explanations go in docstrings. Section-header comments and tool directives are allowed.
- **Quality.** Write a failing test before each fix. Keep nesting at 3 levels or fewer and functions around 40 lines or fewer. Use guard clauses. Leave no dead code and use full-word names.
- **Tests.** Use the development profile while working: tests of the changed files and of everything that imports them, run in parallel, with fast-tier tests at 1 s or less. Reuse the session fixtures and the short-window case. Run `make test-all` and `make lint` once before the push. Never shrink or delete recordings or goldens.
- **Docs in the same commit.** Update `.claude/docs/` (tools, events, hooks, api, evals), the contract map for the backend, and `CHANGELOG.md`.
- **Temporary files** go only in `.tmp/sbr/`.

## 1. Setup and inventory (coordinator, with a haiku search worker)

1. Run `git pull --ff-only origin main` and `git -C ../gemini pull --ff-only`. Record both commits and `gm.__version__`.
2. Run the fast tier once as a baseline.
3. Write an inventory to `.tmp/sbr/inventory.md`:
   - every tool that runs a gemini study or search, with what it saves and returns;
   - how `save_design` and the write-once rule for `design/` work (`engine/session.py`, `FROZEN`);
   - how `TokenBudget` and `CostBudget` read usage, nested runs included;
   - how the CLI, `gd.Run` and `run.py` add hooks;
   - the RunStore and Workspace protocols (`geomind/stores/run.py`, `geomind/stores/workspace.py`);
   - the replay error of each of the two broken recordings, verbatim.

## 2. Section S: studies the app can list (worker S)

S owns `geomind/tools/gemini/study.py`, `geomind/tools/gemini/stored.py` (the study helpers only), `geomind/types/events.py` (the new event only), the event schemas and samples, and their tests.

1. **Bug first.** Write a test: call `run_study` twice over the same design, with different settings that change the result. If the second call is refused or loses data, fix it. The stored plant of each run is named after the study, as `design/<study name>_<plant name>`, so names cannot collide. Apply the same check to `optimize` and `size_plant`, which take a `name` from the agent; their behaviour on a taken name must be a clear `ToolError` that names the taken design, not an internal error.
2. **A stored study.** Every study tool (`run_study`, `optimize`, `size_plant`, `sample_uncertainty`, `sensitivity`) stores what it ran as a chat artifact `study/<name>`, written once like `design/`:
   - `study`: the gemini `study.json` dict that was run, with `plants` naming the stored designs and `cases` the case file. For a tool that runs one plant, use the same form with one plant.
   - `result`: gemini's `to_dict()` of what came back, in display units where gemini gives them (`StudyResult`, or the run or search result for the single-plant tools).
   - `designs`: the design references it read and the ones it wrote.
   - `case`: the case reference or hash it ran on, so a later case change cannot make it look current.
   - `tool` and `versions` (the same three versions `run.started` holds).

   `name` is a new argument on `run_study`, `sample_uncertainty` and `sensitivity`, required like `name` on `optimize` and `size_plant`; there is no generated default name. Every study tool returns `study: "study/<name>"` in its output.
3. **An event the backend can record.** Add a public event `study.recorded` with the public fields `run`, `index`, `call_id`, `study` (the key), `tool`, `method`, `designs` (the plant names) and `best` (the best design reference, or null). It is emitted once, after the artifact is saved, through the session as other events are, so it reaches the callbacks and the stream. An old reader that does not know the type must ignore it. Check that the backend contract map says unknown event types are skipped; if it does not, list this in the report for Sahand.
4. **Read tools.** Add `list_studies` (read: the chat's `study/` keys with tool, method, designs, best, and whether its case is still the state's case) and `read_study(study)` (read: the stored artifact). Give both to the Designer, the Economist, the Analyst and the Explainer. Check each agent's tool tests and the agents doc.
5. **Prompts.** The Designer, Economist and Explainer prompts and the designing skill say that every study gets a name, and that an answer cites the study key it relies on. Update the recordings that call study tools (their inputs now carry `name`), and re-record only what changes.
6. **Tests.** Cover each tool storing its study; the write-once refusal; the event's fields and its order after the artifact is saved; `list_studies` after a case change showing the study as not current; a 0.3.1 log without `study.recorded` still replaying and exporting; and the export showing study keys in the tool calls.

## 3. Section B: a budget over a project (worker B)

B owns `geomind/engine/hooks.py` (the new hook only), `geomind/run.py` and `geomind/cli.py` (the hook wiring only), a new protocol in `geomind/stores/` if needed, and their tests.

1. Add a protocol `UsageLedger` with one method, `spent(project_id) -> Usage`. It returns the tokens and cost of every finished run of a project, as the backend stores them. geomind ships `MemoryUsageLedger` for tests and `FileUsageLedger`, which sums the `run.finished` usage of root runs under a `FileRunStore` root that have that project.
2. Add `ProjectBudget(ledger, project_id, max_tokens=None, max_cost=None)`, a hook that denies an LLM call once `ledger.spent(project_id)` plus this run's usage, nested runs included, reaches a cap. At least one cap is required; giving neither is an error. The deny reason names the project, the cap and what was spent, in the same form as `TokenBudget`.
3. Wiring:
   - `gd.Run(..., project_budget=ProjectBudget(...))`, or the existing hooks list if that is how `gd.Run` takes hooks. Pick the smaller change and document it.
   - The CLI gets `--project-max-cost` and `--project-max-tokens`, used with `--project` and the `FileUsageLedger` on `.runs`.
   - A live `--mode auto` run still needs a run cap (`--max-cost` or `--max-tokens`). A project cap alone does not satisfy that rule.
4. Tests: under the cap, the run goes ahead; at the cap, it is denied before the call; nested runs count; giving no cap is an error; `FileUsageLedger` sums only root runs of that project; a resumed run does not count its own earlier steps twice.
5. Backend note for the report: the backend implements `UsageLedger.spent` from its own run table and passes `ProjectBudget` to `gd.Run`.

## 4. Section P: the two broken replays (worker P)

P owns `geomind/engine/replay.py`, the tool files the two failures point to (`read_plant` in `tools/gemini/plants.py`, `update_state` in `tools/state.py`), and the two recordings. If P needs `study.py`, it waits for S's merge.

1. Reproduce each failure with `geomind replay` or the evals runner, and save the error in `.tmp/sbr/P.md`.
2. Find the cause for each. It is one of three things, and the report says which:
   - the recording is stale against today's tool, so re-record it from its task with the scripted model;
   - the tool is not deterministic, for example output that depends on dict order, time or a temporary path, so fix the tool;
   - replay rules treat a `read` tool's re-run differently from the original, so fix the replay.
3. Fix it with a failing test first. When the cause is a stale recording, also add a fast test that replays every recording under `evals/recordings/`, so a stale one fails in CI and not weeks later. Keep it within the fast budget, or put it in the slow tier and say so.
4. All recordings replay at the end, the loop ones included.

## 5. Merge and finish (coordinator)

1. Merge order: P, then S, then B. B touches no study files, so it can merge in any order after S. Review every diff against the rules in 0b.
2. Run `make test-all` and `make lint`, then replay every recording.
3. Version: geomind `0.4.0` (new required `name` argument on three tools, new tools, a new event and a new hook). Update `CHANGELOG.md`, the snapshots, the schemas, the contract map and `plan.md`.
4. Push `origin main`. Remove the worker worktrees and branches.

## 6. Done when

- Every study tool stores `study/<name>` in gemini's study and result form, and emits `study.recorded`.
- A second study over the same plant is never refused for a name clash it did not choose.
- `list_studies` and `read_study` work, and the agents cite study keys.
- `ProjectBudget` caps a project across runs, with the CLI flags and a file ledger, and has no default cap.
- Every recording replays, and a fast or slow test keeps it that way.
- `make test-all` and `make lint` pass, and geomind 0.4.0 is pushed with the docs, contract map and changelog.

## 7. Final report (at most 40 lines)

- The commits, with one line each.
- The test results (fast, slow, e2e, docker) and the fast-tier time.
- The cause and fix of each broken replay.
- For Sahand (backend), the exact contract:
  - the `study.recorded` event fields;
  - the `study/<name>` artifact shape;
  - the `UsageLedger.spent` method;
  - how to pass `ProjectBudget`;
  - whether unknown event types are already skipped.
- Gemini requests, if any, and anything still open.

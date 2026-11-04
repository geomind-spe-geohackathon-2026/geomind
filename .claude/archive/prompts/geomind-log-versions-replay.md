# geomind: versions in the event log, and a full replay of loop runs

Repository: geomind (`crust-team/geomind`). Work on `main`. You start at `989cb59` (geomind 0.3.0, gemini 0.5.0 at `../gemini`).
This prompt is self-contained: everything you need is here.

## 0. Goal

The competition asks for the agent log: every prompt, every answer and the token use of every agent. `geomind show <run> --format md` writes that log. Two gaps make it weaker than it should be:

1. **The versions are not in the event log.** `render_export` (`geomind/export.py:_header`) reads the gemini and geomind versions from `run_manifest.json`. Only `geomind run` writes that file (`geomind/cli.py:write_manifest`). A run started any other way, such as from the backend, a chat, `gd.Run` or an eval, shows "not recorded". The log on its own does not say which code produced it.
2. **Replay of a loop run skips the inner agents.** `replay_run` (`geomind/engine/replay.py`) replays only the top-level run. A loop such as DesignLoop or CompareLoop is a driver agent whose tool calls start nested runs (Designer, Verifier, Economist, Explainer). In a replay, `step.py:_execute` → `_reuse` returns each nested run's recorded answer and applies its recorded state changes (`recorded_changes`), but it never runs the nested agents again. So:
   - a replay checks nothing about the inner agents, which are where all the LLM calls are;
   - the replayed log has no inner calls, so the export of a replayed loop run is not the export of the original.

   Section K worked around this by testing export equality with a single-agent replay and with two runs of the same recording. That workaround goes away here.

There is also one small bug of the same kind as the earlier "oldest message" bug:

3. **The export header shows the wrong request.** `_header` takes the first user message of the root `run.started.messages`. Those messages hold the chat history plus the new message, so in a chat with earlier turns the header shows an old message. Use the last user message, which is the run's own request, as `loops/design.py` now does.

## 0b. Rules (all of them apply)

- **Coordinator.** The main session only plans, dispatches, reviews diffs and merges. Workers run as subagents: sonnet for code, haiku for read-only search. Each worker has its own git worktree (`../geomind-<name>`, branch `logrep-<name>`) and owns a disjoint set of files. Workers write details to `.tmp/logrep/<name>.md` and report back in at most 15 lines.
- **gemini is read-only.** Change nothing in `../gemini`. If gemini is missing something, add it to `.tmp/logrep/gemini-requests.md` and say so in the report.
- **Backward compatible.** Logs stored by geomind 0.3.0 must still load, recover, replay and export. A new event field is optional on read and is always written by new runs. Do not rename or remove any public name or event field.
- **General.** Nothing is specific to the hackathon or to one loop. A replay of any nested run (a loop, or any agent that delegates) follows the same rule.
- **No defaults in package code** for engineering or economic values. This prompt adds none.
- **No comments in code.** Explanations go in docstrings. Section-header comments and tool directives (`# noqa`) are allowed.
- **Quality.** Write a failing test before each fix. Keep nesting at 3 levels or fewer and functions around 40 lines or fewer. Use guard clauses. Leave no dead code and use full-word names.
- **Tests.** Use the development profile while working: tests of the changed files and of everything that imports them, run in parallel, with fast-tier tests at 1 s or less. Run `make test-all` and `make lint` once before the push. Never shrink or delete existing recordings or goldens.
- **Docs in the same commit.** Update `.claude/docs/` (engine, events and export docs, plus `api.md` for the event field) and `CHANGELOG.md`.
- **Temporary files** go only in `.tmp/logrep/`.

## 1. Setup and inventory (coordinator, with a haiku search worker)

1. Run `git pull --ff-only origin main` and `git -C ../gemini pull --ff-only`. Record both commits and `gm.__version__`.
2. Run the fast tier once as a baseline and note any failures.
3. Write an inventory to `.tmp/logrep/inventory.md`:
   - every place that writes `RunStarted` (`engine/session.py:start`);
   - every reader of the event schema (`geomind/schemas/events.json`, `runlog.json`, the snapshots, `contracts.md` if present, and the backend contract map);
   - every caller of `replay_run` and `Engine.replay` (the CLI `replay`, the e2e and eval tests, the evals runner);
   - how a nested run is started (`engine/delegation.py:run_child`), how its events sit in the shared root log (`run_id`, `parent`, `parent_step`, `root`), and how `_child_calls` and `_nested_changes` match a nested run to the call that started it;
   - which recordings in `evals/recordings/` and `tests/` are loop runs with nested runs.

## 2. Section V: versions in the log (worker V)

V owns `geomind/types/events.py`, `geomind/engine/session.py`, `geomind/export.py`, `geomind/cli.py` (the manifest part only), the schemas and snapshots for events, and their tests.

1. Add an optional field `versions: dict[str, str] = {}` to `RunStarted`, which is not streamed. Keep `public_fields` unchanged.
2. Fill it on every new run, not only root runs, with `{"geomind": geomind.__version__, "gemini": gm.__version__, "python": platform.python_version()}`. Import gemini lazily as the rest of the engine does. If gemini cannot be imported, write no `gemini` key; never write a placeholder value.
3. Export: `_header` reads the versions from the root `run.started.versions`. When a log has none (a 0.3.0 log), it falls back to the manifest, and then to "not recorded". Keep the manifest, which still records the repository commits and the input hashes.
4. Replay: when the replayed versions differ from the recorded ones, the replay still runs. Put the difference on the result (for example `RunResult` metadata, or a `ReplayReport` returned next to it; choose the smaller change and document it). The CLI `replay` command prints that difference as one line. A different version is information, not an error.
5. Fix bug 3: the request in the header is the last user message of the root `run.started.messages`. Test it with a chat history of two turns.
6. Tests:
   - a new run's log has the versions;
   - a 0.3.0 log without the field still loads, recovers and exports, falling back to the manifest;
   - the export header shows the log's versions;
   - a replay whose gemini version differs reports the difference and does not raise;
   - the header shows the current request with history present.
7. Regenerate `events.json`, `runlog.json` and the snapshots, and update the docs.

## 3. Section R: full replay of nested runs (worker R)

R owns `geomind/engine/replay.py`, `geomind/engine/step.py` (the replay branch only), `geomind/engine/delegation.py` (only if needed), and `tests/unit/engine/test_replay.py`, plus new tests.

Goal: replaying a run replays every nested run in its tree with that nested run's own recorded completions. The replayed log then has the same tree of runs, steps, LLM calls and tool calls as the original.

1. When a replayed delegate call has a recorded nested run, the replay runs that nested agent again as a real nested run. It uses a `FakeLLM` built from that nested run's own `llm.completed` events and the same `_Recording` rules, applied per run. It does not reuse the recorded answer. Nested runs nested deeper are replayed the same way, at any depth.
   - Match a nested run to its call with the existing `_child_calls` logic (step and task), not by log order, because parallel calls overlap in the log.
   - Inside a nested run, apply the same rule as at the top: `read` and `compute` tools run again, while other tools and user answers reuse their recorded results.
   - The `recorded_changes` route (re-applying a nested run's state changes without running it) is no longer needed for nested runs that are replayed. Remove it if nothing else uses it. Otherwise keep it only for nested runs that have no recorded completions, and say which in a docstring.
2. Compare every run in the tree, not only the root:
   - the tool calls, in step order (reuse `_in_step_order` and `_compare_calls`);
   - the end of every nested run that finished (`_compare_end`).

   A difference raises `ReplayError` naming the run id and its agent, the step and the tool.
3. A paused run, or a nested run that is still waiting on the user, ends the replay at the same place, as today.
4. The `_ReplayStore` fallback to the original store stays for artifacts that a replayed nested run did not write itself.
5. Tests:
   - A unit test of a two-level tree, a driver whose call starts an agent with one tool call and an answer. The replayed log has the nested run's `llm.completed` and `tool.result` events.
   - A changed recorded completion in the nested run makes the replay raise, naming that nested run.
   - Parallel delegate calls in one step are matched correctly.
   - A three-level tree.
   - A 0.3.0 recording of a loop run still replays.
6. Remove the section K workaround: the e2e scripted design runs now check that `render_export(original) == render_export(replayed)`, ignoring only run ids and timestamps if they differ. Keep the existing single-agent replay test.
7. Replay time: the scripted e2e runs already take 60 to 100 s, because they replay their recording twice. With a full nested replay, check that the fast tier stays under 300 s. If an e2e test now replays a whole loop twice, replay once and compare both the export and the calls from that one replay.

## 4. Merge and finish (coordinator)

1. Merge V first, then R (R's e2e export check needs V's header). Resolve conflicts in `replay.py` by keeping both: V's version difference and R's nested replay.
2. Run `make test-all` and `make lint`, then replay every loop recording in `evals/recordings/` with `geomind replay` or the evals runner. All of them must pass.
3. Version: geomind `0.3.1` (additive: a new optional event field and a stronger replay). Update `CHANGELOG.md`, the snapshots and the docs.
4. Backend note in the report: `run.started` has a new optional field `versions` that is not streamed. Nothing in the backend has to change, but the backend may show it.
5. Push `origin main`.

## 5. Done when

- Every new run's log holds the geomind, gemini and python versions, and the export reads them from the log.
- A 0.3.0 log still loads, replays and exports.
- `geomind replay` of a DesignLoop or CompareLoop run replays every inner agent, and a changed inner completion is caught.
- The export of a replayed loop run equals the original's.
- The export header shows the run's own request.
- `make test-all` and `make lint` pass, and every loop recording replays.
- geomind 0.3.1 is pushed to `main`, with the docs and changelog updated.

## 6. Final report (at most 40 lines)

- The commits, with one line each.
- The test results (fast, slow, e2e, docker) and the fast-tier time before and after.
- What changed in the event schema, and how a 0.3.0 log is read.
- How a nested run is matched and replayed, and what was removed (`recorded_changes`, if removed).
- Anything still open, and the gemini requests, if any.

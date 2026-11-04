# geomind S1c: simplify before S2

Prompt for Claude Code, run in `/Users/sahand/Desktop/crust-team/geomind`.

## Goal

Make geomind smaller and more explicit before S2 builds on it. Six changes, each its own commit, behaviour unchanged except where stated. The rule behind all of them: **one concept, one implementation, nothing hidden.**

## 0. Read first

- `AGENTS.md` and every file in `.claude/docs/`.
- `../docs/contracts.md`: make the Version 9 change yourself, in the first commit's working tree (it is outside this repo, so it is not committed here):
  - in the first line, `Version 8` becomes `Version 9` with the note: "geomind drops checkpoints (the event log is the only run state): `save_checkpoint`/`load_checkpoint` and the internal `checkpoint` event are removed.";
  - in section 3, the interfaces version becomes `2.3` with "checkpoints removed, recovery and resume read `load_events` only";
  - delete the `save_checkpoint` and `load_checkpoint` lines of `RunStore`, and `checkpoint` from the list of internal events.

## 1. Rules

- Follow `.claude/docs/conventions.md` and `testing.md` exactly: simple, just enough code, nesting ≤ 3, functions about 40 lines, no comments in code, `NOTE:` decisions in docstrings, `geomind.errors` classes.
- While working run only the tests of changed files and their importers (`scripts/test_changed.py`, parallel); before each commit the full fast suite in parallel. Never the network.
- Deleting code is the goal: remove tests that only tested removed code; keep every test of behaviour that stays, adjusted to the new API.
- Update `AGENTS.md` and `.claude/docs/` in the same commit as each change, including the list of implicit mechanisms in `conventions.md`.
- Temporary files in `.tmp/`. Subagents use lighter models (Sonnet or Haiku).
- Commit on `main` after each step; push `origin main` at the end. Do not change `../gemini` or `../backend`.
- If something is missing, unclear or risky, stop and say so.

## 2. Steps

### Step 1: no hidden active run

- `runtime.py` keeps only the settings (`state`, `get`, `settings`, `load_state`). Remove `activate`, `active_run` and the `_active_run` context variable.
- The run is passed explicitly: `Context` carries the run session (`context.session`, or narrow methods on `Context` such as `complete`, `save_artifact`, `report_error`, `delegate`, `usage`; choose the smaller set and say which).
  - `Agent.complete(context, messages)` and `Agent.__call__(context)` use it.
  - Tool functions that need the run declare a first parameter `context`; `dispatch` passes it; plain tools stay plain functions without it. The tool schema never shows `context`.
  - Hooks receive the context as their first argument (`before_llm_call(context, agent, messages)`, and the same for the other two), so `TokenBudget` and `CostBudget` read `context.usage`.
- Remove "the active run" from the implicit mechanisms in `conventions.md`; describe the explicit flow in `agents.md`, `tools.md` and `hooks.md`.

### Step 2: the event log is the only run state

The contract (Version 9) drops checkpoints; a second path to the same state breaks "one concept, one implementation".

- Delete `engine/checkpoint.py`, the `checkpoint` internal event, `CheckpointSaved`, `CheckpointError` if nothing else raises it, and every `save_checkpoint`/`load_checkpoint` in stores, conformance checks, callbacks, loops and `run.py`.
- Everything a checkpoint held must already be in events; move what is not (loop state: record it on `step.finished` as an internal field, or as a `loop.state` internal event; pick one and say which).
- `Run.load`, `Engine.resume`, `Engine.replay` and crash recovery all read `store.load_events(run_id)` and `recover(events)` only. Keep the tests that kill a run mid-step and resume it without a second LLM call.
- The class of the root agent is stored in `run.started` as today. Drop support for runs recorded before the rename (there is no production data): delete `FORMER_PREFIX`, the `"swarm" + "ax.core."` string and the stored S1 run fixture, and remove the matching exemption from the name test. The name test then exempts only `CHANGELOG.md`.
- Update `events.md`, `engine.md`, `contracts.md` in `.claude/docs/`.

### Step 3: no metaclass on `Agent`

- Remove `_AgentMeta` and the sealing after `__init__`. Declarations are still recognised by `Agent.__setattr__` exactly as before; assigning after `__init__` is simply allowed, as in gemini's `Module`.
- Remove the tests of sealing; keep the tests of declaration order, duplicates and unknown types.

### Step 4: `stores/` package

- Move `engine/store.py` and `engine/workspace.py` into a new package `geomind/stores/` (`run.py` for `RunStore`, `MemoryRunStore`, `FileRunStore`; `workspace.py` for `Workspace`, `MemoryWorkspace`, `FileWorkspace`; `__init__.py` exporting them). Delete `geomind/stores.py`.
- Dependency order: `stores` sits right after `types` (it needs only types, errors and utils): `utils`, `errors` ← `types` ← `stores` ← `runtime` ← ... ← `engine` ← ... . Update the boundary test.
- `gd.stores` keeps the same public names.

### Step 5: delegation in one place

- Today `engine.py` has `run_child`, `_answer_child`, `_finish_delegate` and parts of `_answer` for sub-agents. Move all delegation logic into `engine/delegation.py` (functions taking the session), so `engine.py` reads as: run, resume, replay, end. `tools/delegate.py` stays the tool.
- No behaviour change; the delegate tests stay as they are.

### Step 6: size check

- Report the line counts before and after (`find geomind -name "*.py" | xargs wc -l | sort -n`), the files that got shorter, and any file over 250 lines with a one-line reason it cannot be split.
- If a step made some helper or type unused, delete it now.

## Done when

- No `active_run`, no checkpoint, no metaclass, no `engine/store.py`, no `swarm` string anywhere; tests enforce the last two.
- The full fast suite passes; Flake8, Black and isort are clean; six commits pushed to `origin main`.

## Report back

The chosen shape for the run on `Context` and where loop state now lives; line counts before and after; anything in `contracts.md` that should change; anything that got more complex instead of simpler.

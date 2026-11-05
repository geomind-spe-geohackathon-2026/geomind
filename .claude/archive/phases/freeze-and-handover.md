# Task: Freeze geomind's interfaces, clean `.claude/`, and write the handover plan

## 0. Context and rules

- **Goal.** Another team member takes over agent work (agents, tasks, evals) from now on. So that:
  - every interface the backend and the agent developer depend on is **final now and pinned by tests**; Sahand builds the backend against it and must never be broken later;
  - `.claude/` holds everything decided, built and still to do, so a new session (or a new person's Claude) can read the docs and continue without asking.
- **Workspace.** It is `/Users/sahand/Desktop/crust-team`. Change **only** `geomind/`.
  - You may read `../gemini/`, `../backend/` and `../docs/`, but never change them, including `../docs/contracts.md`. Section 7 says what to report instead.
  - Do not touch `../infrastructure/`.
- **Read first,** in this order:
  1. `../docs/geomind-handover.md`. Sahand copies it there from the project files before he starts you. It is the specification for section 2 and the list of decisions.
  2. `../docs/contracts.md`, the current file version (18 or later), sections 2 and 3.
  3. `../gemini/.claude/docs/api.md` and `../gemini/gemini/__init__.py`, gemini's current public API. Read only; use only names exported there.
  4. `AGENTS.md` and every file in `.claude/docs/`.
- **Pre-check.** `git status` is clean on `main`, and `git pull origin main` succeeds. No other Claude session or process is working inside `geomind/`; sessions in sibling folders do not block you. If machine load makes a 1 s budget test fail, rerun it alone before treating it as a failure, and say which ones you retimed.
- **Branch.** Work directly on `main`: commit after each section, and push `origin main` at the end. No other branch, no PR.
- **Nothing changes behaviour.** This task adds signatures, schemas, snapshots and docs. Every existing test stays green and keeps what it checks. Never delete or weaken a test.
- **Tests.**
  - While working, run only the tests of the changed files and of everything that imports them, in parallel (`make test` / `scripts/test_changed.py`).
  - Before each commit, run the full fast suite with `make test-all` and `make lint`.
  - No test calls the network, and no fast test runs over about 1 s.
  - Do not make a live OpenRouter run in this task.
- **Quality bar** (as in `.claude/docs/conventions.md`):
  - nesting at most 3 levels, functions about 40 lines at most, flake8 `max-complexity = 10`;
  - guard clauses, full-word names, explicit `gd.errors` classes;
  - no dead, speculative or golfed code;
  - **no comments inside code**: docstrings and `NOTE:` only;
  - no new runtime dependency.
- **Docs.** Every commit that changes behaviour or structure updates `AGENTS.md` or `.claude/docs/` in the same commit.
- **Temporary files** go to `.tmp/freeze/`.
- **Subagents** use lighter models: sonnet for code, haiku for read-only searches.
- **Stop and say so** when something is missing or risky, for example a gemini name you need that is not exported. Never guess a gemini name, and never import a gemini internal path.
- **Credentials** never go into code, tests, docs, events or logs. Do not read `../backend/.env`.

## 1. Clean `.claude/` and `AGENTS.md`

1. **Inventory.** List every file under `.claude/` and every link in `AGENTS.md`. Write the list to `.tmp/freeze/inventory.md`.
2. **Check every doc against the code.** Correct it in place wherever it is stale:
   - the contract version numbers: `.claude/docs/contracts.md` still says file version 15 and interface 2.5, so set them to the current ones;
   - gemini names that no longer exist;
   - the first package name as a Python package;
   - references to phases or files that do not exist;
   - commands and options that differ from `cli.py`;
   - tables of shipped agents and tools.
3. **One fact, one place.** Where two docs explain the same thing, keep it in the more specific doc and link to it from the other. Do not merge or rename doc files unless one is nearly empty, and say which you merged.
4. **Make `AGENTS.md` usable without the sibling folders.**
   - "Start here" first links `.claude/docs/plan.md` (section 2), then the rest.
   - The shared documents in `../docs/` are listed as optional background. Inside this repo, every rule a contributor needs is in `.claude/docs/`.
5. Leave `.tmp/` (git-ignored) alone, apart from your own folder.

Commit: `docs: clean .claude and AGENTS.md against the code`.

## 2. `.claude/docs/plan.md`: the handover plan

Create `.claude/docs/plan.md` from `../docs/geomind-handover.md`, and correct it against the code.

- **Keep its sections:** goal and inputs, repositories, design decisions with their reasons, gemini conventions, what is built, frozen interfaces, remaining work, how to work and open questions.
- **"What is built":** every row carries its commit hash. Correct anything the handover gets wrong about the code, and list each correction in the report.
- **"Remaining work":** S2b, S3 and S4 as numbered tasks. Each task names its files, the frozen tool or loop it implements, its tests and its "done when". After section 3, each task points to the stub it replaces.
- **No duplication:** if a fact is already in another `.claude/docs/` file, `plan.md` links to it instead of repeating it.
- Add one line at the top: "This file is the roadmap. Update it in the same commit that finishes or changes a task."

Commit: `docs: plan.md, the handover plan and roadmap`.

## 3. Freeze the agent developer's interfaces

### 3.1 `NotImplementedYet`

- Add `gd.errors.NotImplementedYet` (derives from `GeomindError` and `NotImplementedError`), documented in `errors.md`.
- Tool dispatch turns it into an error result with `code: "not_implemented"`. It does the same for gemini's own `gm.errors.NotImplementedYet`, so the model learns that the capability does not exist yet and does not retry.

### 3.2 One error-result shape

Tool error results take gemini's **Problem** shape: `{"error": {"path", "code", "message", "suggestions"}}`.

- A gemini error passes through its own `to_dict()` unchanged. `tools/dispatch.py` currently builds its own `{class, message}`; replace that.
- geomind's errors and Pydantic validation errors map to the same shape. Use `path` as the input field, and take `code` from a fixed list in `tools.md`: `invalid_input`, `unknown_name`, `not_implemented`, `not_allowed`, `timeout`, `internal`.
- An unexpected exception stays an `internal` result, is recorded and is reported by `on_error`, as it is today.
- Check what the `runlog` `tool_call.error` field now holds, and report it (section 7).

### 3.3 The full tool catalogue, up to S4

Every tool below exists now as a real `Tool`: final name, typed signature, docstring (its first line is the description the model sees), `effect` and `idempotent`.

- Tools marked **built** keep their code. Change only the error shape (3.2), and fix gemini names that no longer exist.
- Tools marked **stub** raise `NotImplementedYet("<tool> comes in <phase>")`.
- Before you write each gemini tool, map it to the gemini public name it will call. Put the mapping in `tools.md`, in a table of tool, gemini name and status. A tool with no gemini name is a **gap**: list it in the report and leave it as a stub. Do not invent gemini calls.
- Group the gemini tools in a package `geomind/tools/gemini/` (`catalogue.py`, `plants.py`, `runs.py`, `results.py`, `assessment.py`), re-exported from `gd.tools.gemini`, so each file stays small. Keep `gd.tools.gemini.<name>` as the public path.

| Tool | Effect | Inputs | Returns | Status, phase |
|---|---|---|---|---|
| `list_modules` | read | `category=None` | `[{name, category, summary}]` | stub, S2b |
| `describe_module` | read | `name` | gemini's module description | stub, S2b |
| `evaluate_module` | compute | `name, parameters, inlets=None, controls=None` | gemini's evaluate result (Values) | stub, S2b |
| `list_plants` | read | none | `[{name, summary}]` of the registered plants | stub, S2b |
| `read_plant` | read | `design=None` (`None` = the project's plant from `Workspace.plant`; otherwise a design reference) | the description with current values | stub, S2b |
| `build_plant` | write | `plant` (a plant dict; its input schema is gemini's plant schema), `name` | `{design, problems}`; a plant that fails validation returns the problems and stores nothing | stub, S2b |
| `list_profiles` | read | none | `[{name, quantity, unit, start, end}]` | stub, S2b |
| `read_profile` | read | `name, start=None, end=None` | a Value series | stub, S2b |
| `simulate` | compute | `design=None, changes=None, profile=None, start=None, end=None` | `{reference, summary}`; full results stored as an artifact | stub, S2b |
| `read_result` | read | `reference, path=None, field=None, start=None, end=None` | a Value series, or a summary | built; align to the Value shape |
| `check_results` | compute | `reference, limits=None` | `{passed, checks: [Check]}` (balances, limits, the hard limits) | stub, S3 |
| `compute_kpis` | compute | `reference, names=None` | `{name: Value}` | stub, S3 |
| `estimate_costs` | compute | `reference, assumptions=None` | `{capex, opex, lcoh, lcoc, npv, co2}` as Values, plus the assumptions used | stub, S3 |
| `optimize` | compute | `design, variables, objective, constraints=None, budget=None` | `{design, objective, history}` | stub, S4 (bonus) |
| `sample_uncertainty` | compute | `design, distributions, samples, metrics` | `{metric: {p10, p50, p90}}` as Values | stub, S4 (bonus) |
| `test_module` | execute | `path` | gemini's `check_module` report, run in the sandbox | stub, S3 |
| `search_documents` | read | `query` | `[{id, title, text, score}]` | built |

**Design references.**

- A *design* is a stored, validated plant dict. `build_plant` saves it with `RunStore.save_artifact(run_id, "design/<name>", plant_dict)` and returns `"design/<name>"`.
- A result reference is `"result/<id>"`. `read_result` already defines the stored shape; keep it, and write it down in `tools.md`.
- Freeze both formats in `tools.md`.

**Built tools that stay as they are:** `update_state`, `read_skill`, `ask_user`, `finish`, `run_python`, `read_file`, `write_file` and `Delegate`. Check that their names and schemas in the snapshot (3.6) match `tools.md`.

### 3.4 Loops and routing

- `LOOPS` in `run.py` holds `tool` (built), `design`, `makerchecker` and `compare`.
- `DesignLoop`, `MakerCheckerLoop` and `CompareLoop` exist in `geomind/loops/` with their final constructor signatures, taken from the S3 and S4 tasks in `plan.md`:
  - `DesignLoop(designer, verifier, max_rounds=5)`;
  - `MakerCheckerLoop(maker, checker, max_rounds=3)`;
  - `CompareLoop(loop, alternatives, criteria)`.
- Their `run` raises `NotImplementedYet`. Final names are fine if you need different ones; say which.
- `Route` has its final fields: `kind` (`"answer"` or `"loop"`), `loop` (one of the `LOOPS` names), `agent` (one of the `AGENTS` names) and `brief`. A route to a stub loop gives a run error with `stop_reason="not_implemented"`. Add `not_implemented` to the documented stop reasons, and report it (section 7).

### 3.5 Verification

- `geomind/verify/` exposes `gd.verify.verify(plant, results, *, requirements=(), limits=None) -> {passed, checks}`, built on gemini's checks. It is a stub for S3.
- The hook `gd.hooks.Verified` (on `before_finish`, it refuses to finish while the last verification failed) is a stub for S3.
- Signatures and docstrings are final.

### 3.6 Snapshots

- `scripts/snapshot_api.py` writes these files:
  - `tests/unit/snapshots/tools.json`: per tool, the name, the description's first line, effect, idempotent and input schema;
  - `tests/unit/snapshots/agents.json`: the declaration sections, the `Agent` methods and their signatures, `Prompt`, `Model`, `Output`, `Route`, `LOOPS` and `AGENTS` names, the eval task fields, and the `geomind chat` and `geomind` subcommands with their options.
- `tests/unit/test_frozen_api.py` compares the live package against them.
- When something differs, the test says exactly which item changed and what to do: raise `gd.__version__`, rerun the script, add a `CHANGELOG.md` entry, and tell Sahand if `contracts.md` is affected.
- The script refuses to overwrite a snapshot whose recorded version equals the current `gd.__version__`, unless `--allow-same-version` is passed. That flag is for additive, non-breaking changes, and the changelog says which.

Commit per subsection, or in two or three commits if that is cleaner.

## 4. Freeze the backend's interfaces

1. **Version.** `gd.__version__` follows semver below 1.0 (a breaking change raises the minor version), the same rule as gemini. Set it to `0.1.0` for this frozen state, unless it is already higher. Start `CHANGELOG.md` if it does not exist.
2. **`tests/unit/snapshots/api.json`.** The same script writes it, and the same test checks it. It holds:
   - the signatures of `gd.Run.__init__`, `start`, `astart`, `Run.load`, `resume`, `aresume` and `cancel`;
   - the `RunResult` fields, statuses and stop reasons;
   - the method names and signatures of the `RunStore`, `Workspace`, `LLM`, `Sandbox` and `SandboxProvider` protocols;
   - the methods of `Callback`;
   - the signatures of `gd.Permissions` and the shipped hooks;
   - the `Completion`, `Usage` and `Message` fields;
   - every event type, public or internal, with its `data()` keys;
   - the answer shapes;
   - the `gd.runlog` shape;
   - the top-level `gd.__all__`.
3. **JSON schemas** in `geomind/schemas/`, shipped as package data:
   - `events.json`: one schema per public event `data`;
   - `problem_state.json`;
   - `state_changed.json`: the JSON Patch subset;
   - `request.json` and `answer.json`;
   - `runlog.json`;
   - `tool_error.json`: the Problem shape of 3.2;
   - `eval_task.json`.

   Generate each one from the Pydantic model or dataclass that defines it, with the same script. Add one sample per schema in `geomind/schemas/samples/`. A test proves that each schema file equals the generated one, and that each sample loads through the real model. Use no new dependency: validate through the models, not `jsonschema`.
4. **Check the contract map.** Section 3 of the contract lists `RunStore` with 7 methods, `Workspace` with `plant` and `documents`, and the `Run` call shown there. Make sure `tests/unit/test_contract_map.py` and `api.json` cover every item in contracts.md sections 2 and 3. Do not change the code to fit the contract or the contract to fit the code; list every difference for section 7.

Commit: `api: freeze the backend and agent interfaces (0.1.0)`.

## 5. Docs for the frozen state

- In `.claude/docs/api.md`, add a section "Frozen interfaces". It lists what is frozen, where the snapshots and schemas live, the change rule (version, snapshot, changelog, contract note) and what is *not* frozen (prompt texts, skill texts, internal modules, model ids in `runtime.py`).
- In `.claude/docs/tools.md`, the tool table of 3.3 gets a status column, the gemini mapping, the error codes, and the design and result reference formats.
- `.claude/docs/agents.md` shows the shipped agents and which tools each one will get when filled.
- `.claude/docs/plan.md` tasks point to their stubs.
- `AGENTS.md` adds one rule: "Frozen interfaces change only with a version raise; see api.md".

## 6. Final checks and push

- Run `make test-all` and `make lint` once more, check that `git status` is clean, then `git push origin main`.
- Run `geomind chat --agent analyst --recording <an existing recording>` once to see that the CLI still works offline, and say whether it did.

## 7. Report back

Write the report to `.tmp/freeze/report.md` and print it, in English. It holds:

1. The commits, with one line each.
2. The doc corrections from section 1, and the corrections to the handover from section 2.
3. The tool-to-gemini mapping table, plus every **gap**: a tool with no gemini public name, with the name or shape it needs.
4. **Contract differences for Sahand**, as proposed edits to `docs/contracts.md`, never applied by you. At least:
   - the tool error shape in `runlog`;
   - the `not_implemented` stop reason;
   - `gd.__version__` and the schemas in `geomind/schemas/`;
   - anything in sections 2 and 3 that does not match the code.
5. What the backend must check when it installs this version.
6. Test counts and times, and any test you retimed.
7. Anything risky, missing or unclear.

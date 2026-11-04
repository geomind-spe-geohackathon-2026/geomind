# geomind S2: gemini tools, problem state, long conversations, one sample agent, agent skeletons and evals

Prompt for Claude Code, run in `/Users/sahand/Desktop/crust-team/geomind`.

## Goal

Make geomind useful on real geothermal questions. After this phase:

```
geomind run "What heat does the example doublet deliver at 150 m3/h?"
```

answers with numbers computed by gemini through the sample `Analyst` agent; every other agent exists as a skeleton with its prompt file, ready for another person to fill and test by hand (`geomind chat`) and by tasks (`evals/`); a shared problem state records goal, requirements, assumptions and results across messages; long chats stay under the context limit; and the eval runner is ready with one sample task.

## 0. Read first

- `AGENTS.md` and every file in `.claude/docs/`.
- `../docs/geomind-design.md` sections 3, 4, 11 and 12 (12 is this phase). If your copy has no section 12, stop and ask for the current file.
- `../docs/contracts.md` sections 2 and 3: it must be **Version 14 or later** (`step.finished` has `text`; section 3 is 2.5). If it is older, stop and ask for the current file.
- gemini's public API: `../gemini/AGENTS.md`, `../gemini/.claude/docs/api.md` and the docs it points to for the module registry, `Module.describe()`, plant loading and `gm.plants.migrate`. geomind uses **only** `import gemini as gm` public names, never `gemini.core` or any private path.

## 1. Rules

- Follow `.claude/docs/conventions.md` and `testing.md` exactly: simple, just enough code, nesting ≤ 3, functions about 40 lines, no comments in code, `NOTE:` decisions in docstrings, `geomind.errors` classes, guard clauses, full-word names.
- While working run only the tests of changed files and their importers (`scripts/test_changed.py`, parallel); before each commit the full fast suite in parallel. Never the network in tests: use `FakeLLM` and recorded completions. Tests that call gemini use small inputs and stay under the 1 s budget; mark anything slower for the release profile.
- Update `AGENTS.md` and `.claude/docs/` in the same commit as each change; add `context.md`, `gemini-tools.md` and `evals.md`; `agents.md` becomes the handover guide (step 5).
- Temporary files in `.tmp/`. Subagents use lighter models (Sonnet or Haiku).
- Develop on `main`, commit after each step, push `origin main` at the end. Do not change `../gemini` or `../backend`.
- If something is missing, unclear or risky, stop and say so. In particular, if gemini lacks a public name this prompt needs, do every step that does not need it, then stop and list exactly what is missing.

## 2. Steps

### Step 1: carry-overs from S1c and the contract

- `step.finished` data becomes `{index, usage, text}` (the step's full assistant text, `""` if none), as in the contract table.
- `text.delta` is no longer passed to `save_event`: it goes to callbacks only. Recovery and replay use `llm.completed`. Keep a test that a reloaded run's `runlog` and `step.finished.text` hold the full text.
- Export `gd.event_from_dict` at the top level (public-API test).
- Tools reach the workspace through `context.session` (add `session.workspace` back if that is the simplest).

### Step 2: problem state (`geomind/context/state.py`)

New package `geomind/context/`, placed right after `prompts` in the dependency order (`... ← prompts ← context ← providers ← ...`); update the boundary test.

- `ProblemState` (Pydantic): `version`, `goal`, `requirements`, `assumptions`, `design`, `results`, `verification`, `questions`, with the item shapes of design section 3 (`requirements`: id, text, metric, target, tolerance, status; `assumptions`: id, text, value, source, confirmed; `results`: id, summary, reference; `questions`: id, text).
- `apply_changes(state, changes)` takes JSON Patch operations exactly as the contract's `state.changed` (`add`, `replace`, `remove`; JSON Pointer; id-addressed lists; `-` appends an item that must have an `id`), validates the result against the model and returns a new state with `version + 1`; an invalid patch raises a `geomind.errors` class with a message that tells the model how to fix it. Reuse `types/patch.py` if it already does part of this.
- Tool `update_state(changes)` (`effect="write"`, allowed by default rule because it only touches the run's own notes): applies the changes and emits `state.changed {version, changes}`.
- The state is part of the run state, rebuilt from `state.changed` events by `recover`.
- Per chat: `Run` loads it with `store.load_state(chat)` at start (empty state when `None`) and saves it with `store.save_state(chat, state)` when the run ends.
- `render(state)`: compact text, one line per item, shown to the model by the context builder **after** the history (the last part of every call), never appended to the message list.

### Step 3: long conversations (`geomind/context/`)

- `history.py`: turns from `load_history` into messages; newest turns verbatim.
- `compaction.py`: when the rendered context passes `runtime.get("compaction_threshold")` (new setting, default 0.6 of the model's context window; the window per model in a small table with a safe default), older turns are replaced by one summary message written by the `Summarizer` agent (cheap model); the problem state and the last `runtime.get("compaction_keep_turns")` turns (default 6) stay verbatim. Record an internal `compaction` event holding the summary, so recovery reuses it and never summarises twice.
- `skills.py` and `geomind/prompts/skills/*.md`: tool `read_skill(name)` (`effect="read"`) returns one skill; the system prompt lists only skill names with one line each. First skills: `gemini-units` (units accepted and returned), `reading-results` (summaries, references, `read_result`). An unknown name returns an error result with the close match.
- Test: a scripted 50-turn chat with `FakeLLM` stays under the threshold, compacts once at the expected turn, and still answers a question about turn 3 from the summary.

### Step 4: gemini tools (`geomind/tools/gemini.py`)

Only gemini public API. Each tool declares its `effect`; inputs accept unit strings (`"150 m3/h"`), and gemini does every unit conversion.

| Tool | Effect | Does |
|---|---|---|
| `list_modules(category=None)` | read | names, categories and one-line summaries from gemini's registry |
| `describe_module(name)` | read | `Module.describe()`: parameters, controls, boundaries, inlets, outputs with units and bounds |
| `evaluate_module(name, parameters, inlets, controls)` | compute | one call of one module; outputs with units |
| `read_plant()` | read | the project's plant from the workspace, as a compact tree of modules and key parameters |
| `simulate(changes, profile)` | compute | a copy of the plant with parameter or control changes, run by gemini's engine over a short profile; full results saved as an artifact, a summary (min, max, mean, unit per field) returned with its reference |
| `read_result(reference, path, field, start=None, end=None)` | read | a slice of a stored result |
| `search_documents(query)` | read | the workspace's document search |

- Errors from gemini come back as error results with the gemini error class and message (dispatch already does this); check that gemini's close-match suggestions reach the model.
- `FileWorkspace.plant` loads plants through gemini's public loader (registry names). Old plant files go through `gm.plants.migrate(old_dict)` first; a file that fails migration is a clear workspace error.
- Plant templates (`list_plants`, `configure_plant`) are **not** in this phase.
- Tests use gemini's example doublet and the smallest profiles that show the behaviour.

### Step 5: one sample agent, skeletons for the rest

Defining and testing the other agents is handed to another person, so this step builds **one complete sample agent** and **the full, correct structure for every other agent**, empty but ready to fill.

**Sample agent, complete: `agents/analysis/analyst.py`** (plus `Summarizer`, which step 3 needs: cheap model, no tools, prompt `prompts/general/summarizer.md`)

- `Analyst` with the gemini tools, `update_state`, `read_skill`, `ask_user`, `finish`; strong model (`runtime` setting `analyst_model`, default `default_model`).
- Prompt `prompts/analysis/analyst.md`: role, how to use the tools (every number from a tool, units always stated), record assumptions and results in the problem state, ask when a needed value is missing, how to finish.
- `Run` uses `ToolLoop(Analyst())` for now, through a small explicit routing table in `run.py` (`LOOPS = {"tool": ToolLoop}`, `AGENTS = {"analyst": Analyst, ...}`), so later agents are added as rows. `CodeAssistant` stays selectable when a sandbox is configured.

**Skeletons, structure only (no behaviour):**

```text
geomind/agents/
├── agent.py
├── general/        assistant.py, summarizer.py   (summarizer complete: compaction uses it)
├── coordination/   coordinator.py
├── analysis/       analyst.py          (complete)
├── design/         designer.py
├── verification/   verifier.py
├── economics/      economist.py
└── reporting/      explainer.py
geomind/prompts/
└── <same folders>/<name>.md            one prompt per agent
```

- Each skeleton is a real `Agent` subclass with: a docstring stating its job (from design sections 6 and 12: coordinator routes, designer proposes configurations and sizes, verifier runs the physics checks, economist computes cost and CO2, explainer writes the answer for the user); its constructor sections with `# Prompt` loading its prompt file and `# Model` with its role setting; `# Tools` only with tools that already exist; no `forward` override.
- Each prompt file has the same fixed headings, empty below them except one line saying what goes there: `## Role`, `## Inputs`, `## Tools`, `## Rules`, `## Output`, `## Examples`. The analyst's prompt fills all of them and is the reference.
- `Coordinator` declares `Output(Route)` with `Route(kind="answer" | "loop", answer=None, loop="tool", agent="analyst", brief=None)` defined in its file, but `Run` does not call it yet.
- Skeletons are exported from `gd.agents`, are **not** in the routing table, and their status is "skeleton" in `agents.md`. `NOTE:` in each docstring: structure fixed now so another person can fill prompt, tools and tasks without changing the layout.
- One test per skeleton: it constructs, its prompt file exists and has all six headings, its sections are in order.

**How to add an agent: `.claude/docs/agents.md`** (the handover document): the folder and file to fill, the prompt headings, how to choose tools and effects, how to add it to the routing table, how to write its eval tasks, how to test it by hand. Short, with the analyst as the worked example.

### Step 6: testing agents by hand and by tasks

**By hand:** `geomind chat --agent analyst [--project PATH] [--live] [--model ID]`: an interactive terminal session with one agent. Each turn prints the streamed text, every tool call with its input and a short output, permission requests (answered in the terminal), and the problem state after the turn; `/state`, `/log` (the runlog of the last turn), `/reset` and `/quit` commands. Without `--live` it uses `FakeLLM` with a recording given by `--recording FILE`; with `--live` it uses OpenRouter. Runs are saved under `.runs/` so `geomind show` works on them. Any agent name in `gd.agents` works, so skeletons can be tried as soon as they are filled.

**By tasks:** `evals/` at the repository root.

```
evals/
├── tasks/<agent>/<name>.yaml     message, plant, criteria   (one folder per agent)
├── recordings/<agent>/<name>.jsonl
├── run.py                        python -m evals.run --agent analyst [--live]
└── reports/                      generated, git-ignored except summary.md
```

- A task file: `message`, optional `plant` and `history`, and `criteria` checked by code, never by an LLM: a number with tolerance against gemini's own result, a tool that must or must not be called, a question that must be asked, a problem-state field that must be set. The format is documented in `evals.md` with every field.
- Offline by default (`FakeLLM` from `recordings/`); `--live` runs OpenRouter and writes the recording. Without `OPENROUTER_API_KEY`, `--live` stops with a clear message.
- Report per task and total: passed, steps, tool calls, tokens, cost, time; `evals/reports/summary.md`.
- **Only one sample task** for the analyst: heat delivered by the example doublet at 150 m3/h, with a hand-written recording that makes realistic tool calls, so the runner and every criterion type are tested. Empty `tasks/<agent>/` folders (with a `.gitkeep`) for every skeleton agent.

## Done when

- `geomind chat --agent analyst --live` (with a key) and `geomind run "What heat does the example doublet deliver at 150 m3/h?"` answer through gemini tools.
- The problem state persists across two messages of one chat; `state.changed` events match the contract.
- The 50-turn chat test compacts once and keeps the answer.
- Every skeleton agent and its prompt file exist with the fixed structure; `agents.md` explains how to fill one.
- `python -m evals.run --agent analyst` passes the sample task offline and writes `summary.md`.
- The full fast suite passes; Flake8, Black and isort are clean; all steps committed and pushed to `origin main`.

## Report back

What was built; every gemini public name used and any that was missing; the eval table; whether a live run was possible and its token cost; anything in `contracts.md` that should change.

# geomind: brief for the design thread

This file hands the geomind work to a new thread. It holds everything decided so far, what is still open, and how Sahand likes to work. Read all of it before replying.

## 1. What geomind is

`geomind` is the agent package of the GEMINI system built for the SPE Europe Energy GeoHackathon. Agents take a task from the user (a question, or a design brief for a deep-geothermal heating and cooling system), use the `gemini` physics package as tools, check their own results with physics, and explain them. Every prompt, answer, tool call and token count is logged, because the competition asks for that log.

The competition:

- Challenge 1 (50%): an agentic AI workflow that analyses the problem, drives GEMINI, picks and runs models, fills missing models, compares alternatives and explains the configuration.
- Challenge 2 (50%): an integrated deep-geothermal heating and cooling design; report capacities, design, and the agent log (prompts, answers, token usage).
- Bonus: multi-agent, optimisation, uncertainty, techno-economics, automatic verification.

## 2. Where it sits

```
crust-team/                      (Sahand's machine: /Users/sahand/Desktop/crust-team)
├─ infrastructure/   docker-compose
├─ frontend/         React + Vite + Tailwind
├─ backend/          FastAPI
├─ geomind/          this package, its own repo
└─ gemini/           physics and engine (Python package)

frontend → backend → geomind → gemini
```

- geomind depends on `gemini` (editable path dependency `../gemini`) and never on the backend.
- The backend uses geomind through three interfaces it implements (`LLM`, `RunStore`, `Workspace`), passes callbacks and hooks, and calls `gd.Run(...)`. The only backend folder that imports geomind is `src/api/v1/assistant/runs/adapters/`.
- Every chat message goes through geomind. The backend never picks a loop or an agent; a coordinator agent in geomind does. The backend owns storage, access, the queue and the live stream (SSE); geomind owns understanding, loop choice, tools and memory.
- The PyPI name `geomind` belongs to Sahand.

## 3. Decisions already made

- **Four layers, nested:** prompt ⊂ context ⊂ harness ⊂ loop. The loop is the outer layer, not a class inside the harness. See `agent-engineering-layers.md`.
- **Three kinds of extension points:**
  - Interfaces: what geomind needs and cannot run without (LLM, store, workspace). Passed in.
  - Callbacks: observers that cannot change anything (`on_run_start`, `on_llm_call`, `on_tool_end`, ...). Same style as gemini's engine callbacks.
  - Hooks: can block or change (`before_llm_call`, `before_tool_call`, `before_finish`): allow, deny with reason, or a request to the user that pauses the run with a checkpoint.
- **Folder layout like gemini** (Sahand asked for this explicitly):

```text
geomind/
├── __init__.py       # curated `import geomind as gd`
├── utils/            # leaf
├── errors/           # leaf, every gd.errors class
├── providers/        # LLM providers behind one protocol: base, openrouter, fake
├── tools/            # like gemini.ops: Tool, registry, dispatch, built-ins, gemini tools
├── core/
│   ├── types/        # messages, completions, tool calls, usage, requests, results
│   ├── runtime.py    # context-local settings
│   ├── prompts/      # .md per role
│   ├── context/      # problem state, memory, compaction, retrieval
│   ├── verify/       # physics verifiers (balance, demand, bounds, units)
│   ├── agents/       # agent.py (Agent), container.py (Team), <category>/<name>.py
│   └── engine/       # Engine, step, callbacks, hooks, checkpoint, store, replay, results
└── loops/            # like gemini.optim: tool, design, makerchecker, compare
evals/  examples/  scripts/  tests/{unit,integration,e2e,fixtures}  .claude/docs/  AGENTS.md
```

- **Parallels with gemini** to keep wherever they fit: Agent ≈ Module, Team ≈ Sequential, Engine ≈ Engine, Callback ≈ Callback, hooks ≈ forward hooks (same `.remove()` handles), providers ≈ backends (renamed because LLM services are a different kind of thing), tools ≈ ops, loops ≈ optim, checkpoints ≈ checkpoints.
- **Naming:** `providers` (not `backends`, not `adapters`; `adapters` already means the backend's interface implementations). Folder names one word, lower case, no underscores.
- **Verification by physics:** no design reaches the user without passing numeric verifiers (balances, demand coverage, bounds, units). This is our advantage over coding agents.
- **Evals:** fixed tasks with criteria checked by code; compare loops on success, steps, tokens, cost and time. Record and replay LLM answers so loops can be tested without cost.
- **Phases:** S1 package and engine, S2 gemini tools and context and evals, S3 design agents and verified loops (Challenge 2), S4 compare loop and eval report. Backend and frontend run in parallel against `contracts.md`.

## 4. Open questions to think through

These are what the design thread is for. Think them through properly, propose, and discuss with Sahand before writing any prompt.

1. **The Agent class.** How close to gemini's `Module`? What is declared in `__init__` (prompt, tools, model, context policy)? What does `forward` take and return (context → action)? How do agents nest in a `Team`?
2. **Engine vs loop.** Where exactly is the line? What does one engine step mean? How does a loop drive the engine (like gemini `optim` drives `Engine.replay`)?
3. **Problem state.** Its shape, who writes it, how it is shown to the model, how it survives compaction and checkpoints.
4. **Tools from gemini.** How module metadata becomes a tool schema; how large results are summarised and fetched later; how errors come back.
5. **Hooks and requests.** The exact pause and resume model; what a request looks like; how a resumed run continues inside a loop.
6. **Multi-agent.** Coordinator and specialists: shared problem state vs messages; context isolation for sub-agents.
7. **Public API.** What `import geomind as gd` exposes; the smallest possible user code for a run, a custom agent, a custom loop.
8. **Contracts.** Check section 3 of `contracts.md` (the interfaces and `gd.Run`) against the design and propose changes if needed.
9. **What gemini must provide** (module metadata, plant dictionaries, economics) and whether anything is missing.
10. **gemini's own agent folder.** Sahand's local gemini copy had `gemini/agentic` and `gemini/design` folders that are not on GitHub. Ask him what is in them now: whatever is agent logic should move to geomind, so gemini stays physics and engine only.

## 5. Files to read

In the project folder:

- `phases/README.md`: all phases, shared rules.
- `phases/contracts.md`: HTTP API, live events, geomind interfaces.
- `phases/geomind/s1-engine.md` to `phase-4-compare-and-evals.md`: the current phase drafts. They are drafts; the design thread may change them.
- `research/agent-engineering-layers.md`: prompt, context, harness and loop engineering, with sources.
- `frontend/feature-map.md`: domains, features and use-cases of the whole product.

GEMINI package (GitHub `geomind/gemini-geothermal-suite-open`, branch `refactor`): `AGENTS.md` and every file in `.claude/docs/`, especially `conventions.md`, `modules.md`, `engine.md`, `errors.md`, `utils.md`, `runtime.md`, `testing.md`, `api.md`. Also `gemini/__init__.py`, `gemini/core/engine/callbacks.py`, `gemini/core/modules/module.py`. Read only; do not change that repo.

## 6. How Sahand works

- Writes in Persian; reply in Persian. Start every line with a Persian word, put English names in code blocks or follow them with a right-to-left mark, keep mixed lines short.
- This thread designs and writes prompts. Sahand runs the work in Claude Code on his own machine. Do not write code in a repo or push anything.
- During design talk, discuss only. Write or hand over a prompt only when Sahand says «go».
- Names matter a lot to him. Give every name a reason; prefer industry terms; avoid vague words.
- He wants the structure to follow gemini's, the API to be simple, and complexity hidden.
- Code quality bar for every prompt: simple and readable, just enough code, nesting at most 3, functions about 40 lines, no dead code, no comments inside code (docstrings only), guard clauses, full-word names.
- Every prompt: fast targeted tests while working (only changed code and its importers, in parallel), full fast suite before commit, never the network in tests; temporary files in `.tmp/`; update `AGENTS.md` and docs in the same commit; subagents use lighter models; say so when something is missing or risky; commit per step, no push until told.
- He accepts what he does not object to, but says clearly when he disagrees. Recommend one option; do not list many.

## 7. The first goal of the new thread

Design geomind in depth with Sahand, answering the open questions in section 4. When he says «go», write the Claude Code prompt for phase S1 into `phases/geomind/` (updating `s1-engine.md` or replacing it), following section 6.

# geomind S2: gemini tools, context and evals

## Goal

Agents can use every gemini module as a tool, keep a compact shared problem state, survive long conversations, and be measured on fixed tasks.

## Context

- Follow the shared rules in `../docs/phases.md` (section "Rules for every phase") and the contracts in `../docs/contracts.md`.
- Needs S1. Read `geomind/AGENTS.md`, `../gemini/.claude/docs/api.md`, `modules.md`, `equipment.md`, and `../docs/agent-engineering-layers.md` (context engineering section).

## Steps

### 1. Tools from gemini

`tools/gemini.py`:

- A few generic tools, not one tool per module (agreed in the design thread: a bloated tool set is a known failure mode): `list_modules(category)`, `describe_module(name)` (schema from `Module.help()` and each declaration's `schema`, `unit` and bounds; nothing described twice), `evaluate_module(name, parameters, inlets, controls)`, `list_plants`, `configure_plant(template, parameters)`, `simulate(plant, profile)`, `read_plant` and `search_documents` (through `Workspace`). The catalogue (name, class, category) is built in geomind from `gm.modules` exports, because gemini has no registry by design.
- Results are compact: large arrays are stored and returned as a reference with a short summary (min, max, mean, units); a `read_result` tool fetches slices when needed.
- Tool errors come back as results with the `gm.errors` class and message, so the model can fix its call.

### 2. Context

`core/context/`:

- `state.py`: `ProblemState`, the structured shared state of a task (goal, requirements, assumptions, chosen design, results, open questions). Agents read and update it through tools; it is shown to the model in a compact rendered form at every step.
- `memory.py`: history selection for a chat (recent turns plus the problem state).
- `compaction.py`: summarise older turns when the context passes a limit; keep the problem state and the last turns verbatim.
- `retrieval.py`: just-in-time loading through tools instead of pasting data into prompts.

### 3. Coordinator

`core/agents/coordination/coordinator.py`: reads the message and the problem state, answers directly or picks a loop. For now the only loop is `ToolLoop`; S3 adds more. The backend never chooses; this agent does.

### 4. Evals

```
evals/
├── tasks/<area>/<name>.yaml   task, inputs, success criteria (numbers with tolerances)
├── run.py                     python -m evals.run --loop tool --tasks basics
└── reports/                   generated, git-ignored except a summary
```

- Criteria are checked by code (numbers from gemini), never by an LLM alone.
- Report per task: passed, steps, tool calls, input and output tokens, cost, time.
- Start with five tasks on the example doublet (operating point, pump at another frequency, heat delivered, a missing parameter that needs `ask_user`, a module lookup).
- Recorded completions from eval runs become fixtures for replay tests.

## Done when

- `geomind run "What heat does the example doublet deliver at 150 m3/h?"` answers with gemini numbers, through tools.
- A 50-turn scripted conversation stays under the context limit through compaction and still answers correctly.
- `python -m evals.run` writes a report for the five tasks.
- Docs describe tools, context and evals.

## Report back

The eval table, token cost, any gemini metadata that was missing or unclear for building tools, and suggested contract changes.

# geomind Python package

geomind is the agent harness of the crust-team product: agents, an engine over an event log,
tools, permissions, and the `Run` facade the backend uses.
`gemini` is its physics library.

Use `import geomind as gd`. `gm` stays gemini's alias.

Read [docs/rules.md](docs/rules.md) first: it holds every project rule.

## First: ask the mode

At the start of every session, before any change, ask the user which mode this session works in:
development, production or hotfix (QA), as the project root's `docs/ops/development-modes.md`
defines them. Work by that mode's rules until the user changes it; without an answer, change
nothing.

## Read both: `.claude/` for agents, `docs/` for people

`.claude/` is written for agents: start with [.claude/README.md](.claude/README.md) (its
`docs/` reference, `notes/` current work, `archive/` history). `docs/` is written for people:
design, contracts, reports, bug lists. Read both, and the project-wide context in the project root
`geomind-spe-hackathon-2026/`, the parent folder of this clone: its `AGENTS.md`, the shared
memory `.claude/memory/MEMORY.md` and `docs/`. One clone, no git worktrees.

## Start here

- [Plan](.claude/docs/plan.md): the goal, the decisions and their reasons, what is built, and the
  numbered remaining work. Start with this file.

How to test is in [Testing: Test profiles](.claude/docs/testing.md#test-profiles).

Read every file in `.claude/docs/` before changing the repository:

- [Public API](.claude/docs/api.md): the curated `import geomind as gd` names and workflows.
- [Conventions](.claude/docs/conventions.md): dependencies, naming, comments, code quality and
  implicit mechanisms.
- [Contracts](.claude/docs/contracts.md): how geomind implements the backend contract.
- [Agents](.claude/docs/agents.md): `Agent`, `Prompt`, `Output`, `Model` and declarations.
- [Context](.claude/docs/context.md): the problem state, long conversations and skills.
- [Engine](.claude/docs/engine.md): steps, the log, recovery, resume and replay.
- [Events](.claude/docs/events.md): every event type, public or internal, with its JSON.
- [Tools](.claude/docs/tools.md): `Tool`, `@tool`, dispatch, built-ins, code tools and `Delegate`.
- [Providers](.claude/docs/providers.md): the `LLM` protocol, retries, `OpenRouter` and `FakeLLM`.
- [Hooks](.claude/docs/hooks.md): decision points, decisions and the shipped hooks.
- [Permissions](.claude/docs/permissions.md): rules, modes and the fixed decision order.
- [Runtime](.claude/docs/runtime.md): context-local settings.
- [MCP](.claude/docs/mcp.md): the tools of the MCP servers a run is given.
- [Errors](.claude/docs/errors.md): the `gd.errors` classes and when each is raised.
- [Evals](.claude/docs/evals.md): testing an agent by tasks, offline or live.
- [Testing](.claude/docs/testing.md): tiers, test profiles, budgets, fixtures and CI.
- [Releasing](.claude/docs/releasing.md): installs, updating gemini and publishing a release.
- [Utilities](.claude/docs/utils.md): the `geomind.utils` helpers and how to add one.

The docs for a new session are in [.claude/docs/](.claude/docs/plan.md), so this repository works
on its own; the project rules are in [docs/rules.md](docs/rules.md). Keep both current: they say
what the code does now. The shared contract between the repositories is the backend's
`docs/app-build/contracts.md`; the tests read a copy of it,
[tests/fixtures/contracts/shared.md](tests/fixtures/contracts/shared.md), and
[contracts.md](.claude/docs/contracts.md) maps it to the code.

Changes by version are in [docs/CHANGELOG.md](docs/CHANGELOG.md). `README.md` and `docs/` are for
people; `.claude/docs/` is for agents.

## Layout

```text
geomind/
├── __init__.py       # curated import geomind as gd API
├── __main__.py       # python -m geomind runs the command line
├── cli.py            # geomind run, chat, replay, show
├── run.py            # Run: the facade the backend uses
├── testing/          # conformance checks for RunStore and Workspace implementations
├── utils/            # leaf: hooks, context settings, time, json, strings
├── errors/           # leaf: every gd.errors class
├── types/            # messages, decisions, results, events, redaction, runlog
├── stores/           # RunStore, Workspace and their memory and file implementations
├── runtime.py        # context-local settings
├── prompts/          # <team>/<name>.md role files, skills/*.md and Prompt
├── context/          # problem state, compaction, skills: the deterministic part
├── providers/        # LLM protocol, retry layer, OpenRouter, FakeLLM
├── mcp/              # a small MCP client: list_tools, McpClient, McpError
├── schemas/          # JSON schemas and samples of the exchanged documents, generated
├── tools/            # Tool, tool decorator, dispatch, built-ins, Delegate, Team, gemini/
├── verify/           # verification of a design over gemini's checks
├── agents/           # Agent, AgentResult, Model, Output; <team>/<name>.py per agent
├── engine/           # engine, session, step, delegation, log, recovery, state, context,
│                     # callbacks, hooks, permissions, replay, compaction
└── loops/            # Loop, ToolLoop, DesignLoop, CompareLoop
examples/             # area/category/NN_name.py
scripts/              # test_changed.py, the development test profile; snapshot_api.py
evals/                # tasks/, recordings/, reports/ and the runner, run.py
tests/                # unit mirror, integration, e2e and recorded fixtures
docs/                 # for people: rules.md, CHANGELOG.md
```

## The gemini parallels

| gemini | geomind | Meaning |
|---|---|---|
| `Module`, one tick | `Agent`, one decision | declarations in `__init__`, behaviour in `forward` |
| `ModuleResult` | `AgentResult` | built by `__call__`, never by user code |
| `Engine.simulate/replay` | `Engine.run/replay/resume` | drives the unit over steps, finite |
| `Callback` | `Callback` | observers, same method style |
| forward pre-hooks | `before_*` hooks | can deny or pause; registration returns a handle |
| `gemini.backends` | `geomind.providers` | implementations behind one protocol |
| `gemini.ops` | `geomind.tools` | the primitive actions with dispatch |
| `optim` (drives `Engine.replay`) | `loops` (drive `Engine.run`) | algorithms over the engine |
| saved runs | the event log | resume anywhere, in another process |

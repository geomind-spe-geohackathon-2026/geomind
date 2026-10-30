# geomind Python package

geomind is the agent harness of the crust-team product: agents, an engine over an event log,
tools, permissions, a sandbox for model-written code, and the `Run` facade the backend uses.
`gemini` is its physics library.

Use `import geomind as gd`. `gm` stays gemini's alias.

The name `geomind` on PyPI belongs to an unrelated, abandoned package. Keep `name = "geomind"` in
`pyproject.toml` for local and editable installs, and do not publish.

## Start here

Test with the development profile (`make test`); see
[Testing: Test profiles](.claude/docs/testing.md#test-profiles).

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
- [Sandbox](.claude/docs/sandbox.md): where model-written code runs and what it cannot reach.
- [Runtime](.claude/docs/runtime.md): context-local settings.
- [Errors](.claude/docs/errors.md): the `gd.errors` classes and when each is raised.
- [Testing](.claude/docs/testing.md): tiers, test profiles, budgets, fixtures and CI.
- [Utilities](.claude/docs/utils.md): the `geomind.utils` helpers and how to add one.

The shared documents of all repositories are outside this one: the
[agreed design](../docs/geomind-design.md), the [contracts](../docs/contracts.md), the
[engineering layers](../docs/agent-engineering-layers.md), the
[harness review](../docs/open-source-harnesses.md) and the [phases](../docs/phases.md).

When a commit changes behaviour, structure or conventions, update the relevant document in the
same commit, so a new session can read the docs and know the current state.

## Branching

Work directly on `main`: commit after each step and push `origin main` when a phase ends. Do not
create another branch.

Test before each commit with `make test`, then `make test-all` and `make lint`.

## Layout

```text
geomind/
├── __init__.py       # curated import geomind as gd API
├── __main__.py       # python -m geomind runs the command line
├── cli.py            # geomind run, replay, show
├── run.py            # Run: the facade the backend uses
├── testing/          # conformance checks for RunStore and Workspace implementations
├── utils/            # leaf: hooks, context settings, time, json, strings
├── errors/           # leaf: every gd.errors class
├── types/            # messages, decisions, results, events, redaction, runlog
├── stores/           # RunStore, Workspace and their memory and file implementations
├── runtime.py        # context-local settings
├── prompts/          # <role>.md files and Prompt
├── context/          # problem state, compaction, skills: the deterministic part
├── providers/        # LLM protocol, retry layer, OpenRouter, FakeLLM
├── sandbox/          # Sandbox and SandboxProvider protocols, Manifest, local, docker
├── tools/            # Tool, tool decorator, dispatch, built-ins, code tools, Delegate
├── agents/           # Agent, AgentResult, Model, Output, general/assistant.py
├── engine/           # engine, session, step, delegation, log, recovery, state, context,
│                     # callbacks, hooks, permissions, replay
└── loops/            # Loop, ToolLoop
examples/             # area/category/NN_name.py
scripts/              # test_changed.py, the development test profile
tests/                # unit mirror, integration, e2e and recorded fixtures
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

# Implementation conventions

Write for Python 3.11, the oldest supported version (3.11 to 3.14), and use Black, isort,
100-character lines and Flake8 with docstrings. Record an intentional decision as a `NOTE:`
sentence in the docstring of the function, class or test that makes it.

## Dependencies

A package may import only the packages to its left:

`geomind.utils`, `geomind.errors` ← `types` ← `runtime` ← `prompts` ← `providers`
← `sandbox` ← `tools` ← `agents` ← `engine` ← `stores` ← `loops` ← `run` ← `testing`
← `cli` ← `geomind/__init__`.

`tests/unit/test_package_boundaries.py` enforces this order.

- `types` sits below `providers` because a provider returns a `Completion`.
- `sandbox` sits below `tools` because the code tools use it.
- `tools.delegate` reaches the engine only through `context.session`, never by import. The same
  goes for `Agent.complete`, `dispatch`, the code tools and the hooks. The context is passed
  explicitly; nothing reaches the run through hidden state.
- `geomind.utils` and `geomind.errors` are leaf packages: they import only the standard library,
  installed dependencies and themselves.
- `import geomind` does not import `gemini`, which takes more than a second. `FileWorkspace.plant`
  reaches it only through the class a plant file names. `dispatch` recognises `gemini.errors`
  classes by the module path in their class hierarchy.

The folder `types` shares its name with the standard library module. This is safe because every
import is absolute (`geomind.types`); never put the package folder itself on `sys.path`.

`context/` (problem state, compaction) arrives in S2 and `verify/` in S3.

The import alias is `gd` (`import geomind as gd`), not `gm`, which is gemini's.

## Agent rules

1. Declare in `__init__`, after `super().__init__()`.
2. Constructor sections are `# Agents`, `# Prompt`, `# Tools`, `# Output`, `# Model`, in that
   order, with empty sections omitted.
3. `forward` is exactly `async def forward(self, context)` and returns an `Action`. Override it
   only for a rule-based step.
4. Do not construct `AgentResult` in agent code; `Agent.__call__` creates it.
5. There is no `Team` and no agent container: the order of agents is a policy, and policies are
   loops.

## Naming

Use full words, not abbreviations. Booleans read as questions (`is_waiting`, `has_request`). Add a
unit suffix only where the type does not carry the unit, such as `TEST_BUDGET_S`. Folder names are
one word, lower case, without underscores.

Never name the framework that gemini's module design resembles, nor any other agent framework, in
code, docstrings, examples or documents; describe the concept itself.
`test_no_framework_names_in_tracked_text_files` in `tests/unit/test_code_quality.py` fails on any
occurrence in a tracked file. The shared `../docs/` research notes are outside this repository.

## Comments

The only comments allowed in code are:

- the fixed section headers of an agent constructor: `# Agents`, `# Prompt`, `# Tools`,
  `# Output`, `# Model`;
- tool directives with a specific code: `# noqa: <code>`, `# type: ignore[<code>]` and
  `# pragma: no cover`.

Everything worth explaining goes into docstrings. A decision is a `NOTE:` sentence in the
docstring, never a comment. `test_only_section_headers_and_tool_directives_are_comments` checks
every Python file in `geomind/`, `examples/`, `tests/` and `scripts/`.

## Code quality

- Flat code: nest at most three blocks deep (an `elif` chain counts once), prefer guard clauses
  and write no `else` after `return` or `raise`.
- Small functions: about 40 lines of body and one job each. The documented exceptions, each with
  its reason, are listed in `LONG_FUNCTIONS` in `tests/unit/test_code_quality.py`.
- McCabe complexity at most 10 (`max-complexity = 10` in `pyproject.toml`).
- Just enough code: no dead code, unused options or parameters, speculative generality or golfed
  one-liners.
- Clear names, as in [Naming](#naming).
- Explicit errors: raise an `gd.errors` class (see [errors.md](errors.md)), never a bare `except`,
  and no silent fallback that hides a failure.
- A bug gets a failing test first; the fix makes it pass.

Enforcement: `tests/unit/test_code_quality.py` checks nesting, function length, `else` after an
early exit, builtin raises, comments and framework names. Flake8 (`make lint` and the Lint
workflow) checks complexity (C901), bare `except` (E722), unused imports and variables (F401,
F841) and docstrings. The remaining points are checked in review.

## Implicit mechanisms

The package avoids hidden behaviour. These are the only implicit mechanisms, each with its reason:

- `Agent.__setattr__` registers what `__init__` assigns: a `Tool` goes to the ordered tool
  registry, an `Agent` becomes a child with a dotted path, and a `Prompt`, `Output` or `Model` fills
  its one slot. Constructors therefore read as plain assignments in section order. Unknown or
  duplicate names raise `DeclarationError` with a close-match suggestion.
- `Tool` looks at the first parameter of its function: one named `context` receives the run's
  context from `dispatch` and is left out of the schema, so a tool that needs the run says so in
  its signature and every other tool stays a plain function.
- `gd.runtime.settings()` is a context setting built on `geomind.utils.context.ContextSetting`: a
  context variable change usable as a `with` block and as a decorator, restored on exit.
- `class_path`/`import_class` in `utils/imports.py` are the only import-by-string: `run.started`
  names the agent class that rebuilds a run, and a plant file names its plant class.
- `Callback.on_<event>` methods are found through the `CALLBACK_METHODS` table in
  `engine/callbacks.py`, so a callback overrides only the methods it needs.

Adding another implicit mechanism needs a reason of the same weight and an entry here.

## Departures from gemini

Each one also has a `NOTE:` in the docstring that makes it.

- The core is `async`, with a sync facade on `Run`. gemini is sync. Parallel tools, streaming and
  the FastAPI backend need it, and changing it later would touch every layer.
- Stores and workspaces stay sync, for the backend, and are called through `asyncio.to_thread`.
- The event log is the only run state: `apply(state, event)` is the only code that changes it,
  and there is nothing like gemini's separate saved run record.
- Hooks can deny or pause. gemini's pre-hooks observe or adjust inputs.
- `Agent` has no `__getattr__` and keeps no values: declarations are plain attributes, and values
  of one run live in the session.
- The dependency order adds `stores`, the small module behind `gd.stores`, after `engine`.
- `engine/session.py` is one file beyond the layout of the S1 prompt: the object behind
  `context.session`.
- Tool names follow the attribute of the agent that declares them, on a copy of the tool.

## Parallels with gemini

The table is in [AGENTS.md](../../AGENTS.md#the-gemini-parallels).

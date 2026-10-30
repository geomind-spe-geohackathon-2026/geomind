# Runtime settings

`sx.runtime` holds context-local process settings and the active run, in
`swarmax/core/runtime.py`.

- `get(name)`, `state()`, `load_state(mapping)` and `settings(**changes)`, usable as `with` and as
  a decorator, built on `swarmax.utils.context.ContextSetting`.
- Settings: `default_model` (from `SWARMAX_MODEL`, else `FIXED_DEFAULT_MODEL`), `max_steps`,
  `retry_count`, `retry_delay`, `request_timeout`, `tool_result_limit` (characters),
  `delegate_summary_tokens`, `sandbox_timeout`, `sandbox_memory`, `sandbox_disk`, `sandbox_cpu`.

Unknown names raise `sx.errors.UnknownNameError`. asyncio tasks and `asyncio.to_thread` workers
start from a copy of their creator's context, while new threads start from the defaults. A run
stores the settings it starts with, and a resumed run applies them again.

## The active run

`activate(run)` makes a run active for a `with` block, and `active_run()` returns it or raises
`RunError`. It is the session of `swarmax/core/engine/session.py`: `Agent.complete`, `dispatch`,
the code tools, `Delegate` and the budget hooks reach the provider, store and sandbox through it,
so none of them imports the engine. This is an implicit mechanism, listed in
[conventions.md](conventions.md#implicit-mechanisms).

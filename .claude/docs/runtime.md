# Runtime settings

`gd.runtime` holds context-local process settings, in `geomind/runtime.py`.

- `get(name)`, `state()`, `load_state(mapping)` and `settings(**changes)`, usable as `with` and as
  a decorator, built on `geomind.utils.context.ContextSetting`.
- Settings: `default_model` (from `GEOMIND_MODEL`, else `FIXED_DEFAULT_MODEL`), `max_steps`,
  `retry_count`, `retry_delay`, `request_timeout`, `tool_result_limit` (characters),
  `delegate_summary_tokens`, `sandbox_timeout`, `sandbox_memory`, `sandbox_disk`, `sandbox_cpu`.

Unknown names raise `gd.errors.UnknownNameError`. asyncio tasks and `asyncio.to_thread` workers
start from a copy of their creator's context, while new threads start from the defaults. A run
stores the settings it starts with, and a resumed run applies them again.

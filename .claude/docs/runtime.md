# Runtime settings

`gd.runtime` holds context-local process settings, in `geomind/runtime.py`.

- `get(name)`, `state()`, `load_state(mapping)` and `settings(**changes)`, usable as `with` and as
  a decorator, built on `geomind.utils.context.ContextSetting`.
- Settings: `default_model` (from `GEOMIND_MODEL`, else `FIXED_DEFAULT_MODEL`), `max_steps`,
  `retry_count`, `retry_delay`, `request_timeout`, `prompt_caching` (true: see
  [providers.md](providers.md#openrouter)), `tool_result_limit` (characters, 40 000: a
  plant's description with its spec fits),
  `delegate_summary_tokens`, `sandbox_timeout`, `sandbox_memory`, `sandbox_disk`, `sandbox_cpu`,
  `compaction_threshold` (a share of the model's window), `compaction_keep_turns`.
- Role settings: `analyst_model`, `designer_model`, `verifier_model`, `economist_model` and
  `explainer_model` are `None`, which means `default_model`; `coordinator_model` and
  `summarizer_model` default to `FIXED_CHEAP_MODEL`.

Unknown names raise `gd.errors.UnknownNameError`. asyncio tasks and `asyncio.to_thread` workers
start from a copy of their creator's context, while new threads start from the defaults. A run
stores the settings it starts with, and a resumed run applies them again.

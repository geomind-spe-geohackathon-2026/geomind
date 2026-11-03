# Runtime settings

`gd.runtime` holds context-local process settings, in `geomind/runtime.py`.

- `get(name)`, `state()`, `load_state(mapping)` and `settings(**changes)`, usable as `with` and as
  a decorator, built on `geomind.utils.context.ContextSetting`.
- Settings: `default_model` (from `GEOMIND_MODEL`; unset is `None`, and a real provider refuses to call), `max_steps`,
  `max_steps` (`GEOMIND_MAX_STEPS`; no default: a run without it refuses to start; at the limit
  the run waits on `continue` or `stop`), `retry_count` and `retry_delay` (`GEOMIND_RETRY_COUNT`,
  `GEOMIND_RETRY_DELAY`; no value of
  geomind's own, required for a live run, as `runtime.model_problems()` and
  `missing_model_settings()` report), `request_timeout`, `prompt_caching` (true: see
  [providers.md](providers.md#openrouter)), `tool_result_limit` (characters, 40 000: a
  plant's description with its spec fits),
  `delegate_summary_tokens`, `sandbox_timeout`, `sandbox_memory`, `sandbox_disk`, `sandbox_cpu`,
  `compaction_threshold` (a share of the model's window), `compaction_keep_turns`.
- Role settings: `analyst_model`, `designer_model`, `verifier_model`, `economist_model` and
  `explainer_model` are `None`, which means `default_model`; `coordinator_model` and
  `summarizer_model` come from `GEOMIND_CHEAP_MODEL`, else `None` (no model id is built in).
  `role_models()` returns the model of every role; `missing_model_settings()` names the unset
  variables. `context_window` (`GEOMIND_CONTEXT_WINDOW`, tokens) and `cache_marked_models`
  (`GEOMIND_CACHE_MARKED_MODELS`, comma-separated model id prefixes) default to `None`: see
  [providers.md](providers.md#openrouter) and [context.md](context.md).
- `provider`: the OpenRouter providers to try, in order (see
  [providers.md](providers.md#openrouter)), from `GEOMIND_PROVIDER` (comma-separated slugs, for
  example `relace/fp4`); `None` lets OpenRouter choose.

Limits of spending and time are not settings: `answer_reserve` and the prices belong to a budget
hook (see [hooks.md](hooks.md#shipped-hooks)), which keeps no default and is off when unset.

Unknown names raise `gd.errors.UnknownNameError`. asyncio tasks and `asyncio.to_thread` workers
start from a copy of their creator's context, while new threads start from the defaults. A run
stores the settings it starts with, and a resumed run applies them again; a setting added after
the run was stored (`ADDED_SETTINGS`) takes its default.

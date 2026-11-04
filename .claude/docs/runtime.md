# Runtime settings

`gd.runtime` holds context-local process settings, in `geomind/runtime.py`.

- `get(name)`, `state()`, `load_state(mapping)` and `settings(**changes)`, usable as `with` and as
  a decorator, built on `geomind.utils.context.ContextSetting`.
- Settings: `max_steps` (`GEOMIND_MAX_STEPS`; no default: a run without it refuses to start; at the limit
  the run waits on `continue` or `stop`), `retry_count` and `retry_delay` (`GEOMIND_RETRY_COUNT`,
  `GEOMIND_RETRY_DELAY`; no value of
  geomind's own, required for a live run, as `runtime.model_problems()` and
  `missing_model_settings()` report), `request_timeout`, `prompt_caching` (true: see
  [providers.md](providers.md#openrouter)), `tool_result_limit` (characters, 40 000: a
  plant's description with its spec fits),
  `delegate_summary_tokens`,
  `compaction_threshold` (a share of the model's window), `compaction_keep_turns`.
- Role settings: one per model agent of `ROLES` (the class name in lower case), `<role>_model`,
  from its own `GEOMIND_<ROLE>_MODEL`: `GEOMIND_ANALYSISLEAD_MODEL`, `GEOMIND_CASELEAD_MODEL`,
  `GEOMIND_COORDINATOR_MODEL`, `GEOMIND_DESIGNLEAD_MODEL`, `GEOMIND_ECONOMIST_MODEL`,
  `GEOMIND_EXPLAINER_MODEL`, `GEOMIND_GEOSCIENTIST_MODEL`, `GEOMIND_REVIEWER_MODEL`, `GEOMIND_SUMMARIZER_MODEL`, `GEOMIND_PROCESSENGINEER_MODEL`,
  `GEOMIND_INTEGRATIONENGINEER_MODEL`, `GEOMIND_RESERVOIRENGINEER_MODEL`,
  `GEOMIND_WELLENGINEER_MODEL`, `GEOMIND_ENERGYSYSTEMSENGINEER_MODEL`, `GEOMIND_PROJECTLEAD_MODEL`,
  `GEOMIND_SUPPORTLEAD_MODEL`, `GEOMIND_CURATOR_MODEL`. `design_concurrency`
  (`GEOMIND_DESIGN_CONCURRENCY`, required for a live run, no default) bounds how many engineers
  of the design team fill their parts side by side. `engineer_max_steps`
  (`GEOMIND_ENGINEER_MAX_STEPS`, required for a live run, no default) is an engineer's own step
  limit: at it the engineer's run ends with what it has, with no question to the user.
  `knowledge_dir` (`GEOMIND_KNOWLEDGE_DIR`) is the command line's knowledge base folder, required
  for a run with a project; a backend gives its knowledge through the workspace instead. The
  `evolve_*` settings (`GEOMIND_EVOLVE_EVALUATIONS`, `_POPULATION`, `_SEED`, `_POLISH`) are
  `evolve_structure`'s, required for a live run. So are its two stops, gemini's
  `evolve(stop=...)`: `evolve_stop_generations` (`GEOMIND_EVOLVE_STOP_GENERATIONS`, the
  generations in a row with no new design on the feasible front) and `evolve_stop_seconds`
  (`GEOMIND_EVOLVE_STOP_SECONDS`, a time limit); each is a number or `off`, and both `off` spend
  the whole budget. Unset is
  `None`, with no fallback: there is no `GEOMIND_MODEL`, `GEOMIND_CHEAP_MODEL` or
  `default_model` since 0.4.22, and no model id is built in. `geomind run --model ID` sets every
  role's model.
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
the run was stored (`ADDED_SETTINGS`) takes its default, and one removed since
(`REMOVED_SETTINGS`: the sandbox settings, `default_model` and the old role names) is dropped.

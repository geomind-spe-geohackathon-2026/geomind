# Hooks

Three decision points that can deny or pause a run, in `geomind/engine/hooks.py`. A hook
derives from `gd.hooks.Hook` and overrides any of `before_llm_call(context, agent, messages)`,
`before_tool_call(context, agent, call)` and `before_finish(context, agent, action)`, plain or
`async`. The context gives the hook the run: `context.usage` and `context.session`. Each returns
`None` (no objection), `Deny(reason)` or a `Request`; `before_tool_call` may also return
`Allow(input=...)` to change the input.

| Decision | `before_llm_call` | `before_tool_call` | `before_finish` |
|---|---|---|---|
| `None` | call | call | finish |
| `Deny` | run stops, `denied` | tool skipped, reason is its result | finish refused, reason fed back |
| `Request` | pause | pause before the tool | pause before the answer |

The first objection wins, in registration order. An `Allow` does not skip the permission rules.
`Cancel`, a kind of `Deny`, ends the run with `cancelled` at any point.

Register with `engine.register_hook(hook)`, which returns a handle with `.remove()`. Hooks are code,
so they are passed again when a run resumes in another process.

## Shipped hooks

- `TokenBudget(max_tokens, answer_reserve=None, answer_agents=None, bound_input=False)` and
  `CostBudget(max_cost, answer_reserve=None, answer_agents=None, prices=None)` keep a run under the
  cap. They read `context.session.total_usage`: the usage of the run and of every run above it, so a
  delegate's calls count against the whole run's budget. A nested run's usage joins its parent's
  when it ends, and a sibling still running is not counted yet. `geomind run --max-tokens` and
  `--max-cost` set them.
  **No call past the cap.** With `prices` (a mapping from model id to `(input, output)` price per
  token, or a function that returns one) a cost budget estimates each call before it is made: the
  input bound (`input_bound`: the messages and tool schemas at one token per two characters, never
  under what a provider counts) times the input price, plus the call's `max_tokens` times the
  output price. If that passes the cap the hook lowers the call's `max_tokens` to what fits, through
  the session (`limit_output`, used once); if even the input does not fit, the call is denied. A run
  then ends at or below its cap. A token budget does the same with `bound_input=True`. Both are off
  when unset (a call is then refused only once the cap is reached), and a model without a price, or
  a rule step, is not estimated. geomind has no price table: `geomind run` reads the prices of
  OpenRouter's public model list (`GET /models`, the list `check-live` already uses) for a live run
  with a cost cap, and says on the output when it cannot, and a run from a recording fetches none.
  **`answer_reserve`.** An amount, in the unit of the cap, held back from every call except those
  of the agents named in `answer_agents` (`agent.name`, such as `explainer`) and the last step of a
  run, so the agent that writes the answer can still pay for it. No default: unset it is off, and a
  reserve without `answer_agents` raises `BudgetError`. It is an argument of the hook, not a
  `gd.runtime` setting, because it belongs to one cap and one unit.
- `TimeLimit(max_seconds, clock=time.monotonic)` denies an LLM call once `max_seconds` have passed
  since the first LLM call of the root run, in this process (a run resumed elsewhere starts the
  clock anew). The limit is required; there is no default.
- **After a limit stop.** When a root run whose answer is text ends on `TokenBudget`,
  `CostBudget`, `ProjectBudget` or `TimeLimit` (`denied`) or on the step limit, the engine gives it
  an answer built with no LLM call from the problem state and the log (`geomind/engine/partial.py`):
  what was asked, the designs, studies and results with their references, gemini's checks, the
  open questions and unconfirmed assumptions, why it stopped and what a rerun with a higher limit
  does next. It is `RunResult.answer` and the `answer` of `run.finished`, with `stop_reason` and
  `status` unchanged, and it is streamed as `text.delta` like any answer. A denial that is no limit
  (a user's refusal, `Cancellation`) and a nested run have no such answer, nor has an agent whose
  output is not text. `geomind export` shows it in a `## Stop` section.
- `ProjectBudget(ledger, project_id, max_tokens=None, max_cost=None, answer_reserve=None,
  answer_agents=None, prices=None, bound_input=False)` keeps the project under a cap: it fits calls
  as the two budgets above do, and denies the next LLM call once
  `ledger.spent(project_id)` plus this run's `total_usage` reaches a cap. `answer_reserve` needs
  exactly one cap. At least one cap is
  required (`BudgetError` otherwise) and there is no default. The reason reads `project token
  budget: <project> used N of CAP` (or `cost`). The ledger is a `UsageLedger` (see
  [engine](engine.md)): `spent(project_id)` returns the `Usage` of every finished run of the
  project, as the backend stores it; `MemoryUsageLedger` is for tests and `FileUsageLedger(root)`
  sums the root runs under a `FileRunStore` root whose `run.started.project` is the project and
  that have a `run.finished`, with their nested runs, once. A paused or running run is not
  finished, so a resumed run is not in the ledger and its earlier steps count once, through the
  session. The ledger is read once per root run, at its first LLM call, in a worker thread
  (`asyncio.to_thread`), because a ledger is sync and may be a database; this run's usage is added live.
  Runs of one project running at the same time are not counted against each other, because the
  ledger holds finished runs only. A project cap does not replace a run cap. Pass it in `gd.Run(hooks=[...])`;
  `geomind run --project P --project-max-cost USD --project-max-tokens N` sets it with
  `FileUsageLedger(".runs")`.
- `RequireApproval(tools)` is a shortcut for ask rules, in their place in the
  [permission order](permissions.md).
- `Cancellation(is_cancelled)` calls the function the caller gives before every LLM and tool call
  and before the answer, and ends the run with `cancelled`. The function may read anything, so this
  works across processes.
- `Verified()` refuses to finish while the design fails verification, so no design reaches the user
  without passing every check. The problem state names the design (`design.reference`, a
  `design/<name>`) and its result (`verification.result`, a `result/<id>` of `simulate`). Before
  the answer the hook runs gemini's checks again on that stored run, with the state's requirements
  and the state's case (`gd.verify.verify(plant, results, case)`), and refuses with each failed
  check and its domain. A `passed` the model wrote is never trusted; a result whose plant is not the
  design's is stale (`stale_result`), and one that ran on another case than the state's is off the
  case (`result_off_case`, read from the result's `<id>.case` and the digests of its files,
  `<id>.files`). A case that differs from `case_origin`, the case the user gave, fails with
  `case_changed` and the list of changes until the user approves it. A state with no
  design and no verification has nothing to verify, so an answer to a question finishes. A nested
  run answers its parent, not the user, so it hands any design back to its loop.

## Pausing

A `Request` becomes a pause: the engine logs `request` with the pending action before it tells the
callbacks, so an answer always finds it. It returns
`RunResult(status="waiting", request=...)`, and the process may exit. `Request.id` is filled in
from the sequence number, so it is deterministic. An approved call is not asked again, and an
approval applies to that call id only.

# Hooks

Three decision points that can deny or pause a run, in `swarmax/core/engine/hooks.py`. A hook
derives from `sx.hooks.Hook` and overrides any of `before_llm_call(agent, messages)`,
`before_tool_call(agent, call)` and `before_finish(agent, action)`, plain or `async`. Each returns
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

- `TokenBudget(max_tokens)` and `CostBudget(max_cost)` deny the next LLM call over the budget. They
  read the usage of the active run, nested runs included once they end.
- `RequireApproval(tools)` is a shortcut for ask rules, in their place in the
  [permission order](permissions.md).
- `Cancellation(is_cancelled)` calls the function the caller gives before every LLM and tool call
  and before the answer, and ends the run with `cancelled`. The function may read anything, so this
  works across processes.

## Pausing

A `Request` becomes a pause: the engine logs `request` with the pending action, saves a checkpoint,
then tells the callbacks, so an answer always finds the checkpoint. It returns
`RunResult(status="waiting", request=...)`, and the process may exit. `Request.id` is filled in
from the sequence number, so it is deterministic. An approved call is not asked again, and an
approval applies to that call id only.

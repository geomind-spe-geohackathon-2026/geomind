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

- `TokenBudget(max_tokens)` and `CostBudget(max_cost)` deny the next LLM call over the budget. They
  read `context.usage`, nested runs included once they end.
- `RequireApproval(tools)` is a shortcut for ask rules, in their place in the
  [permission order](permissions.md).
- `Cancellation(is_cancelled)` calls the function the caller gives before every LLM and tool call
  and before the answer, and ends the run with `cancelled`. The function may read anything, so this
  works across processes.
- `Verified()` refuses to finish while the design fails verification, so no design reaches the user
  without passing every check. The problem state names the design (`design.reference`, a
  `design/<name>`) and its result (`verification.result`, a `result/<id>` of `simulate`). Before
  the answer the hook runs gemini's checks again on that stored run, with the state's requirements
  (`gd.verify.verify`), and refuses with each failed check and its domain. A `passed` the model
  wrote is never trusted; a result whose plant is not the design's is stale. A state with no
  design and no verification has nothing to verify, so an answer to a question finishes. A nested
  run answers its parent, not the user, so it hands any design back to its loop.

## Pausing

A `Request` becomes a pause: the engine logs `request` with the pending action before it tells the
callbacks, so an answer always finds it. It returns
`RunResult(status="waiting", request=...)`, and the process may exit. `Request.id` is filled in
from the sequence number, so it is deterministic. An approved call is not asked again, and an
approval applies to that call id only.

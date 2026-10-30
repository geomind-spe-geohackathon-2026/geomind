# Permissions

Declarative rules and a mode, in `geomind/engine/permissions.py`.
`gd.Permissions(mode="ask", allow=(), ask=(), deny=())`; a rule is a tool name or
`"effect:<effect>"`, and an unknown mode or effect raises `UnknownNameError`.

## The order

Every tool call is decided in this fixed order:

1. `before_tool_call` hooks: a deny or a request ends the decision; an allow does not skip the
   rules.
2. Deny rules.
3. The limits of the mode: `plan` runs no tool and feeds back "plan mode: describe what you would
   do"; `readonly` denies all but `read` and `compute`.
4. Ask rules, always a `Request` of kind `approval`. `RequireApproval(tools)` adds to these.
5. Allow rules: an allow rule lets a `write`, `execute` or `external` tool run without asking in
   `ask` mode.
6. The rest of the mode: `auto` allows all; `ask` asks for `write`, `execute` and `external`.

Allow rules come before the mode because the mode decides every remaining call, so an allow rule
after it could never apply.

Steps 3 and 4 are swapped against the S1 prompt, where the mode came after ask rules. There, an
approval through an ask rule would run a `write` tool in `readonly`, which the modes promise never
to do. An ask rule on a `read` tool still asks in `readonly`.

## Decisions

Every decision is a `permission` event naming the rule that made it, such as `deny:effect:execute`,
`ask:save_note`, `allow:save_note`, `mode:ask`, `hook:TokenBudget` or `user`. A denial is a tool
result, not an exception. An approval answered by the user applies to that call id only. A call
the user approved is not asked again, by hooks or rules.

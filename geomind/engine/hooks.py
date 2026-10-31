"""Decision points that can deny or pause, and the shipped hooks."""

import asyncio

from geomind.engine.callbacks import call_maybe_async
from geomind.errors import ToolError
from geomind.tools.gemini.assessment import stored_run
from geomind.types import Allow, Cancel, Deny, Request
from geomind.verify import verify


class Hook:
    """Override any point, plain or ``async``.

    ``before_llm_call(context, agent, messages)``, ``before_tool_call(context, agent, call)`` and
    ``before_finish(context, agent, action)`` each return ``None`` for no objection,
    ``Deny(reason)`` or a ``Request``; ``before_tool_call`` may also return ``Allow(input=...)`` to
    change the input.
    NOTE: gemini's pre-hooks observe or adjust a call, while these can stop it, because a run has
    a user and a budget to answer to.
    """

    ask_rules = ()
    always_asked = False
    """Whether this hook is asked even at a point the user already approved."""

    def before_llm_call(self, context, agent, messages):
        """Object to an LLM call, or not."""

    def before_tool_call(self, context, agent, call):
        """Object to a tool call, or not."""

    def before_finish(self, context, agent, action):
        """Object to the final answer, or not."""


async def ask_hooks(hooks, point, context, agent, subject):
    """Return ``(decision, hook name)``: the first objection, else the last changed input."""
    changed = None
    for hook in hooks:
        decision = await call_maybe_async(getattr(hook, point), context, agent, subject)
        if isinstance(decision, (Deny, Request)):
            return decision, type(hook).__name__
        if isinstance(decision, Allow) and decision.input is not None:
            subject = subject.model_copy(update={"input": decision.input})
            changed = decision, type(hook).__name__
    return changed or (None, None)


class TokenBudget(Hook):
    """Stop a run before an LLM call once it has used ``max_tokens``."""

    def __init__(self, max_tokens):
        """Keep the limit."""
        self.max_tokens = max_tokens

    def before_llm_call(self, context, agent, messages):
        """Deny the call over the budget."""
        used = context.usage.input_tokens + context.usage.output_tokens
        if used >= self.max_tokens:
            return Deny(reason=f"token budget: used {used} of {self.max_tokens}")
        return None


class CostBudget(Hook):
    """Stop a run before an LLM call once it has cost ``max_cost``."""

    def __init__(self, max_cost):
        """Keep the limit."""
        self.max_cost = max_cost

    def before_llm_call(self, context, agent, messages):
        """Deny the call over the budget."""
        cost = context.usage.cost
        if cost >= self.max_cost:
            return Deny(reason=f"cost budget: used {cost} of {self.max_cost}")
        return None


class RequireApproval(Hook):
    """Ask before the named tools; a shortcut for ask rules, in their place in the order."""

    def __init__(self, tools):
        """Keep the tool names or ``effect:<effect>`` rules."""
        self.ask_rules = tuple(tools)


class Verified(Hook):
    """Refuse to finish while the last verification failed, so no failed design reaches the user.

    The problem state names the design (``design.reference``, a ``design/<name>``) and the result
    that verifies it (``verification.result``, a ``result/<id>`` of ``simulate``). Before the answer
    the hook runs gemini's checks again on that stored run, with the requirements of the state.
    NOTE: a ``passed`` the model wrote is never trusted, and a result whose plant is not the
    design's is stale. A state with no design has nothing to verify.
    """

    async def before_finish(self, context, agent, action):
        """Deny the answer unless the design's stored run passes every check now."""
        problem = context.problem
        design = (problem.design or {}).get("reference")
        result = (problem.verification or {}).get("result")
        if design is None and result is None:
            return None
        return await asyncio.to_thread(verdict, context, design, result)


def verdict(context, design, result):
    """Return ``None`` when the design's stored run passes every check, else the ``Deny``."""
    if design is None or result is None:
        return Deny(
            reason="verification: the design and its result are not both in the problem state; "
            "simulate the design, run check_results, and record design.reference and "
            "verification.result"
        )
    try:
        plant, results = stored_run(context, result, "Verified")
    except ToolError as error:
        return Deny(reason=f"verification: {error}")
    if plant.to_dict() != context.session.load_artifact(design):
        return Deny(
            reason=f"verification: {result} is stale; it ran another plant than {design}. "
            "Simulate the current design and check it again"
        )
    found = verify(plant, results, requirements=context.problem.requirements)
    if found["passed"]:
        return None
    failed = ", ".join(f"{item['name']} ({item['domain']})" for item in found["failures"])
    return Deny(reason=f"verification: {design} fails {failed}; change the design and verify again")


class Cancellation(Hook):
    """End the run with ``cancelled`` when ``is_cancelled()`` says so.

    It is checked before every LLM and tool call and before the answer. The function may read
    anything, such as Redis, so it works across processes. NOTE: it is ``always_asked``, because an
    approval given before a cancellation must not outrun it.
    """

    always_asked = True

    def __init__(self, is_cancelled):
        """Keep the function the caller gives."""
        self.is_cancelled = is_cancelled

    def _check(self):
        """Return the decision of this moment."""
        return Cancel(reason="cancelled") if self.is_cancelled() else None

    def before_llm_call(self, context, agent, messages):
        """Check before an LLM call."""
        return self._check()

    def before_tool_call(self, context, agent, call):
        """Check before a tool call."""
        return self._check()

    def before_finish(self, context, agent, action):
        """Check before the answer."""
        return self._check()

"""Decision points that can deny or pause, and the shipped hooks."""

from swarmax.core import runtime
from swarmax.core.engine.callbacks import call_maybe_async
from swarmax.core.types import Allow, Cancel, Deny, Request


class Hook:
    """Override any point, plain or ``async``.

    ``before_llm_call(agent, messages)``, ``before_tool_call(agent, call)`` and
    ``before_finish(agent, action)`` each return ``None`` for no objection, ``Deny(reason)`` or a
    ``Request``; ``before_tool_call`` may also return ``Allow(input=...)`` to change the input.
    NOTE: gemini's pre-hooks observe or adjust a call, while these can stop it, because a run has
    a user and a budget to answer to.
    """

    ask_rules = ()

    def before_llm_call(self, agent, messages):
        """Object to an LLM call, or not."""

    def before_tool_call(self, agent, call):
        """Object to a tool call, or not."""

    def before_finish(self, agent, action):
        """Object to the final answer, or not."""


async def ask_hooks(hooks, point, agent, subject):
    """Return ``(decision, hook name)``: the first objection, else the last changed input."""
    changed = None
    for hook in hooks:
        decision = await call_maybe_async(getattr(hook, point), agent, subject)
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

    def before_llm_call(self, agent, messages):
        """Deny the call over the budget."""
        usage = runtime.active_run().state.usage
        used = usage.input_tokens + usage.output_tokens
        if used >= self.max_tokens:
            return Deny(reason=f"token budget: used {used} of {self.max_tokens}")
        return None


class CostBudget(Hook):
    """Stop a run before an LLM call once it has cost ``max_cost``."""

    def __init__(self, max_cost):
        """Keep the limit."""
        self.max_cost = max_cost

    def before_llm_call(self, agent, messages):
        """Deny the call over the budget."""
        cost = runtime.active_run().state.usage.cost
        if cost >= self.max_cost:
            return Deny(reason=f"cost budget: used {cost} of {self.max_cost}")
        return None


class RequireApproval(Hook):
    """Ask before the named tools; a shortcut for ask rules, in their place in the order."""

    def __init__(self, tools):
        """Keep the tool names or ``effect:<effect>`` rules."""
        self.ask_rules = tuple(tools)


class Cancellation(Hook):
    """End the run with ``cancelled`` when ``is_cancelled()`` says so.

    It is checked before every LLM and tool call and before the answer. The function may read
    anything, such as Redis, so it works across processes.
    """

    def __init__(self, is_cancelled):
        """Keep the function the caller gives."""
        self.is_cancelled = is_cancelled

    def _check(self):
        """Return the decision of this moment."""
        return Cancel(reason="cancelled") if self.is_cancelled() else None

    def before_llm_call(self, agent, messages):
        """Check before an LLM call."""
        return self._check()

    def before_tool_call(self, agent, call):
        """Check before a tool call."""
        return self._check()

    def before_finish(self, agent, action):
        """Check before the answer."""
        return self._check()

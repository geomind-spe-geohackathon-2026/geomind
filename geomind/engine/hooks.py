"""Decision points that can deny or pause, and the shipped hooks."""

import asyncio

from geomind.engine.callbacks import call_maybe_async
from geomind.errors import BudgetError
from geomind.types import Allow, Cancel, Deny, Request
from geomind.verify.design import verify_design


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
    """Stop a run before an LLM call once it has used ``max_tokens``, nested runs included."""

    def __init__(self, max_tokens):
        """Keep the limit."""
        self.max_tokens = max_tokens

    def before_llm_call(self, context, agent, messages):
        """Deny the call over the budget."""
        usage = context.session.total_usage
        used = usage.input_tokens + usage.output_tokens
        if used >= self.max_tokens:
            return Deny(reason=f"token budget: used {used} of {self.max_tokens}")
        return None


class CostBudget(Hook):
    """Stop a run before an LLM call once it has cost ``max_cost``, nested runs included."""

    def __init__(self, max_cost):
        """Keep the limit."""
        self.max_cost = max_cost

    def before_llm_call(self, context, agent, messages):
        """Deny the call over the budget."""
        cost = context.session.total_usage.cost
        if cost >= self.max_cost:
            return Deny(reason=f"cost budget: used {cost} of {self.max_cost}")
        return None


class ProjectBudget(Hook):
    """Stop a run before an LLM call once its project has used a cap, this run included.

    The project has spent ``ledger.spent(project_id)`` in finished runs, which the backend
    stores; this run adds ``context.session.total_usage``, nested runs included. A run being
    resumed is not finished, so the ledger does not hold it and its steps count once. At least
    one cap is required: there is no default.
    """

    def __init__(self, ledger, project_id, max_tokens=None, max_cost=None):
        """Keep the ledger, the project and the caps; raise ``BudgetError`` with neither cap."""
        if max_tokens is None and max_cost is None:
            raise BudgetError("project budget: expected max_tokens or max_cost; got neither")
        self.ledger = ledger
        self.project_id = project_id
        self.max_tokens = max_tokens
        self.max_cost = max_cost

    def before_llm_call(self, context, agent, messages):
        """Deny the call once the project reaches a cap."""
        usage = self.ledger.spent(self.project_id) + context.session.total_usage
        used = usage.input_tokens + usage.output_tokens
        if self.max_tokens is not None and used >= self.max_tokens:
            return self._deny("token", used, self.max_tokens)
        if self.max_cost is not None and usage.cost >= self.max_cost:
            return self._deny("cost", usage.cost, self.max_cost)
        return None

    def _deny(self, kind, used, cap):
        """Return the denial that names the project, the cap and what was spent."""
        return Deny(reason=f"project {kind} budget: {self.project_id} used {used} of {cap}")


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
    design's is stale. A state with no design has nothing to verify, and a nested run answers its
    parent, not the user, so it hands any design back.
    """

    async def before_finish(self, context, agent, action):
        """Deny the answer unless the design's stored run passes every check now."""
        if context.session.state.parent is not None:
            return None
        problem = context.problem
        design = (problem.design or {}).get("reference")
        result = (problem.verification or {}).get("result")
        if design is None and result is None:
            return None
        return await asyncio.to_thread(verdict, context)


def verdict(context):
    """Return ``None`` when the design's stored run passes every check, else the ``Deny``."""
    found = verify_design(context)
    if found["passed"]:
        return None
    if "reason" in found:
        return Deny(reason=f"verification: {found['reason']}")
    design = context.problem.design.get("reference")
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

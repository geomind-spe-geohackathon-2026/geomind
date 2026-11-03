"""Decision points that can deny or pause, and the shipped hooks."""

import asyncio
import json
import math
from time import monotonic

from geomind.engine.callbacks import call_maybe_async
from geomind.errors import BudgetError
from geomind.types import RULE_MODEL, Allow, Cancel, Deny, Request, Usage
from geomind.verify.design import verify_design

CHARACTERS_PER_TOKEN_BOUND = 2
"""Characters per token that never overstate what a provider counts, for the input bound."""


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


def input_bound(agent, messages):
    """Return an upper bound of the input tokens of a call: its messages and tool schemas.

    NOTE: text is about four characters per token, code and JSON about two or three, so one token
    per ``CHARACTERS_PER_TOKEN_BOUND`` characters never falls under what a provider counts.
    """
    text = "".join(message.model_dump_json() for message in messages)
    text += json.dumps(agent.tool_schemas())
    return -(-len(text) // CHARACTERS_PER_TOKEN_BOUND)


def token_room(cap, used, held, tokens_in):
    """Return the output tokens that fit under a token cap after the input of one call."""
    return cap - used - held - tokens_in


def cost_room(cap, spent, held, tokens_in, price):
    """Return the output tokens that fit under a cost cap after the input of one call.

    ``price`` is ``(input price, output price)`` per token, or ``None`` when the model has none:
    then only a cap already reached is refused.
    """
    left = cap - spent - held
    if price is None:
        return math.inf if left > 0 else 0
    left -= tokens_in * price[0]
    if left <= 0:
        return 0
    return math.inf if price[1] <= 0 else math.floor(left / price[1])


def tokens_worst(tokens_in):
    """Return the worst usage of a call at a number of output tokens, in tokens."""
    return lambda output: Usage(input_tokens=tokens_in, output_tokens=output)


def cost_worst(tokens_in, price):
    """Return the worst usage of a call at a number of output tokens, in cost; none unpriced."""
    if price is None:
        return None
    return lambda output: Usage(cost=tokens_in * price[0] + output * price[1])


def both_worst(tokens_in, price):
    """Return the worst usage of a call in tokens and, when priced, in cost."""
    cost = cost_worst(tokens_in, price)
    return lambda output: tokens_worst(tokens_in)(output) + (cost(output) if cost else Usage())


def price_of(prices, model):
    """Return ``(input, output)`` per token of a model from a mapping or function, else ``None``."""
    if prices is None:
        return None
    return prices(model) if callable(prices) else prices.get(model)


class Capped(Hook):
    """The shared part of the budgets: the reserve for the answer and the fit of one call.

    ``answer_reserve`` is an amount, in the unit of the cap, held back from every call except
    those of the agents named in ``answer_agents`` and the last step of a run, so the agent that
    writes the answer can still pay for it. Unset it is off, and then ``answer_agents`` is not
    used. ``prices`` is a mapping from model id to ``(input, output)`` price per token, or a
    function that returns one; without a price a cost cap only refuses a call once it is reached.
    A cap bounds the input of a call only with ``prices`` (cost) or ``bound_input=True`` (tokens);
    unset, a call is refused once the cap is reached, as before.
    """

    def __init__(self, answer_reserve=None, answer_agents=None, prices=None, bound_input=False):
        """Keep the reserve and the prices; a reserve needs the agents that may spend it."""
        if answer_reserve is not None and not answer_agents:
            raise BudgetError("budget: answer_reserve needs answer_agents; expected names")
        self.answer_reserve = answer_reserve
        self.answer_agents = tuple(answer_agents or ())
        self.prices = prices
        self.bounds_input = bound_input or prices is not None

    def _held(self, context, agent):
        """Return the reserve held back from this call: none for the answer's own agents."""
        if self.answer_reserve is None:
            return 0
        if agent.name in self.answer_agents or context.steps_left == 1:
            return 0
        return self.answer_reserve

    def _fit(self, context, agent, room, reason, worst=None):
        """Deny a call that has no room, else lower its ``max_tokens`` and hold its worst case.

        ``worst`` gives the usage of the call at a number of output tokens. A bounded call holds
        it until it returns (``RunSession.reserve``), so calls side by side cannot pass the cap.
        """
        session = context.session
        if room < 1:
            session.note_limit(reason)
            return Deny(reason=reason)
        ceiling = agent.model.max_tokens
        is_call = self.bounds_input and agent.model.resolved_name() != RULE_MODEL
        if is_call and room != math.inf and (ceiling is None or room < ceiling):
            session.limit_output(int(room))
        output = min(item for item in (room, ceiling or math.inf))
        if is_call and worst is not None and output != math.inf:
            session.reserve(worst(int(output)))
        return None

    def _tokens_in(self, agent, messages):
        """Return the input bound of a call; zero for a rule step and where bounding is off."""
        if not self.bounds_input or agent.model.resolved_name() == RULE_MODEL:
            return 0
        return input_bound(agent, messages)


class TokenBudget(Capped):
    """Keep a run under ``max_tokens``, nested runs included, with no call past the cap.

    With ``bound_input=True``, before each LLM call it bounds the call: the input
    (``input_bound``) plus the output the call may use. A call whose input does not fit is denied;
    otherwise the call's ``max_tokens`` is lowered to what fits. Without it, a call is refused once
    the cap is reached.
    """

    def __init__(self, max_tokens, answer_reserve=None, answer_agents=None, bound_input=False):
        """Keep the limit, the optional reserve and whether to bound the input."""
        super().__init__(answer_reserve, answer_agents, bound_input=bound_input)
        self.max_tokens = max_tokens

    def before_llm_call(self, context, agent, messages):
        """Deny the call that does not fit, or lower its output limit."""
        usage = context.session.total_usage
        used = usage.input_tokens + usage.output_tokens
        tokens_in = self._tokens_in(agent, messages)
        held = self._held(context, agent)
        room = token_room(self.max_tokens, used, held, tokens_in)
        reason = f"token budget: used {used} of {self.max_tokens}"
        if used < self.max_tokens:
            reason += f"; the next call needs about {tokens_in} input tokens and {held} are kept"
        return self._fit(context, agent, room, reason, worst=tokens_worst(tokens_in))


class CostBudget(Capped):
    """Keep a run under ``max_cost``, nested runs included, with no call past the cap.

    Before each LLM call it estimates the call: the input bound times the input price plus the
    ``max_tokens`` it may use times the output price, from ``prices``. A call whose input does not
    fit is denied; otherwise ``max_tokens`` is lowered to what fits, so the run ends at or below
    the cap. A model without a price is only refused once the cap is reached.
    """

    def __init__(self, max_cost, answer_reserve=None, answer_agents=None, prices=None):
        """Keep the limit, the optional reserve and the prices."""
        super().__init__(answer_reserve, answer_agents, prices)
        self.max_cost = max_cost

    def before_llm_call(self, context, agent, messages):
        """Deny the call that does not fit, or lower its output limit."""
        cost = context.session.total_usage.cost
        tokens_in = self._tokens_in(agent, messages)
        price = price_of(self.prices, agent.model.resolved_name())
        held = self._held(context, agent)
        room = cost_room(self.max_cost, cost, held, tokens_in, price)
        reason = f"cost budget: used {cost} of {self.max_cost}"
        if cost < self.max_cost:
            reason += f"; the next call needs about {tokens_in} input tokens and {held} is kept"
        return self._fit(context, agent, room, reason, worst=cost_worst(tokens_in, price))


class TimeLimit(Hook):
    """Stop a run before an LLM call once ``max_seconds`` have passed since its first call.

    The clock starts at the first LLM call of a root run, in this process; a run resumed in
    another process starts it anew. There is no default: the limit is required.
    """

    def __init__(self, max_seconds, clock=monotonic):
        """Keep the limit and the clock, which tests replace."""
        self.max_seconds = max_seconds
        self.clock = clock
        self._started = {}

    def before_llm_call(self, context, agent, messages):
        """Deny the call once the time is up."""
        root = context.session.state.root
        elapsed = self.clock() - self._started.setdefault(root, self.clock())
        if elapsed < self.max_seconds:
            return None
        reason = f"time limit: {elapsed:.0f} s of {self.max_seconds} s"
        context.session.note_limit(reason)
        return Deny(reason=reason)


class ProjectBudget(Capped):
    """Keep a project under a cap, this run included, with no call past it.

    The project has spent ``ledger.spent(project_id)`` in finished runs, which the backend
    stores; this run adds ``context.session.total_usage``, nested runs included. A run being
    resumed is not finished, so the ledger does not hold it and its steps count once. At least
    one cap is required: there is no default. The ledger is read once per root run, at its first
    call, in a worker thread, so runs of the project running at the same time are not counted
    against each other. A call is fitted as for ``TokenBudget`` and ``CostBudget``;
    ``answer_reserve`` needs exactly one cap, as it has one unit.
    """

    def __init__(
        self,
        ledger,
        project_id,
        max_tokens=None,
        max_cost=None,
        answer_reserve=None,
        answer_agents=None,
        prices=None,
        bound_input=False,
    ):
        """Keep the ledger, the project and the caps; raise ``BudgetError`` with neither cap."""
        if max_tokens is None and max_cost is None:
            raise BudgetError("project budget: expected max_tokens or max_cost; got neither")
        if answer_reserve is not None and max_tokens is not None and max_cost is not None:
            raise BudgetError("project budget: answer_reserve has one unit; expected one cap")
        super().__init__(answer_reserve, answer_agents, prices, bound_input)
        self.ledger = ledger
        self.project_id = project_id
        self.max_tokens = max_tokens
        self.max_cost = max_cost
        self._earlier = {}

    async def _spent_before(self, context):
        """Return what the project spent before this root run, read from the ledger once."""
        root = context.session.state.root
        if root not in self._earlier:
            self._earlier[root] = await asyncio.to_thread(self.ledger.spent, self.project_id)
        return self._earlier[root]

    async def before_llm_call(self, context, agent, messages):
        """Deny the call that does not fit under a cap, or lower its output limit."""
        usage = await self._spent_before(context) + context.session.total_usage
        used = usage.input_tokens + usage.output_tokens
        tokens_in = self._tokens_in(agent, messages)
        held = self._held(context, agent)
        rooms = []
        price = price_of(self.prices, agent.model.resolved_name())
        if self.max_tokens is not None:
            room = token_room(self.max_tokens, used, held, tokens_in)
            rooms.append((room, self._reason("token", used, self.max_tokens)))
        if self.max_cost is not None:
            room = cost_room(self.max_cost, usage.cost, held, tokens_in, price)
            rooms.append((room, self._reason("cost", usage.cost, self.max_cost)))
        room, reason = min(rooms, key=lambda item: item[0])
        worst = both_worst(tokens_in, price)
        return self._fit(context, agent, room, reason, worst=worst)

    def _reason(self, kind, used, cap):
        """Return the denial text that names the project, the cap and what was spent."""
        return f"project {kind} budget: {self.project_id} used {used} of {cap}"


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

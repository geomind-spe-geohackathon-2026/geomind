"""A tool that runs another agent in a nested run."""

import asyncio
import json

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import Tool
from geomind.types import Record
from geomind.utils.strings import first_paragraph

CHARACTERS_PER_TOKEN = 4
STOP_CODES = ("context_exceeded",)
"""Codes a nested run's message may start with, which its delegate passes on."""


def bound(session, limit, where):
    """Return the semaphore of one run that the setting ``limit`` sizes; unset, refuse.

    NOTE: it lives on the session, so the delegates of one step share it, and a new run starts
    with a new one.
    """
    size = runtime.get(limit)
    if size is None:
        variable = f"GEOMIND_{limit.upper()}"
        raise ToolError(
            f"{where}: {limit} = None; expected {variable}, how many such runs go side by side",
            code="not_allowed",
        )
    limits = session.limits
    if limit not in limits:
        limits[limit] = asyncio.Semaphore(size)
    return limits[limit]


class DelegateInput(Record):
    """What the model passes: the task text."""

    task: str


class Delegate(Tool):
    """Run ``agent`` in a nested engine run with a clean context: the task text only.

    The nested run has its own run id and ``parent`` set on every event. The model
    reads only the answer, cut to ``max_summary_tokens``. NOTE: the effect is ``compute`` so that
    delegating needs no approval of its own, because the nested tools are decided one by one. It is
    still not pure: a nested run does not run again in a replay as a pure tool does, and after a
    crash it is not repeated. ``runs_beside`` lets the calls of one step run together, for agents
    that never wait for a user: ``is_pure`` stays false, so a replay still runs them again.
    ``limit`` names the runtime setting that bounds how many delegates of that limit run at once
    in one run, such as ``design_concurrency``; it is required when given, with no default.
    """

    def __init__(self, agent, max_summary_tokens=None, runs_beside=False, limit=None):
        """Offer ``agent`` as a tool named after it."""
        super().__init__(
            agent.name,
            first_paragraph(type(agent).__doc__ or agent.name),
            DelegateInput.model_json_schema(),
            self._delegate,
            effect="compute",
            idempotent=False,
            input_model=DelegateInput,
        )
        self.agent = agent
        self.max_summary_tokens = max_summary_tokens
        self.runs_beside = runs_beside
        self.limit = limit

    @property
    def is_pure(self):
        """Return that a nested run is never pure."""
        return False

    async def _delegate(self, context, task):
        """Run the nested agent through the run of ``context``, within its limit if it has one."""
        if self.limit is None:
            result = await context.session.delegate(self.agent, task)
        else:
            async with bound(context.session, self.limit, self.name):
                result = await context.session.delegate(self.agent, task)
        return self.outcome(result, context.session.child_limit)

    def outcome(self, result, limit=None):
        """Return the output of a finished nested run, or its request when it waits.

        ``limit`` is the reason a budget or time limit stopped the nested run: the error then has
        the code ``budget`` and names the limit with what was spent and the cap. A typed answer
        comes back as JSON text. Another stop is
        ``nested_stopped`` with its message, and a crash ``internal``, its text left in the log.
        """
        if result.request is not None:
            return result.request
        if result.status != "done" and limit is not None:
            raise ToolError(f"{self.name}: run {limit}", code="budget")
        if result.status != "done" and result.message:
            code, _, rest = result.message.partition(": ")
            known = code in STOP_CODES
            raise ToolError(
                f"{self.name}: the nested run stopped with {result.stop_reason}: "
                f"{rest if known else result.message}",
                code=code if known else "nested_stopped",
            )
        if result.status != "done":
            raise ToolError(
                f"{self.name}: the nested run stopped with {result.stop_reason}; the detail is in "
                "the log",
                code="internal",
            )
        tokens = self.max_summary_tokens or runtime.get("delegate_summary_tokens")
        answer = result.answer if isinstance(result.answer, str) else json.dumps(result.answer)
        return answer[: tokens * CHARACTERS_PER_TOKEN]

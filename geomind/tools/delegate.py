"""A tool that runs another agent in a nested run."""

import asyncio
import json
import re

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import Tool
from geomind.types import Record
from geomind.utils.strings import first_paragraph

CHARACTERS_PER_TOKEN = 4
STOP_CODES = ("context_exceeded",)
"""Codes a nested run's message may start with, which its delegate passes on."""


NESTED_RETRIES = 1
"""How often a nested run that a provider failure stopped is run again (QA-011)."""
PROVIDER_FAILURE = re.compile(r"status = 5\d\d|timed out|idle timeout|overloaded", re.IGNORECASE)
"""A nested run's stop message of a passing provider failure (a 504, a timeout)."""
RETRY_NOTE = (
    "Your previous run of this task stopped on a provider failure (an LLM call timed out). What "
    "it wrote is kept in the problem state (the case, stored designs, assumptions): read it first "
    "and go on from it; redo only what is not there."
)
"""What a nested run reads when its delegate runs it again after a provider failure."""


def provider_failed(result):
    """Tell whether a nested run ended on a passing provider failure, not a request or a limit."""
    if result.request is not None or result.status == "done":
        return False
    return result.stop_reason == "error" and bool(PROVIDER_FAILURE.search(result.message or ""))


def required_setting(name, where):
    """Return a setting a delegate needs, or refuse naming its environment variable."""
    value = runtime.get(name)
    if value is None:
        raise ToolError(
            f"{where}: {name} = None; expected GEOMIND_{name.upper()}", code="not_allowed"
        )
    return value


def bound(session, limit, where):
    """Return the semaphore of one run that the setting ``limit`` sizes; unset, refuse.

    NOTE: it lives on the session, so the delegates of one step share it, and a new run starts
    with a new one.
    """
    size = required_setting(limit, where)
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
    ``steps`` names the runtime setting of the nested run's own step limit, such as
    ``engineer_max_steps``: at it the nested run ends with what it has instead of asking to go
    on; required when given, with no default. ``once`` runs the agent at most once per run: a
    second call answers ``already_asked``, as its findings are still in the conversation.
    """

    def __init__(
        self, agent, max_summary_tokens=None, runs_beside=False, limit=None, steps=None, once=False
    ):
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
        self.steps = steps
        self.once = once

    @property
    def is_pure(self):
        """Return that a nested run is never pure."""
        return False

    async def _delegate(self, context, task, beside=False):
        """Run the nested agent through the run of ``context``, within its limit if it has one.

        ``beside`` runs it as a member of a ``Team``, which never pauses for an approval; a
        ``runs_beside`` delegate always runs so, as its calls of one step run together and one
        pause among them never reached the chat (QA-016, run 0cb4b436).
        """
        if self.once:
            asked = context.session.__dict__.setdefault("asked_once", set())
            if self.name in asked:
                raise ToolError(
                    f"{self.name}: already asked in this run; its findings are above in the "
                    "conversation, kept whole for the run: work from them, and ask the user for "
                    "what they lack",
                    code="already_asked",
                )
            asked.add(self.name)
        max_steps = required_setting(self.steps, self.name) if self.steps else None
        beside = beside or self.runs_beside
        for attempt in range(NESTED_RETRIES + 1):
            if self.limit is None:
                result = await context.session.delegate(self.agent, task, max_steps, beside)
            else:
                async with bound(context.session, self.limit, self.name):
                    result = await context.session.delegate(self.agent, task, max_steps, beside)
            if attempt == NESTED_RETRIES or not provider_failed(result):
                break
            task = f"{task}\n\n{RETRY_NOTE}"
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


class TeamInput(Record):
    """What the model passes: one brief per member, by the member's tool name."""

    briefs: dict[str, str]


class Team(Tool):
    """Run several members' agents side by side in one call, one brief each, within their limit.

    NOTE: the parallel phase is code, not the model's choice of one step: each member is a
    ``Delegate`` (with its ``limit``), every brief runs as its own nested run at the same time, and
    a member that fails gives its error beside the others' answers instead of stopping them.
    A member cannot pause while its team mates run, so its approvals are allowed (QA-016: its
    request came back as output, never reached the chat and its work was lost).
    """

    def __init__(self, name, description, members):
        """Offer ``members``, delegates by tool name, as one tool named ``name``."""
        super().__init__(
            name,
            description,
            TeamInput.model_json_schema(),
            self._run,
            effect="compute",
            idempotent=False,
            input_model=TeamInput,
        )
        self.members = members

    @property
    def is_pure(self):
        """Return that nested runs are never pure."""
        return False

    async def _run(self, context, briefs):
        """Run each member on its brief at the same time; return each answer or error by name."""
        unknown = sorted(set(briefs) - set(self.members))
        if unknown or not briefs:
            raise ToolError(
                f"{self.name}: briefs = {sorted(briefs)}; expected one brief for each of "
                f"{', '.join(self.members)} that has work",
                path="briefs",
            )
        answers = await asyncio.gather(
            *(self._member(context, name, task) for name, task in briefs.items())
        )
        return dict(zip(briefs, answers))

    async def _member(self, context, name, task):
        """Return one member's answer, or its error as ``{error: {code, message}}``."""
        try:
            return await self.members[name]._delegate(context, task, beside=True)
        except ToolError as error:
            return {"error": {"code": error.code, "message": str(error)}}

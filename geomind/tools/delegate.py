"""A tool that runs another agent in a nested run."""

import asyncio
import copy
import json
import re
from uuid import uuid4

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import Tool
from geomind.types import Record
from geomind.utils.strings import first_paragraph

CHARACTERS_PER_TOKEN = 4
ESCAPING = 1.25
"""How much longer a JSON-text answer gets once it is a string in the team's JSON result."""
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


FINDING_TASK = 200
FINDING_SUMMARY = 400
"""The characters of the brief and of the answer a finding's line shows."""


def _start(text, limit):
    """Return the start of a text on one line, cut at ``limit`` characters."""
    line = " ".join(str(text).split())
    return line if len(line) <= limit else f"{line[:limit].rstrip()} ..."


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
        self.reruns_after_crash = True
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

    def for_call(self, session, tool_input):
        """Return a ``write`` copy of a ``runs_beside`` delegate whose agent writes (QA-329).

        A nested run beside never waits, so its writes are allowed without a card; with the
        chat's Auto-approve off, the call itself then asks once, before the run starts.
        """
        if not self.runs_beside or not agent_writes(self.agent):
            return self
        found = copy.copy(self)
        found.effect = "write"
        return found

    def card_summary(self, tool_input):
        """Return the card of a delegate that runs beside: who runs and that its writes ask none."""
        task = str((tool_input or {}).get("task") or "").strip().splitlines()
        what = f" for: {task[0][:CARD_TASK_CHARACTERS]}" if task and task[0] else ""
        return (
            f"Run {self.name}{what}; its writes (designs, ranges, studies) run without a card "
            "of their own."
        )

    async def _delegate(self, context, task, beside=False, instance=None):
        """Run the nested agent through the run of ``context``, within its limit if it has one.

        ``beside`` runs it as a member of a ``Team``, which never pauses for an approval; a
        ``runs_beside`` delegate always runs so, as its calls of one step run together and one
        pause among them never reached the chat (QA-016, run 0cb4b436). ``instance`` names the
        nested run when a team runs several instances at once (``Geoscientist II``); ``once``
        then holds per instance.
        """
        if self.once:
            asked = context.session.__dict__.setdefault("asked_once", set())
            key = instance or self.name
            if key in asked:
                raise ToolError(
                    f"{self.name}: already asked in this run; its findings are above in the "
                    "conversation, kept whole for the run: work from them, and ask the user for "
                    "what they lack",
                    code="already_asked",
                )
            asked.add(key)
        max_steps = required_setting(self.steps, self.name) if self.steps else None
        beside = beside or self.runs_beside
        seen = len(tree_events(context.session))
        for attempt in range(NESTED_RETRIES + 1):
            if self.limit is None:
                result = await context.session.delegate(
                    self.agent, task, max_steps, beside, instance
                )
            else:
                async with bound(context.session, self.limit, self.name):
                    result = await context.session.delegate(
                        self.agent, task, max_steps, beside, instance
                    )
            if attempt == NESTED_RETRIES or not provider_failed(result):
                break
            task = f"{task}\n\n{RETRY_NOTE}"
        outcome = self.outcome(result, context.session.child_limit)
        if result.request is None:
            await self.record_finding(context.session, task, result)
            outcome = with_denials(outcome, tree_events(context.session)[seen:])
        return outcome

    async def record_finding(self, session, task, result):
        """Keep a nested agent's whole answer as a finding of the problem state (QA-047).

        The answer is saved as the chat artifact ``finding-<id>``, and the state gets one line, so
        a run that stops before the work is written (a cancel, a pending approval) leaves it for
        the next run, which reads it instead of asking again. A failure to save it never fails the
        call: the answer still goes back. The id is random, as team members answer at once.
        """
        answer = result.answer if isinstance(result.answer, str) else json.dumps(result.answer)
        if not answer or not answer.strip():
            return
        try:
            key = uuid4().hex[:8]
            reference = f"finding-{key}"
            await session.save_artifact(
                reference, {"agent": self.name, "task": task, "answer": answer}
            )
            finding = {
                "id": f"F{key}",
                "agent": self.name,
                "task": _start(task, FINDING_TASK),
                "summary": _start(answer, FINDING_SUMMARY),
                "reference": reference,
            }
            await session.change_state([{"op": "add", "path": "/findings/-", "value": finding}])
        except Exception as error:
            await session.report_error(error, f"{self.name}: finding")

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


def tree_events(session):
    """Return the events of the request's run tree, or ``[]`` when the session keeps none."""
    try:
        return list(session.engine.store.load_events(session.state.root))
    except AttributeError:
        return []


DENIED_INPUT_CHARS = 300
"""How much of a denied call's input the parent reads beside the user's words."""


def with_denials(answer, events):
    """Return a nested answer with each user denial of its run, so the parent sees it (QA-288).

    The design lead obeyed "Do not change or search the plant"; the project lead read only its
    summary, saw a pick where it had asked a search, and briefed the search again. Each denial is
    one line: the tool, what the call sent and the user's words.
    """
    inputs = {}
    lines = []
    for event in events:
        call = getattr(event, "call", None)
        if event.type == "request" and call is not None:
            inputs[call.id] = call.input
        if event.type == "permission" and event.decision == "deny" and event.rule == "user":
            sent = json.dumps(inputs.get(getattr(event, "call_id", None)), default=str)
            words = f": {event.reason!r}" if event.reason else ""
            lines.append(
                f"- The user denied {event.tool} ({sent[:DENIED_INPUT_CHARS]}){words}. This is "
                "the user's instruction for this request: never brief the denied work again."
            )
    if not lines or not isinstance(answer, str):
        return answer
    return answer + "\n\nDenied by the user in this work:\n" + "\n".join(dict.fromkeys(lines))


class Brief(Record):
    """One task for one instance of a member: the member's tool name and the task text."""

    role: str
    task: str


class TeamInput(Record):
    """What the model passes: one brief per member by tool name, or a list of instance briefs."""

    briefs: dict[str, str] | list[Brief]


ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
"""The numerals of a member's instances, in brief order."""


def team_size(name):
    """Return the most briefs one team call runs, ``GEOMIND_TEAM_SIZE`` (QA-201); no default."""
    size = runtime.get("team_size")
    if size is None:
        raise ToolError(
            f"{name}: team_size = None; expected GEOMIND_TEAM_SIZE, the most sub-agents a lead "
            "runs at once"
        )
    if not 1 <= size <= len(ROMAN):
        raise ToolError(f"{name}: team_size = {size}; expected 1 to {len(ROMAN)}")
    return size


def role_title(name):
    """Return the display name of a member's tool name: ``reservoir_engineer`` -> ``Reservoir engineer``."""
    return name.replace("_", " ").capitalize()


def instance_names(briefs):
    """Return the display name of each brief of a list: ``<Role> <Roman numeral>`` (IMP-025).

    The numbers count per role in brief order, so three geoscientist briefs are Geoscientist I,
    II and III, and a member with one brief is ``<Role> I``.
    """
    seen = {}
    names = []
    for brief in briefs:
        seen[brief.role] = seen.get(brief.role, 0) + 1
        names.append(f"{role_title(brief.role)} {ROMAN[seen[brief.role] - 1]}")
    return names


class Team(Tool):
    """Run several members' agents side by side in one call, one brief each, within their limit.

    NOTE: the parallel phase is code, not the model's choice of one step: each member is a
    ``Delegate`` (with its ``limit``), every brief runs as its own nested run at the same time, and
    a member that fails gives its error beside the others' answers instead of stopping them.
    A member cannot pause while its team mates run, so its approvals are allowed (QA-016: its
    request came back as output, never reached the chat and its work was lost).

    ``briefs`` is either ``{member: task}``, one run per member, or a list of ``{role, task}``,
    one run per entry, so several instances of one member run at once (IMP-025): each is named
    ``<Role> <Roman numeral>`` (``Geoscientist II``), its events carry that ``instance``, and the
    answers come back by that name. Each instance should own distinct work (the lead's brief
    says which fields), so their results never clash; the lead merges them.
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
        self.reruns_after_crash = True
        self.members = members

    @property
    def is_pure(self):
        """Return that nested runs are never pure."""
        return False

    def for_call(self, session, tool_input):
        """Return a ``write`` copy of a team whose members write, so a card asks once (QA-329)."""
        if not any(agent_writes(member.agent) for member in self.members.values()):
            return self
        found = copy.copy(self)
        found.effect = "write"
        return found

    def card_summary(self, tool_input):
        """Return the card of a team call: how many runs side by side and that they ask none."""
        briefs = (tool_input or {}).get("briefs") or {}
        count = len(briefs)
        return (
            f"Run {count} member(s) of {self.name} side by side; their writes (designs, ranges, "
            "studies) run without a card of their own."
        )

    @property
    def result_limit(self):
        """Return the most characters of a team result the lead reads whole, not outlined.

        QA-156: each answer is already cut to its member's ``max_summary_tokens``, but the team's
        result went through the generic outline and the lead read the findings back one by one.
        The limit is the team size times the largest member budget, with room for the escaping
        of answers that are JSON text; without a team size, the generic limit holds.
        """
        size = runtime.get("team_size")
        if not size:
            return None
        budgets = [
            (member.max_summary_tokens or runtime.get("delegate_summary_tokens"))
            * CHARACTERS_PER_TOKEN
            for member in self.members.values()
        ]
        return int(size * max(budgets, default=0) * ESCAPING)

    async def _run(self, context, briefs):
        """Run each brief at the same time; return each answer or error by member or instance."""
        if isinstance(briefs, list):
            return await self._instances(context, briefs)
        unknown = sorted(set(briefs) - set(self.members))
        if unknown or not briefs:
            raise ToolError(
                f"{self.name}: briefs = {sorted(briefs)}; expected one brief for each of "
                f"{', '.join(self.members)} that has work",
                path="briefs",
            )
        size = team_size(self.name)
        if len(briefs) > size:
            raise ToolError(
                f"{self.name}: {len(briefs)} briefs; expected at most {size}: merge "
                "the smallest tasks",
                path="briefs",
            )
        answers = await asyncio.gather(
            *(self._member(context, name, task) for name, task in briefs.items())
        )
        return dict(zip(briefs, answers))

    async def _instances(self, context, briefs):
        """Run one instance per brief of a list at the same time; answers by instance name."""
        briefs = [
            item if isinstance(item, Brief) else Brief.model_validate(item) for item in briefs
        ]
        unknown = sorted({item.role for item in briefs} - set(self.members))
        if unknown or not briefs:
            raise ToolError(
                f"{self.name}: roles = {unknown or []}; expected a list of {{role, task}} with "
                f"role one of {', '.join(self.members)}",
                path="briefs",
            )
        size = team_size(self.name)
        if len(briefs) > size:
            raise ToolError(
                f"{self.name}: {len(briefs)} briefs; expected at most {size}: merge "
                "the smallest tasks",
                path="briefs",
            )
        names = instance_names(briefs)
        answers = await asyncio.gather(
            *(
                self._member(context, item.role, item.task, name)
                for item, name in zip(briefs, names, strict=True)
            )
        )
        return dict(zip(names, answers, strict=True))

    async def _member(self, context, name, task, instance=None):
        """Return one member's answer, or its error as ``{error: {code, message}}``."""
        try:
            return await self.members[name]._delegate(context, task, beside=True, instance=instance)
        except ToolError as error:
            return {"error": {"code": error.code, "message": str(error)}}


CARD_TASK_CHARACTERS = 120
"""The characters of a delegate's task its approval card shows."""
QUIET_EFFECTS = ("read", "compute")
"""The effects that need no approval: an agent whose tools have only these writes nothing."""


def agent_writes(agent, depth=0):
    """Tell whether ``agent`` or an agent it delegates to has a tool that needs an approval."""
    for tool in agent.tools().values():
        if tool.effect not in QUIET_EFFECTS:
            return True
        nested = [tool.agent] if isinstance(tool, Delegate) else []
        nested += [m.agent for m in tool.members.values()] if isinstance(tool, Team) else []
        if depth < 2 and any(agent_writes(item, depth + 1) for item in nested):
            return True
    return False

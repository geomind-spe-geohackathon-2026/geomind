"""The engine runs one agent until it stops; loops decide which run comes next.

Finite, like gemini's engine: it never sleeps or schedules itself. NOTE: unlike gemini it is
``async``, because parallel tools, streaming and the FastAPI backend need it and changing that
later would touch every layer. ``Run`` is the sync facade.
"""

import asyncio
from dataclasses import replace

from geomind import runtime
from geomind.engine.delegation import answer_child, end_left_orphans, end_orphans
from geomind.engine.log import RunLog
from geomind.engine.partial import is_limit_stop, partial_answer
from geomind.engine.permissions import Permissions
from geomind.engine.recovery import agent_class, recover
from geomind.engine.replay import replay_run
from geomind.engine.session import RunSession
from geomind.engine.state import RunState, Stop
from geomind.engine.step import (
    answered_result,
    record_result,
    report_usage,
    run_step,
    settle_interrupted,
    text_result,
)
from geomind.errors import (
    AlreadyAnsweredError,
    NotImplementedYet,
    ProviderError,
    RequestError,
    RunError,
)
from geomind.providers import with_retries
from geomind.stores.run import MemoryRunStore
from geomind.stores.usage import usage_report
from geomind.tools.suggestions import next_steps
from geomind.types import Request, RunResult, Usage, status_of, validate_answer
from geomind.types.decisions import typed_answer
from geomind.types.events import (
    PermissionDecided,
    QuestionAutoAnswered,
    RunFinished,
    ToolRecorded,
)
from geomind.utils.hooks import RemovableHandle

AUTO_ANSWERS = 30
"""The most questions Auto-approve answers in one call of ``run`` or ``resume``; then it asks."""
AUTO_TEXT = (
    "Auto-approve is on: the user answers nothing. Go on with your own proposal and record it as "
    "an assumption with source auto-approve."
)
"""The answer of a free-text question with Auto-approve on (QA-339)."""
AUTO_HEADING = "Answered automatically (Auto-approve on); change any of them in the chat:"
"""The first line of the block a root answer ends with after Auto-approve answered questions."""


def proposed_answer(request):
    """Return the answer Auto-approve gives a question: the proposal, the first option, or text."""
    if request.proposed:
        return request.proposed
    if request.options:
        return request.options[0].value
    return AUTO_TEXT


def failure_stop(error, reason):
    """Return the stop of a run an exception ended: a provider's failure keeps its message.

    NOTE: a provider's refusal is no bug, so its text reaches the result, with its ``code``
    first when it has one; any other exception is a crash, its text in the log only.
    """
    if isinstance(error, ProviderError):
        prefix = f"{error.code}: " if error.code else ""
        return Stop(reason, f"{prefix}{error}")
    return Stop(reason, crash_text(error), is_crash=reason == "error")


def crash_text(error):
    """Return a crash as its class, message and innermost file and line (QA-083, QA-319).

    A nested run that crashed told its parent only "the detail is in the log", and the log held
    the message alone ("'str' object has no attribute 'get'"), with no class or place.
    """
    import traceback
    from pathlib import Path

    frames = traceback.extract_tb(error.__traceback__)
    where = ""
    if frames:
        last = Path(frames[-1].filename)
        where = f" at {last.parent.name}/{last.name}:{frames[-1].lineno}"
    return f"{type(error).__name__}: {error}{where}"


def was_asked(session, request_id):
    """Return whether the run's log holds a request with ``request_id``: it was asked before."""
    events = session.engine.store.load_events(session.state.root)
    return any(
        event.type == "request"
        and getattr(getattr(event, "request", None), "id", None) == request_id
        for event in events
    )


def run_result(session, stop, suggestions=None, report=None):
    """Return the result of a stop; ``suggestions`` are those of its ``run.finished`` event.

    A run that waits on a nested run's request counts that run's usage so far, which joins its
    own only when the nested run ends. A nested run's crash keeps its ``crash_text`` in the
    result, so its parent reads the class and place; a root run's crash stays in the log.
    ``report`` is the root run's ``(sessions, agents, total)``.
    """
    sessions, agents, total = report or (None, None, None)
    state = session.state
    waiting = session.child_usage if stop.reason == "request" else None
    return RunResult(
        run_id=state.run_id,
        status=status_of(stop.reason),
        answer=stop.answer,
        request=stop.request,
        usage=state.usage + (waiting or Usage()),
        steps=state.step,
        stop_reason=stop.reason,
        message=None if stop.is_crash and state.parent is None else stop.message,
        suggestions=suggestions,
        sessions=sessions,
        agents=agents,
        total=total,
    )


async def tree_usage(session):
    """Return ``(sessions, agents, total)`` of a root run that ends, else ``None``.

    The last ``usage`` event is made current first, when a step ended the run before sending
    it, so the total and the last ``usage`` event agree; the report reads the stored log, so a
    run resumed in another process counts every call of its tree once.
    """
    state = session.state
    if state.parent is not None:
        return None
    reported = state.reported_usage or Usage()
    usage = state.usage
    if (reported.input_tokens, reported.output_tokens, reported.cost) != (
        usage.input_tokens,
        usage.output_tokens,
        usage.cost,
    ):
        await report_usage(session)
    events = await asyncio.to_thread(session.engine.store.load_events, state.root)
    return usage_report(events)


STEP_OPTIONS = ("continue", "stop")
"""The answers to the question a run asks at its step limit."""
STEPS_POINT = "steps"
AUTO_CONTINUES = 3
"""How often a run in ``auto`` mode takes its steps again by itself before it asks (QA-086)."""
"""The point a run pauses at when it took its steps."""


class Engine:
    """Drives one agent over steps, with one log for the run and its nested runs.

    ``callbacks``, ``hooks`` and ``permissions`` are as agreed. NOTE: ``llm``,
    ``store`` and ``workspace`` are added keywords, since a run needs them and they are not
    arguments of ``run``. The ``recorded*`` attributes are used by replay, each keyed by run id:
    ``recorded`` and ``recorded_changes`` by run, then (step, call id), ``recorded_llms`` by run id,
    ``recorded_children`` by the parent run id, step and task of a nested run, to its run id, and
    ``recorded_steps`` by run id, the decisions at its step limit, in order.
    ``reuses_tools`` makes a replay keep the result of every pure tool.
    """

    def __init__(
        self,
        callbacks=None,
        hooks=None,
        permissions=None,
        *,
        llm=None,
        store=None,
        workspace=None,
        memory=None,
        sandbox=None,
    ):
        """Keep what a run needs; ``llm`` gets the retry layer."""
        self.callbacks = list(callbacks or ())
        self._hooks = {}
        for hook in hooks or ():
            self.register_hook(hook)
        self.permissions = permissions or Permissions()
        self.llm = with_retries(llm) if llm is not None else None
        self.store = store if store is not None else MemoryRunStore()
        self.workspace = workspace
        self.sandbox = sandbox
        self.memory = memory
        self.workspace_memories = {}
        self.mcp_servers = None
        self.mcp_transport = None
        self.recorded = {}
        self.recorded_changes = {}
        self.recorded_children = {}
        self.recorded_llms = {}
        self.recorded_steps = {}
        self.reuses_tools = False
        self._sequences = {}
        self._usages = {}
        self._auto_answer = None

    def register_hook(self, hook):
        """Add a hook; the returned handle has ``.remove()``."""
        return RemovableHandle(self._hooks, hook)

    def hooks(self):
        """Return the registered hooks, in order."""
        return list(self._hooks.values())

    async def run_first(self, agent, context, *, root):
        """Run ``agent`` as a nested run of ``root`` before ``root`` starts, in its log.

        NOTE: this is the routing call: the coordinator decides which loop the root run is, so it
        runs first, with ``parent`` and ``root`` set to the root run and no ``parent_step``. The
        root run continues the numbering of the same log and starts with the routing call's usage,
        as ``recover`` counts it.
        """
        log = RunLog(self, root)
        session = RunSession(self, log, RunState(root=root), agent)
        await session.start(context, max_steps=runtime.get("max_steps"), parent=root, root=root)
        result = await self.drive(session)
        self._sequences[root] = log.sequence
        self._usages[root] = result.usage
        return result

    def _root_session(self, context, agent, loop):
        """Return the session of a new root run, after what ran first for it."""
        log = RunLog(self, context.run_id, self._sequences.pop(context.run_id, 0))
        state = RunState(root=context.run_id, usage=self._usages.pop(context.run_id, Usage()))
        return RunSession(self, log, state, agent, loop)

    async def run(self, agent, context, *, max_steps=None, loop=None):
        """Run ``agent`` from ``context`` until it stops."""
        session = self._root_session(context, agent, loop)
        await session.start(context, max_steps=max_steps or runtime.get("max_steps"))
        return await self._answer_alone(await self.drive(session), agent, loop)

    @property
    def auto_answer(self):
        """The text Auto-approve is answering the pending question with now, else ``None``.

        A tool's ``on_answer`` reads it to record the answer as auto-approved, not as the
        user's (QA-339).
        """
        return self._auto_answer

    async def _answer_alone(self, result, agent, loop):
        """Answer each question of a run in ``auto`` mode with its proposal, and go on (QA-339).

        With the chat's Auto-approve on nobody is asked anything: a question the run stops on
        (``ask_user``, the case confirmation, ``ask_economics``, the step limit, a nested run's
        question) is answered with ``proposed_answer`` through the same path as a user's answer,
        at most ``AUTO_ANSWERS`` times; an approval is left to the permissions.
        """
        if not self._answers_alone():
            return result
        answered = 0
        while (
            result.status == "waiting"
            and result.request is not None
            and result.request.kind == "question"
            and answered < AUTO_ANSWERS
        ):
            answered += 1
            text = proposed_answer(result.request)
            self._auto_answer = text
            try:
                result = await self._resumed(
                    result.run_id, result.request.id, {"text": text}, agent=agent, loop=loop
                )
            finally:
                self._auto_answer = None
        return result

    @classmethod
    async def replay(cls, store, run_id, *, replayed=None, workspace=None):
        """Rerun a stored run and its nested runs offline; a difference raises ``ReplayError``."""
        return await replay_run(cls, store, run_id, replayed=replayed, workspace=workspace)

    async def drive(self, session):
        """Run steps until one reason stops the run, then end it.

        NOTE: any exception ends the run with ``error``, not only an ``gd.errors`` class, because a
        provider made by the backend raises its own errors and a client must see the run end. The
        log and ``on_error`` hold the class and message, and a dying process (a ``BaseException``)
        is not caught, so it can be recovered. A part that is not built yet ends the run with
        ``not_implemented`` instead.
        """
        try:
            stop = await self._steps(session)
        except Exception as error:
            await session.report_error(error, where="engine")
            reason = "not_implemented" if isinstance(error, NotImplementedYet) else "error"
            stop = failure_stop(error, reason)
        return await self.end(session, stop)

    async def decline(self, loop, context, error):
        """Log a run of a loop that is not built yet, so a client sees it start and end."""
        session = self._root_session(context, loop.agent, loop)
        await session.start(context, max_steps=runtime.get("max_steps"))
        await session.report_error(error, where=f"loop {loop.name}")
        return await self.end(session, Stop("not_implemented", str(error)))

    async def _steps(self, session):
        """Run steps until one returns a stop or the step limit is reached.

        A step that asked the user a question gives its step back, so the answer is acted on even
        when the question came at the last step. At the limit the run is not lost: it waits on a
        question, ``continue`` gives it as many steps again and ``stop`` ends it with
        ``step_limit``. A budget still bounds the cost.
        """
        state = session.state
        if state.has_answer and not state.in_step:
            return Stop(state.stop_reason, answer=state.answer)
        while True:
            while state.in_step or state.step < state.max_steps + state.questions:
                stop = await run_step(session, session.agent)
                if stop is not None:
                    return stop
            recorded = self.recorded_steps.get(state.run_id)
            if not recorded and session.ends_at_limit:
                return Stop("step_limit", f"stopped after {state.step} steps")
            if not recorded and self._continues_alone(session):
                await self._decide_steps(session, True, None, rule="mode:auto")
                continue
            if not recorded:
                break
            stop = await self._decide_steps(session, recorded.pop(0) == "allow", None)
            if stop is not None:
                return stop
        request = Request(
            kind="question",
            message=(
                f"{state.agent}: the run took its {state.step} steps; continue with "
                f"{state.step_grant} more, or stop and answer from what it has?"
            ),
            options=list(STEP_OPTIONS),
        )
        return await session.pause(request, STEPS_POINT)

    async def end(self, session, stop):
        """Log the end, unless the run only pauses."""
        await session.log.flush()
        if stop.reason == "request":
            return run_result(session, stop)
        await end_left_orphans(session)
        if is_limit_stop(session, stop):
            stop = await self._answer_from_record(session, stop)
        stop = with_auto_answers(session, stop)
        status = status_of(stop.reason)
        suggestions = suggestions_of(session, status)
        report = await tree_usage(session)
        sessions, agents, total = report or (None, None, None)
        await session.emit(
            RunFinished,
            status=status,
            stop_reason=stop.reason,
            message=stop.message,
            answer=stop.answer,
            suggestions=suggestions,
            sessions=sessions,
            agents=agents,
            total=total,
        )
        await session.save_problem()
        return run_result(session, stop, suggestions, report)

    async def _answer_from_record(self, session, stop):
        """Give a run that a limit stopped the answer its record makes, streamed like any answer."""
        text = await partial_answer(session, stop)
        await session.stream_answer(text)
        return Stop(stop.reason, stop.message, answer=text)

    async def resume(self, run_id, request_id=None, answer=None, *, agent=None, loop=None):
        """Continue a run from its events, in any process.

        With ``request_id`` and ``answer`` it settles the pending request. Without them it
        continues a run whose process died. ``agent`` defaults to a new instance of the stored
        class, and ``loop`` receives its stored state. In ``auto`` mode the questions it then
        stops on are answered alone (``_answer_alone``).
        """
        if request_id is None and answer is None and self._answers_alone():
            waiting = self._waiting_question(run_id)
            if waiting is not None:
                return await self._answer_alone(waiting, agent, loop)
        result = await self._resumed(run_id, request_id, answer, agent=agent, loop=loop)
        return await self._answer_alone(result, agent, loop)

    def _answers_alone(self):
        """Tell whether this engine answers questions itself: ``auto`` mode with the switch on."""
        permissions = self.permissions
        if getattr(permissions, "mode", None) != "auto":
            return False
        return bool(getattr(permissions, "answers_questions", True))

    def _waiting_question(self, run_id):
        """Return a run that already waits on a question as a waiting result, else ``None``.

        A run that asked before a restart (or before Auto-approve was on) waits for nobody: a
        ``resume`` without an answer then gives it to ``_answer_alone``, which answers it in
        ``auto`` mode (QA-354); in another mode ``resume`` refuses a missing answer, as before.
        """
        state = recover(self.store.load_events(run_id), run_id)
        pending = state.pending
        request = pending.request if pending is not None else None
        if state.status != "running" or request is None or request.kind != "question":
            return None
        return RunResult(run_id=state.run_id, status="waiting", request=request)

    async def _resumed(self, run_id, request_id=None, answer=None, *, agent=None, loop=None):
        """Continue a run from its events once: ``resume`` without its answers in ``auto`` mode."""
        state = recover(self.store.load_events(run_id), run_id)
        if state.status != "running":
            raise RunError(f"resume: run = {state.run_id}; it already ended as {state.status}")
        if loop is not None:
            loop.load_state_dict(state.loop_state)
        agent = agent or agent_class(state)()
        agent.load_loop_state(state.loop_state)
        with runtime.settings(**runtime.stored(state.settings)):
            log = RunLog(self, state.root, state.sequence)
            session = RunSession(self, log, state, agent, loop)
            return await self.proceed(session, request_id, answer)

    async def proceed(self, session, request_id, answer):
        """Settle what the run stopped on, then drive it on."""
        state = session.state
        if state.pending is not None:
            stop = await self._answer(session, request_id, answer)
            if stop is not None:
                return await self.end(session, stop)
            return await self.drive(session)
        if request_id is not None:
            if was_asked(session, request_id):
                raise AlreadyAnsweredError(
                    f"resume: request = {request_id!r} was already answered; the run goes on"
                )
            raise RequestError(
                f"resume: request = {request_id!r}; it is unknown or already answered"
            )
        await end_orphans(session)
        await settle_interrupted(session, session.agent)
        return await self.drive(session)

    async def _answer(self, session, request_id, answer):
        """Settle the pending request; return a stop when that ends or pauses the run."""
        pending = session.state.pending
        if pending.child is not None:
            return await answer_child(session, pending, request_id, answer)
        if request_id != pending.request.id:
            if was_asked(session, request_id):
                raise AlreadyAnsweredError(
                    f"resume: request = {request_id!r} was already answered; the run waits on "
                    f"{pending.request.id!r}"
                )
            raise RequestError(f"resume: request = {request_id!r}; expected {pending.request.id!r}")
        answer = validate_answer(pending.request, answer)
        auto = self._auto_answer is not None and answer.get("text") == self._auto_answer
        if auto and pending.point != "tool":
            await self._record_auto(session, pending, answer["text"])
        if pending.point == STEPS_POINT:
            if answer["text"] not in STEP_OPTIONS:
                raise RequestError(f"answer = {answer!r}; expected one of {list(STEP_OPTIONS)}")
            return await self._take_steps(session, pending, answer["text"])
        fields = dict(
            index=session.state.step,
            rule="auto" if auto else "user",
            point=pending.point,
            call_id=pending.call.id if pending.call else None,
            tool=pending.call.name if pending.call else None,
            request=pending.request,
        )
        if "text" in answer:
            return await self._take_text(session, pending, answer["text"], fields, auto)
        if answer["approved"]:
            await session.emit(PermissionDecided, decision="allow", **fields)
            return None
        reason = answer.get("reason") or "denied by the user"
        await session.emit(PermissionDecided, decision="deny", reason=reason, **fields)
        return await self._take_denial(session, pending, reason)

    async def _record_auto(self, session, pending, text):
        """Log a question Auto-approve answered and keep it as an assumption of the state."""
        call = pending.call
        await session.emit(
            QuestionAutoAnswered,
            index=session.state.step,
            request_id=pending.request.id,
            call_id=call.id if call else None,
            tool=call.name if call else None,
            point=pending.point,
            answer=text,
        )
        taken = [
            item for item in session.state.problem.assumptions if item.source == "auto-approve"
        ]
        question = (pending.request.message or "").strip().splitlines()
        assumption = {
            "id": f"AUTO-{len(taken) + 1}",
            "text": f"{call.name if call else pending.point}: "
            f"{question[0][:AUTO_QUESTION_CHARACTERS] if question else ''} -> {text}",
            "value": text,
            "source": "auto-approve",
            "confirmed": False,
            "reason": "Auto-approve on: answered with the agents' proposal",
        }
        await session.change_state([{"op": "add", "path": "/assumptions/-", "value": assumption}])

    async def _take_steps(self, session, pending, text):
        """Give the run its steps again on ``continue``; on ``stop`` end it at its step limit."""
        rule = "auto" if self._auto_answer is not None else "user"
        return await self._decide_steps(session, text == STEP_OPTIONS[0], pending.request, rule)

    def _continues_alone(self, session):
        """Tell whether a run in ``auto`` mode takes its next steps without asking (QA-086).

        With the chat's auto-approve on nobody may be there to click continue, so the run goes on
        by itself ``AUTO_CONTINUES`` times per agent run, then asks as in any mode.
        """
        if getattr(self.permissions, "mode", None) != "auto":
            return False
        taken = session.__dict__.get("auto_continues", 0)
        if taken >= AUTO_CONTINUES:
            return False
        session.__dict__["auto_continues"] = taken + 1
        return True

    async def _decide_steps(self, session, is_continued, request, rule="user"):
        """Log the decision at the step limit; return the stop of ``stop``, else ``None``."""
        await session.emit(
            PermissionDecided,
            index=session.state.step,
            decision="allow" if is_continued else "deny",
            rule=rule,
            point=STEPS_POINT,
            request=request,
            reason=None if is_continued else "the user stopped the run at its step limit",
        )
        if is_continued:
            return None
        return Stop("step_limit", f"stopped after {session.state.step} steps")

    async def _take_text(self, session, pending, text, fields, auto=False):
        """Make a user's reply the tool result, or a message at the other points.

        An answer Auto-approve gave at a tool is recorded between its decision and its result,
        where a replay applies the logged state changes of an answered call again.
        """
        decision = "answer" if pending.point == "tool" else "allow"
        await session.emit(PermissionDecided, decision=decision, **fields)
        if auto and pending.point == "tool":
            await self._record_auto(session, pending, text)
        if pending.point == "tool":
            tool = session.agent.tools().get(pending.call.name)
            if getattr(tool, "on_answer", None) is not None:
                result = await answered_result(session, tool, pending.call, text)
            else:
                result = text_result(pending.call, typed_answer(pending.request, text))
            await record_result(session, pending.call, result, source="answer")
            return None
        await session.emit(ToolRecorded, index=session.state.step, output=text, source="answer")
        return None

    async def _take_denial(self, session, pending, reason):
        """Apply a user's denial at the point the run paused."""
        if pending.point == "llm":
            return Stop("denied", reason)
        if pending.call is None:
            await session.emit(
                ToolRecorded,
                index=session.state.step,
                output=reason,
                is_error=True,
                source="denied",
                feedback="finish",
            )
            return None
        result = text_result(pending.call, reason, is_error=True)
        await record_result(session, pending.call, result, source="denied")
        return None


def suggestions_of(session, status):
    """Return the next steps of a root run that ended ``done``, else ``None``.

    The stage comes from the project's state (``Workspace.project_state``, contract v4), else
    from the chat's problem state; the language from the user's last message; the project lead's
    own list is kept where it fits (``geomind.tools.suggestions``).
    """
    state = session.state
    if state.parent is not None or status != "done":
        return None
    users = [item.content for item in state.messages if item.role == "user"]
    workspace = session.engine.workspace
    listed = workspace.files(state.project) if state.project and hasattr(workspace, "files") else []
    files = [entry["name"] for entry in listed]
    proposed = getattr(session, "proposed_suggestions", None)
    method = getattr(workspace, "project_state", None)
    project = method(state.project) if state.project and callable(method) else None
    user = users[-1] if users else ""
    return next_steps(state.problem, files, user, proposed, project=project) or None


AUTO_QUESTION_CHARACTERS = 160
"""The characters of a question an auto-approved assumption keeps."""


def with_auto_answers(session, stop):
    """Return a root run's text answer with the questions Auto-approve answered listed after it.

    Read from the problem state, so a run resumed in another process lists every one; a nested
    run's answer and a typed answer stay as they are.
    """
    if session.state.parent is not None or not isinstance(stop.answer, str):
        return stop
    taken = [item for item in session.state.problem.assumptions if item.source == "auto-approve"]
    if not taken or AUTO_HEADING in stop.answer:
        return stop
    lines = "\n".join(f"- {item.text}" for item in taken)
    return replace(stop, answer=f"{stop.answer}\n\n{AUTO_HEADING}\n{lines}")

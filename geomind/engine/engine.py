"""The engine runs one agent until it stops; loops decide which run comes next.

Finite, like gemini's engine: it never sleeps or schedules itself. NOTE: unlike gemini it is
``async``, because parallel tools, streaming and the FastAPI backend need it and changing that
later would touch every layer. ``Run`` is the sync facade.
"""

from geomind import runtime
from geomind.engine.context import Context
from geomind.engine.log import RunLog
from geomind.engine.permissions import Permissions
from geomind.engine.recovery import agent_class, recover
from geomind.engine.replay import replay_run
from geomind.engine.session import RunSession, Stop
from geomind.engine.state import RunState
from geomind.engine.step import record_result, run_step, settle_interrupted, text_result
from geomind.engine.store import MemoryRunStore
from geomind.errors import RequestError, RunError, ToolError
from geomind.providers import with_retries
from geomind.tools.dispatch import error_output
from geomind.types import Message, RunResult, status_of, validate_answer
from geomind.types.events import PermissionDecided, RunFinished, ToolRecorded
from geomind.utils.hooks import RemovableHandle


def run_result(session, stop):
    """Return the result of a stop."""
    state = session.state
    return RunResult(
        run_id=state.run_id,
        status=status_of(stop.reason),
        answer=stop.answer,
        request=stop.request,
        usage=state.usage,
        steps=state.step,
        stop_reason=stop.reason,
    )


def result_of_state(state):
    """Return the result of a run that already ended."""
    return RunResult(
        run_id=state.run_id,
        status=state.status,
        answer=state.answer,
        usage=state.usage,
        steps=state.step,
        stop_reason=state.stop_reason,
    )


class Engine:
    """Drives one agent over steps, with one log for the run and its nested runs.

    ``callbacks``, ``hooks``, ``permissions`` and ``sandbox`` are as agreed. NOTE: ``llm``,
    ``store`` and ``workspace`` are added keywords, since a run needs them and they are not
    arguments of ``run``. ``recorded`` is used by replay.
    """

    def __init__(
        self,
        callbacks=None,
        hooks=None,
        permissions=None,
        sandbox=None,
        *,
        llm=None,
        store=None,
        workspace=None,
    ):
        """Keep what a run needs; ``llm`` gets the retry layer."""
        self.callbacks = list(callbacks or ())
        self._hooks = {}
        for hook in hooks or ():
            self.register_hook(hook)
        self.permissions = permissions or Permissions()
        self.sandbox = sandbox
        self.llm = with_retries(llm) if llm is not None else None
        self.store = store if store is not None else MemoryRunStore()
        self.workspace = workspace
        self.recorded = {}

    def register_hook(self, hook):
        """Add a hook; the returned handle has ``.remove()``."""
        return RemovableHandle(self._hooks, hook)

    def hooks(self):
        """Return the registered hooks, in order."""
        return list(self._hooks.values())

    async def run(self, agent, context, *, max_steps=None, loop=None):
        """Run ``agent`` from ``context`` until it stops."""
        log = RunLog(self, context.run_id)
        session = RunSession(self, log, RunState(root=context.run_id), agent, loop)
        await session.start(context, max_steps=max_steps or runtime.get("max_steps"))
        return await self._drive(session)

    @classmethod
    async def replay(cls, store, run_id):
        """Rerun a stored run offline; a difference raises ``ReplayError``."""
        return await replay_run(cls, store, run_id)

    async def run_child(self, parent, agent, task):
        """Run ``agent`` as a nested run with a clean context: the task text only."""
        state = parent.state
        context = Context(
            messages=[Message(role="user", content=task)], chat=state.chat, project=state.project
        )
        session = RunSession(self, parent.log, RunState(root=state.root), agent)
        await session.start(
            context,
            max_steps=runtime.get("max_steps"),
            parent=state.run_id,
            parent_step=state.step,
            root=state.root,
        )
        return await self._drive(session)

    async def _drive(self, session):
        """Run steps until one reason stops the run, then end it.

        NOTE: any exception ends the run with ``error``, not only an ``gd.errors`` class, because a
        provider made by the backend raises its own errors and a client must see the run end. The
        log and ``on_error`` hold the class and message, and a dying process (a ``BaseException``)
        is not caught, so it can be recovered.
        """
        try:
            stop = await self._steps(session)
        except Exception as error:
            await session.report_error(error, where="engine")
            stop = Stop("error", str(error))
        return await self._end(session, stop)

    async def _steps(self, session):
        """Run steps until one returns a stop or the step limit is reached."""
        state = session.state
        if state.has_answer and not state.in_step:
            return Stop(state.stop_reason, answer=state.answer)
        while state.in_step or state.step < state.max_steps:
            stop = await run_step(session, session.agent)
            if stop is not None:
                return stop
        return Stop("step_limit", f"stopped after {state.step} steps")

    async def _end(self, session, stop):
        """Close the sandbox and log the end, unless the run only pauses."""
        await session.log.flush()
        await session.close_sandbox()
        if stop.reason == "request":
            return run_result(session, stop)
        await session.emit(
            RunFinished,
            status=status_of(stop.reason),
            stop_reason=stop.reason,
            message=stop.message,
            answer=stop.answer,
        )
        return run_result(session, stop)

    async def resume(self, run_id, request_id=None, answer=None, *, agent=None, loop=None):
        """Continue a run from its events, in any process.

        With ``request_id`` and ``answer`` it settles the pending request. Without them it
        continues a run whose process died. ``agent`` defaults to a new instance of the stored
        class, and ``loop`` receives its stored state.
        """
        state = recover(self.store.load_events(run_id), run_id)
        if state.status != "running":
            raise RunError(f"resume: run = {state.run_id}; it already ended as {state.status}")
        if loop is not None:
            loop.load_state_dict(state.loop_state)
        agent = agent or agent_class(state)()
        with runtime.settings(**state.settings):
            log = RunLog(self, state.root, state.sequence)
            session = RunSession(self, log, state, agent, loop)
            return await self._continue(session, request_id, answer)

    async def _continue(self, session, request_id, answer):
        """Settle what the run stopped on, then drive it on."""
        state = session.state
        if state.pending is not None:
            stop = await self._answer(session, request_id, answer)
            if stop is not None:
                return await self._end(session, stop)
            return await self._drive(session)
        if request_id is not None:
            raise RequestError(
                f"resume: request = {request_id!r}; it is unknown or already answered"
            )
        await self._end_orphans(session)
        await settle_interrupted(session, session.agent)
        return await self._drive(session)

    async def _end_orphans(self, session):
        """End nested runs a crash left open, and keep what they spent for the parent."""
        state = session.state
        events = self.store.load_events(state.root)
        ended = {event.run_id for event in events if event.type == "run.finished"}
        for event in events:
            is_child = event.type == "run.started" and event.parent == state.run_id
            if is_child and event.run_id not in ended:
                orphan = recover(events, event.run_id)
                child = RunSession(self, session.log, orphan, None)
                await self._end(child, Stop("error", "interrupted by a crash"))
                session.child_usage = orphan.usage

    async def _answer(self, session, request_id, answer):
        """Settle the pending request; return a stop when that ends or pauses the run."""
        pending = session.state.pending
        if pending.child is not None:
            return await self._answer_child(session, pending, request_id, answer)
        if request_id != pending.request.id:
            raise RequestError(f"resume: request = {request_id!r}; expected {pending.request.id!r}")
        answer = validate_answer(pending.request, answer)
        fields = dict(
            index=session.state.step,
            rule="user",
            point=pending.point,
            call_id=pending.call.id if pending.call else None,
            tool=pending.call.name if pending.call else None,
            request=pending.request,
        )
        if "text" in answer:
            return await self._take_text(session, pending, answer["text"], fields)
        if answer["approved"]:
            await session.emit(PermissionDecided, decision="allow", **fields)
            return None
        reason = answer.get("reason") or "denied by the user"
        await session.emit(PermissionDecided, decision="deny", reason=reason, **fields)
        return await self._take_denial(session, pending, reason)

    async def _take_text(self, session, pending, text, fields):
        """Make a user's reply the tool result, or a message at the other points."""
        decision = "answer" if pending.point == "tool" else "allow"
        await session.emit(PermissionDecided, decision=decision, **fields)
        if pending.point == "tool":
            result = text_result(pending.call, text)
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

    async def _answer_child(self, session, pending, request_id, answer):
        """Pass an answer to the nested run that asked; its outcome is the tool result.

        A crash can come after the answer reached the nested run. The log then shows it holds
        no request, so it continues without one, or has ended, so its outcome stands.
        """
        tool = session.agent.tools()[pending.call.name]
        state = recover(self.store.load_events(session.state.root), pending.child)
        if state.status != "running":
            result = result_of_state(state)
        elif state.pending is None:
            child = RunSession(self, session.log, state, tool.agent)
            result = await self._continue(child, None, None)
        else:
            child = RunSession(self, session.log, state, tool.agent)
            result = await self._continue(child, request_id, answer)
        session.child_usage = result.usage
        return await self._finish_delegate(session, pending, tool, result)

    async def _finish_delegate(self, session, pending, tool, result):
        """Turn the outcome of a nested run into the result of the delegate call."""
        try:
            outcome = tool.outcome(result)
        except ToolError as error:
            failed = text_result(pending.call, error_output(error), is_error=True)
            await record_result(session, pending.call, failed)
            return None
        if result.request is not None:
            session.waiting_child = result.run_id
            return await session.wait_for_child(outcome, pending.call)
        await record_result(session, pending.call, text_result(pending.call, outcome))
        return None

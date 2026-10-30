"""The engine runs one agent until it stops; loops decide which run comes next.

Finite, like gemini's engine: it never sleeps or schedules itself. NOTE: unlike gemini it is
``async``, because parallel tools, streaming and the FastAPI backend need it and changing that
later would touch every layer. ``Run`` is the sync facade.
"""

from swarmax.core import runtime
from swarmax.core.engine.checkpoint import Checkpoint, import_class
from swarmax.core.engine.context import Context
from swarmax.core.engine.log import RunLog
from swarmax.core.engine.permissions import Permissions
from swarmax.core.engine.recovery import catch_up
from swarmax.core.engine.replay import replay_run
from swarmax.core.engine.session import RunSession, Stop
from swarmax.core.engine.step import record_result, run_step, settle_interrupted, text_result
from swarmax.core.engine.store import MemoryRunStore
from swarmax.core.types import Message, RunResult, status_of, validate_answer
from swarmax.core.types.events import PermissionDecided, RunFinished, ToolRecorded
from swarmax.errors import RequestError, RunError, SwarmaxError, ToolError
from swarmax.providers import with_retries
from swarmax.tools.dispatch import error_output
from swarmax.utils.hooks import RemovableHandle


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
        session = RunSession(self, log, Checkpoint(root=context.run_id), agent, loop)
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
        session = RunSession(self, parent.log, Checkpoint(root=state.root), agent)
        await session.start(
            context,
            max_steps=runtime.get("max_steps"),
            parent=state.run_id,
            parent_step=state.step,
            root=state.root,
        )
        return await self._drive(session)

    async def _drive(self, session):
        """Run steps until one reason stops the run, then end it."""
        with runtime.activate(session):
            try:
                stop = await self._steps(session)
            except SwarmaxError as error:
                await session.report_error(error, where="engine")
                stop = Stop("error", str(error))
            return await self._end(session, stop)

    async def _steps(self, session):
        """Run steps until one returns a stop or the step limit is reached."""
        state = session.state
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
        await session.save_checkpoint()
        return run_result(session, stop)

    def _latest(self, checkpoint):
        """Return the state of a checkpoint plus whatever the log holds after it."""
        state = checkpoint if isinstance(checkpoint, Checkpoint) else Checkpoint.load(checkpoint)
        load_events = getattr(self.store, "load_events", None)
        return catch_up(state, load_events(state.root)) if load_events else state

    async def resume(self, checkpoint, request_id=None, answer=None, *, agent=None, loop=None):
        """Continue a run from a checkpoint, in any process.

        With ``request_id`` and ``answer`` it settles the pending request. Without them it
        continues a run whose process died. ``agent`` defaults to a new instance of the stored
        class, and ``loop`` receives its stored state.
        """
        state = self._latest(checkpoint)
        if state.status != "running":
            raise RunError(f"resume: run = {state.run_id}; it already ended as {state.status}")
        if loop is not None:
            loop.load_state_dict(state.loop_state)
        agent = agent or import_class(state.agent_class)()
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
        await settle_interrupted(session, session.agent)
        return await self._drive(session)

    async def _answer(self, session, request_id, answer):
        """Settle the pending request; return a stop when that ends or pauses the run."""
        pending = session.state.pending
        if request_id != pending.request.id:
            raise RequestError(f"resume: request = {request_id!r}; expected {pending.request.id!r}")
        answer = validate_answer(pending.request, answer)
        if pending.child is not None:
            return await self._answer_child(session, pending, answer)
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

    async def _answer_child(self, session, pending, answer):
        """Pass an answer to the nested run that asked; its outcome is the tool result."""
        tool = session.agent.tools()[pending.call.name]
        data = await self._load_checkpoint(pending.child)
        state = self._latest(data)
        child = RunSession(self, session.log, state, tool.agent)
        result = await self._continue(child, pending.request.id, answer)
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

    async def _load_checkpoint(self, run_id):
        """Return a stored checkpoint."""
        data = self.store.load_checkpoint(run_id)
        if data is None:
            raise RunError(f"resume: run = {run_id!r}; no checkpoint is stored")
        return data

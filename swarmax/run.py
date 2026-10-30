"""The facade the backend uses, as ``contracts.md`` section 3 fixes it."""

import asyncio

from swarmax.core.agents import Assistant, CodeAssistant
from swarmax.core.engine import Context, Engine, Permissions
from swarmax.core.engine.checkpoint import Checkpoint, import_class
from swarmax.core.engine.context import new_run_id
from swarmax.core.engine.hooks import Cancellation
from swarmax.core.engine.recovery import recover
from swarmax.core.engine.store import MemoryRunStore
from swarmax.core.types import Message
from swarmax.errors import RunError
from swarmax.loops import ToolLoop
from swarmax.providers import OpenRouter


def _sync(coroutine):
    """Run a coroutine for a sync caller; inside an event loop the ``a``-methods are the way."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    coroutine.close()
    raise RunError("Run: called inside an event loop; expected astart() or aresume()")


def _load_state(store, run_id):
    """Return the latest state of a run: from its log, else from its checkpoint.

    NOTE: ``load_events`` is not in the backend contract yet, so a store without it has only its
    checkpoint.
    """
    events = store.load_events(run_id) if hasattr(store, "load_events") else ()
    if events:
        return recover(events, run_id)
    data = store.load_checkpoint(run_id)
    if data is None:
        raise RunError(f"Run: run = {run_id!r}; nothing is stored for it")
    return Checkpoint.load(data)


class Run:
    """One message answered by the harness, with ``start``, ``load``, ``resume`` and ``cancel``.

    In S1 a run uses ``ToolLoop`` with ``Assistant``, or ``CodeAssistant`` when a sandbox is
    configured. S2 replaces this with the coordinator, without changing this signature.
    """

    def __init__(
        self,
        message=None,
        *,
        chat=None,
        project=None,
        history=(),
        llm=None,
        store=None,
        workspace=None,
        sandbox=None,
        permissions=None,
        callbacks=(),
        hooks=(),
    ):
        """Prepare a run; nothing happens before ``start``."""
        self.id = new_run_id()
        self.message = message
        self.chat = chat
        self.project = project
        self.history = list(history)
        self.store = store if store is not None else MemoryRunStore()
        self._is_cancelled = False
        self.engine = Engine(
            callbacks,
            [*hooks, Cancellation(lambda: self._is_cancelled)],
            permissions or Permissions(mode="ask"),
            sandbox,
            llm=llm if llm is not None else OpenRouter(),
            store=self.store,
            workspace=workspace,
        )
        self.loop = ToolLoop(CodeAssistant() if sandbox is not None else Assistant())

    @classmethod
    def load(cls, run_id, **options):
        """Rebuild a run in any process; hooks and callbacks are code, so they are passed again."""
        run = cls(**options)
        run.id = run_id
        state = _load_state(run.store, run_id)
        run.chat = state.chat
        run.project = state.project
        run.loop = ToolLoop(import_class(state.agent_class)())
        return run

    async def astart(self):
        """Run until the answer or a pause."""
        if self.message is None:
            raise RunError("Run: message = None; expected a message to start with")
        messages = [*self.history, Message(role="user", content=self.message)]
        context = Context(self.id, messages, chat=self.chat, project=self.project)
        return await self.loop.run(self.engine, context)

    async def aresume(self, request_id=None, answer=None):
        """Answer the pending request, or continue a run whose process died.

        NOTE: continuing a dead run needs ``load_events``: without the events after the last
        checkpoint, recorded calls would run twice, so that raises instead.
        """
        if request_id is None and not hasattr(self.store, "load_events"):
            raise RunError("Run: resume() needs a store with load_events; see contracts.md")
        state = _load_state(self.store, self.id)
        return await self.loop.resume(self.engine, state, request_id, answer)

    def start(self):
        """Run until the answer or a pause; sync form of ``astart``."""
        return _sync(self.astart())

    def resume(self, request_id=None, answer=None):
        """Continue the run; sync form of ``aresume``."""
        return _sync(self.aresume(request_id, answer))

    def cancel(self):
        """Stop the run at the next hook point; across processes use ``sx.hooks.Cancellation``."""
        self._is_cancelled = True

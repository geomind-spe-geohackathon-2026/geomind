"""The facade the backend uses, as ``contracts.md`` section 3 fixes it."""

import asyncio

from geomind.agents import Assistant, CodeAssistant
from geomind.engine import Context, Engine, Permissions
from geomind.engine.context import new_run_id
from geomind.engine.hooks import Cancellation
from geomind.engine.recovery import agent_class, recover
from geomind.errors import RunError
from geomind.loops import ToolLoop
from geomind.providers import OpenRouter
from geomind.stores.run import MemoryRunStore
from geomind.types import Message


def _sync(coroutine):
    """Run a coroutine for a sync caller; inside an event loop the ``a``-methods are the way."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    coroutine.close()
    raise RunError("Run: called inside an event loop; expected astart() or aresume()")


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
    def load(
        cls,
        run_id,
        *,
        llm=None,
        store=None,
        workspace=None,
        sandbox=None,
        permissions=None,
        callbacks=(),
        hooks=(),
    ):
        """Rebuild a run in any process; what is code or a service is passed again."""
        run = cls(
            llm=llm,
            store=store,
            workspace=workspace,
            sandbox=sandbox,
            permissions=permissions,
            callbacks=callbacks,
            hooks=hooks,
        )
        run.id = run_id
        state = recover(run.store.load_events(run_id), run_id)
        run.chat = state.chat
        run.project = state.project
        run.loop = ToolLoop(agent_class(state)())
        return run

    async def astart(self):
        """Run until the answer or a pause."""
        if self.message is None:
            raise RunError("Run: message = None; expected a message to start with")
        messages = [*self.history, Message(role="user", content=self.message)]
        context = Context(self.id, messages, chat=self.chat, project=self.project)
        return await self.loop.run(self.engine, context)

    async def aresume(self, request_id=None, answer=None):
        """Answer the pending request, or continue a run whose process died."""
        return await self.loop.resume(self.engine, self.id, request_id, answer)

    def start(self):
        """Run until the answer or a pause; sync form of ``astart``."""
        return _sync(self.astart())

    def resume(self, request_id=None, answer=None):
        """Continue the run; sync form of ``aresume``."""
        return _sync(self.aresume(request_id, answer))

    def cancel(self):
        """Stop the run at the next hook point; across processes use ``gd.hooks.Cancellation``."""
        self._is_cancelled = True

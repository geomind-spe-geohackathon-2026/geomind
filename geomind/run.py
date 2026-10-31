"""The facade the backend uses, as ``contracts.md`` section 3 fixes it."""

import asyncio

from geomind.agents import Analyst, CodeAssistant, Designer, Verifier
from geomind.context import ProblemState, restore
from geomind.engine import Context, Engine, Permissions
from geomind.engine.context import new_run_id
from geomind.engine.hooks import Cancellation
from geomind.engine.recovery import agent_class, recover
from geomind.errors import NotImplementedYet, RunError
from geomind.loops import CompareLoop, DesignLoop, MakerCheckerLoop, ToolLoop
from geomind.providers import OpenRouter
from geomind.stores.run import MemoryRunStore
from geomind.types import Message

LOOPS = {
    "tool": ToolLoop,
    "design": DesignLoop,
    "makerchecker": MakerCheckerLoop,
    "compare": CompareLoop,
}
AGENTS = {"analyst": Analyst, "code_assistant": CodeAssistant}


def _sync(coroutine):
    """Run a coroutine for a sync caller; inside an event loop the ``a``-methods are the way."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    coroutine.close()
    raise RunError("Run: called inside an event loop; expected astart() or aresume()")


def loop_of(route):
    """Return the loop a ``Route`` names, with its agents."""
    if route.loop == "tool":
        return LOOPS["tool"](AGENTS[route.agent]())
    if route.loop == "makerchecker":
        return LOOPS["makerchecker"](Designer(), Verifier())
    design = LOOPS["design"](Designer(), Verifier())
    return design if route.loop == "design" else LOOPS["compare"](design, (), ())


class Run:
    """One message answered by the harness, with ``start``, ``load``, ``resume`` and ``cancel``.

    A run uses a loop of ``LOOPS`` with an agent of ``AGENTS``: for now ``ToolLoop`` with
    ``Analyst``, or ``CodeAssistant`` when a sandbox is configured. ``agent`` replaces that choice,
    for testing one agent by hand. The coordinator takes over the routing later, without changing
    this signature, and a new agent is one row in ``AGENTS``.
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
        agent=None,
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
        routed = AGENTS["code_assistant" if sandbox is not None else "analyst"]
        self.loop = LOOPS["tool"](agent if agent is not None else routed())

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
        run.loop = LOOPS["tool"](agent_class(state)())
        return run

    async def astart(self):
        """Run until the answer or a pause."""
        if self.message is None:
            raise RunError("Run: message = None; expected a message to start with")
        problem = await asyncio.to_thread(self._load_problem)
        history = restore(self.history, problem.compaction)
        messages = [*history, Message(role="user", content=self.message)]
        context = Context(self.id, messages, chat=self.chat, project=self.project, problem=problem)
        try:
            return await self.loop.run(self.engine, context)
        except NotImplementedYet as error:
            return await self.engine.decline(self.loop, context, error)

    def _load_problem(self):
        """Return the problem state of the chat; a run without one starts empty."""
        stored = self.store.load_state(self.chat) if self.chat is not None else None
        return ProblemState() if stored is None else ProblemState.model_validate(stored)

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

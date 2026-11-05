"""The facade the backend uses, as ``contracts.md`` section 3 fixes it."""

import asyncio

from geomind.agents import AnalysisLead, Coordinator, DesignLead, ProjectLead, Reviewer, Route
from geomind.agents.project.comparison import CompareDriver
from geomind.agents.project.coordinator import Answer
from geomind.agents.project.drivers import DesignDriver
from geomind.context import ProblemState, restore
from geomind.engine import Context, Engine, Permissions
from geomind.engine.context import new_run_id
from geomind.engine.hooks import Cancellation
from geomind.engine.recovery import agent_class, recover
from geomind.errors import NotImplementedYet, RunError
from geomind.loops import CompareLoop, DesignLoop, ProjectLoop, StudyCompareLoop, ToolLoop
from geomind.providers import OpenRouter
from geomind.stores.run import MemoryRunStore
from geomind.types import Message

LOOPS = {
    "tool": ToolLoop,
    "project": ProjectLoop,
    "design": DesignLoop,
    "compare": CompareLoop,
}
AGENTS = {"analysis_lead": AnalysisLead}
BRIEF = "The coordinator's brief: "
"""How the coordinator's ``task`` starts, as a second message after the user's own."""


def _sync(coroutine):
    """Run a coroutine for a sync caller; inside an event loop the ``a``-methods are the way."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    coroutine.close()
    raise RunError("Run: called inside an event loop; expected astart() or aresume()")


ANSWER_LOOP = "answer"
"""The loop name a run of an ``answer`` route records (QA-190: it was ``tool``)."""


def loop_of(route):
    """Return the loop a ``Route`` names, with its agents; an ``answer`` route answers by rule.

    An answer runs in a tool loop named ``answer``, so the run and its log say it was a direct
    answer, not a tool run of an agent.
    """
    if route.kind == "answer":
        loop = LOOPS["tool"](Answer(route.answer or ""))
        loop.name = ANSWER_LOOP
        return loop
    if route.loop == "tool":
        return LOOPS["tool"](AGENTS[route.agent]())
    if route.loop == "project":
        return LOOPS["project"](ProjectLead())
    return LOOPS[route.loop](DesignLead(), Reviewer())


def loop_for(state):
    """Return the loop a stored run was started with, around the agent it names."""
    agent = agent_class(state)()
    if state.loop == "project":
        return LOOPS["project"](agent)
    if state.loop in ("design", "compare") and isinstance(agent, DesignDriver):
        agents = agent.tools()
        limit = {key: value for key, value in state.loop_state.items() if key == "max_rounds"}
        kind = StudyCompareLoop if isinstance(agent, CompareDriver) else LOOPS[state.loop]
        return kind(agents["design_lead"].agent, agents["reviewer"].agent, **limit)
    return LOOPS["tool"](agent)


class Run:
    """One message answered by the harness, with ``start``, ``load``, ``resume`` and ``cancel``.

    A run uses a loop of ``LOOPS`` with an agent of ``AGENTS``. ``start`` asks the ``Coordinator``
    first: its ``Route`` names the loop and the agent, so the backend never chooses them. The
    routing call is a nested run of this run, logged before it starts. ``agent`` replaces the
    routing, for testing one agent by hand, and so does a ``loop`` set before ``start``.
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
        permissions=None,
        callbacks=(),
        hooks=(),
        agent=None,
        sandbox=None,
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
            llm=llm if llm is not None else OpenRouter(),
            store=self.store,
            workspace=workspace,
            sandbox=sandbox,
        )
        self._loop = LOOPS["tool"](agent if agent is not None else AGENTS["analysis_lead"]())
        self._is_routed = agent is not None
        self._route = None

    @property
    def loop(self):
        """Return the loop of this run."""
        return self._loop

    @loop.setter
    def loop(self, loop):
        """Use ``loop`` and skip the routing."""
        self._loop = loop
        self._is_routed = True

    def _context(self, problem):
        """Return the context of this run's message, after the chat's history.

        The route's brief follows the message, and its preferences join the problem state.
        """
        history = restore(self.history, problem.compaction)
        messages = [*history, Message(role="user", content=self.message)]
        route = self._route
        if route is not None and route.task:
            messages.append(Message(role="user", content=f"{BRIEF}{route.task}"))
        if route is not None and route.preferences:
            preferences = {**problem.preferences, **route.preferences}
            problem = problem.model_copy(update={"preferences": preferences})
        return Context(self.id, messages, chat=self.chat, project=self.project, problem=problem)

    async def _route_message(self):
        """Ask the ``Coordinator`` where the message goes and take that loop; return the route.

        A routing run that fails keeps the default loop; its answer was validated as a ``Route``.
        """
        problem = await asyncio.to_thread(self._load_problem)
        start = self._context(problem)
        context = Context(
            f"{self.id}-route",
            start.messages,
            chat=self.chat,
            project=self.project,
            problem=problem,
        )
        result = await self.engine.run_first(Coordinator(), context, root=self.id)
        self._is_routed = True
        if result.status != "done":
            return None
        route = Route.model_validate(result.answer)
        self._loop = loop_of(route)
        self._route = route
        return route

    @classmethod
    def load(
        cls,
        run_id,
        *,
        llm=None,
        store=None,
        workspace=None,
        permissions=None,
        callbacks=(),
        hooks=(),
        sandbox=None,
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
        run.loop = loop_for(state)
        return run

    async def astart(self):
        """Run until the answer or a pause."""
        if self.message is None:
            raise RunError("Run: message = None; expected a message to start with")
        if not self._is_routed:
            await self._route_message()
        problem = await asyncio.to_thread(self._load_problem)
        context = self._context(problem)
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

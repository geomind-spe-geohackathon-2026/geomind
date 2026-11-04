"""B4: with the memory off no agent is offered a memory tool, and no prompt speaks of memory.

A production run with the memory off answered ``search_memory`` with code ``internal``: 0.4.22
took the bound ``Workspace.memory`` method itself as the memory, offered the memory tools, and
``memory.entries`` failed.
"""

import re

import pytest

from geomind import runtime
from geomind.agents import Agent, Model, named
from geomind.engine import Context, Engine, Permissions
from geomind.engine.session import RunSession
from geomind.engine.state import RunState
from geomind.prompts import Prompt
from geomind.providers import FakeLLM
from geomind.stores import MemoryWorkspace
from geomind.tools import Delegate, finish
from geomind.tools.memory import MEMORY_TOOLS
from tests.fixtures.runs import call, context, engine_for, says, uses

AGENTS = (
    "analysis_lead",
    "case_lead",
    "coordinator",
    "curator",
    "design_lead",
    "economist",
    "energy_systems_engineer",
    "explainer",
    "geoscientist",
    "integration_engineer",
    "process_engineer",
    "project_lead",
    "reservoir_engineer",
    "reviewer",
    "summarizer",
    "support_lead",
    "well_engineer",
)
SPOKEN = re.compile(r"memory|lesson|curator|experience", re.IGNORECASE)
"""What a prompt or a tool's description with the memory off never says."""


class NoMemory(MemoryWorkspace):
    """A workspace that gives no memory for any project: the memory off."""

    def __init__(self):
        """Count the projects asked."""
        super().__init__()
        self.asked = []

    def memory(self, project_id):
        """Return ``None``: the memory is off for every project."""
        self.asked.append(project_id)


def offered(session, name):
    """Return the system prompt and the offered tool schemas of one agent in ``session``."""
    agent = named(name)
    prompt = Context(project="p1", session=session)._prefix(agent)
    return "\n".join(message.content for message in prompt), session.offered_schemas(agent)


def memory_off_sessions():
    """Yield a session with the memory off by the setting, then by the workspace's ``None``."""
    with runtime.settings(memory="off"):
        yield RunSession(engine_for([says()]), None, RunState(project="p1"), None)
    with runtime.settings(memory="on", memory_dir="/nonexistent", memory_similarity=0.5):
        engine = engine_for([says()], workspace=NoMemory())
        yield RunSession(engine, None, RunState(project="p1"), None)


@pytest.mark.parametrize("name", AGENTS)
def test_no_agent_is_offered_or_told_of_the_memory_when_it_is_off(name):
    """Settings off and workspace ``None``: no memory tool, no curator, no word of memory.

    The curator keeps its prompt: it is never offered then, and it has no tool left.
    """
    for session in memory_off_sessions():
        prompt, schemas = offered(session, name)
        names = {item["name"] for item in schemas}
        assert not names & (MEMORY_TOOLS | {"curator"}), name
        if name != "curator":
            assert not SPOKEN.findall(prompt), (name, SPOKEN.findall(prompt))
        described = " ".join(item.get("description", "") for item in schemas)
        assert not SPOKEN.findall(described), (name, SPOKEN.findall(described))


def test_every_shipped_agent_is_checked():
    """The list above names every shipped agent, so a new one is checked too."""
    import geomind.agents as agents

    shipped = {
        named_class
        for named_class in vars(agents).values()
        if isinstance(named_class, type) and issubclass(named_class, Agent)
    }
    assert {type(named(name)) for name in AGENTS} == shipped - {Agent}


def test_with_the_memory_on_the_prompts_still_speak_of_it():
    """The memory on keeps the memory section and the curator's own prompt."""
    from geomind.stores.memory import MemoryMemory

    engine = engine_for([says()], memory=MemoryMemory())
    session = RunSession(engine, None, RunState(project="p1"), None)
    with runtime.settings(memory_similarity=0.5):
        design, _ = offered(session, "design_lead")
        curator, _ = offered(session, "curator")
        support, schemas = offered(session, "support_lead")
    assert "## Memory" in design and "search_memory" in curator
    assert "curator" in support and "curator" in {item["name"] for item in schemas}


class Root(Agent):
    """A root that hands work to the support lead and the design lead."""

    def __init__(self):
        """Declare the two teams as members."""
        super().__init__()
        self.prompt = Prompt.text("Hand the work on.")
        self.support_lead = Delegate(named("support_lead"))
        self.design_lead = Delegate(named("design_lead"))
        self.finish = finish
        self.model = Model("fake/model")


async def test_nested_runs_of_a_project_whose_workspace_gives_no_memory_see_none():
    """The workspace's ``None`` reaches every nested run: no memory tool, no word of memory."""
    workspace = NoMemory()
    completions = [
        uses(call("support_lead", task="keep the lessons")),
        says("no lessons are kept"),
        uses(call("design_lead", call_id="c2", task="design")),
        says("designed"),
        says("done"),
    ]
    llm = FakeLLM(completions)
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"), workspace=workspace)
    with runtime.settings(memory="on", memory_dir="/nonexistent", memory_similarity=0.5):
        result = await engine.run(Root(), context(project="p1"))
    assert result.status == "done"
    calls = llm.calls
    assert len(calls) == len(completions) and set(workspace.asked) == {"p1"}
    for item in calls[1:4:2]:
        names = {schema["name"] for schema in item["tools"]}
        system = "\n".join(m.content for m in item["messages"] if m.role == "system")
        assert not names & (MEMORY_TOOLS | {"curator"})
        assert not SPOKEN.findall(system), SPOKEN.findall(system)

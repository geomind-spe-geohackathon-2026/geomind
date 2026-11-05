"""Scripted runs for engine tests: agents, tools and shorthand completions."""

import asyncio
import json
import math

from geomind.agents import Agent, Model
from geomind.engine import Context, Engine, Permissions
from geomind.errors import ToolError
from geomind.prompts import Prompt
from geomind.providers import FakeLLM
from geomind.tools import Delegate, ask_user, finish, tool
from geomind.types import Completion, Message, ToolCall, Usage
from geomind.types.events import LLM_EVENTS

USAGE = Usage(input_tokens=10, output_tokens=5, cost=0.01)
STEPS = 30
"""The step limit of a run a module-scoped fixture makes, before the per-test settings apply."""
EXECUTED = []
"""Names of the tools that really ran in this process; tests clear it through a fixture."""


@tool(effect="read")
def lookup(key: str):
    """Look a value up."""
    EXECUTED.append("lookup")
    return f"value of {key}"


@tool(effect="compute")
async def add(left: int, right: int):
    """Add two numbers."""
    EXECUTED.append("add")
    await asyncio.sleep(0)
    return left + right


@tool(effect="write", idempotent=False)
def save_note(text: str):
    """Save a note."""
    EXECUTED.append("save_note")
    return f"saved {text}"


@tool(effect="execute")
def run_code(code: str):
    """Run code: a stand-in for a tool that executes, which refuses, as no code runs here."""
    EXECUTED.append("run_code")
    raise ToolError("run_code: no code runs in geomind", code="not_allowed")


@tool(effect="write")
def save_again(text: str):
    """Save a note; running this twice does no harm."""
    EXECUTED.append("save_again")
    return f"saved {text}"


class Worker(Agent):
    """Works with a few tools."""

    def __init__(self):
        """Declare the tools."""
        super().__init__()

        # Prompt
        self.prompt = Prompt.text("Work.")

        # Tools
        self.lookup = lookup
        self.add = add
        self.save_note = save_note
        self.save_again = save_again
        self.run_code = run_code
        self.ask_user = ask_user
        self.finish = finish

        # Model
        self.model = Model("fake/model")


class Helper(Worker):
    """Helps with one task."""


class Lead(Agent):
    """Delegates work to a helper."""

    def __init__(self):
        """Declare the child and its tool."""
        super().__init__()

        # Agents
        self.helper_agent = Helper()

        # Tools
        self.helper = Delegate(self.helper_agent, max_summary_tokens=10)
        self.lookup = lookup
        self.run_code = run_code

        # Model
        self.model = Model("fake/model")


def call(name, call_id="c1", **tool_input):
    """Return one tool call."""
    return ToolCall(id=call_id, name=name, input=tool_input)


def says(text="done", usage=USAGE):
    """Return a completion that answers."""
    return Completion(text=text, usage=usage, model="fake/model")


def uses(*calls, text="", usage=USAGE):
    """Return a completion that calls tools."""
    return Completion(text=text, tool_calls=calls, usage=usage, model="fake/model")


def context(text="go", **options):
    """Return a fresh context with one user message."""
    return Context(messages=[Message(role="user", content=text)], **options)


def engine_for(completions, **options):
    """Return an engine with a scripted provider and, by default, no permission questions."""
    options.setdefault("permissions", Permissions(mode="auto", answers_questions=False))
    return Engine(llm=FakeLLM(completions), **options)


async def run(completions, agent=None, max_steps=None, **options):
    """Run scripted completions; return ``(result, engine, events)``."""
    engine = engine_for(completions, **options)
    start = context()
    result = await engine.run(agent or Worker(), start, max_steps=max_steps)
    return result, engine, engine.store.load_events(start.run_id)


async def stopped_at_limit(engine, result, agent=None):
    """Answer ``stop`` to each step-limit question of a run; return its last result."""
    from geomind.engine.engine import STEP_OPTIONS

    while result.status == "waiting" and result.request.options:
        if [option.value for option in result.request.options] != list(STEP_OPTIONS):
            break
        answer = {"text": STEP_OPTIONS[1]}
        result = await engine.resume(result.run_id, result.request.id, answer, agent=agent)
    return result


def types(events):
    """Return the types of events."""
    return [event.type for event in events]


def logged(events):
    """Return the usage of every completion in a log, nested runs included."""
    usage = Usage()
    for event in events:
        if event.type in LLM_EVENTS:
            usage += event.completion.usage
    return usage


def same_usage(first, second):
    """Tell whether two usages have the same tokens and, up to rounding, the same cost."""
    tokens = (first.input_tokens, first.output_tokens) == (
        second.input_tokens,
        second.output_tokens,
    )
    return tokens and math.isclose(first.cost, second.cost, rel_tol=1e-9)


def of_type(events, kind):
    """Return the events of one type."""
    return [event for event in events if event.type == kind]


def routed(loop="tool", agent="analysis_lead", **route):
    """Return the coordinator's completion that routes a run to a loop and an agent."""
    return says(json.dumps({"kind": "loop", "loop": loop, "agent": agent, **route}))


ROUTE = routed()
"""The route of a plain question: the tool loop with the analysis lead."""

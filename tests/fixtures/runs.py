"""Scripted runs for engine tests: agents, tools and shorthand completions."""

import asyncio

from swarmax.core.agents import Agent, Model
from swarmax.core.engine import Context, Engine, Permissions
from swarmax.core.prompts import Prompt
from swarmax.core.types import Completion, Message, ToolCall, Usage
from swarmax.providers import FakeLLM
from swarmax.tools import ask_user, finish, run_python, tool

USAGE = Usage(input_tokens=10, output_tokens=5, cost=0.01)
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
        self.run_python = run_python
        self.ask_user = ask_user
        self.finish = finish

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
    options.setdefault("permissions", Permissions(mode="auto"))
    return Engine(llm=FakeLLM(completions), **options)


async def run(completions, agent=None, max_steps=None, **options):
    """Run scripted completions; return ``(result, engine, events)``."""
    engine = engine_for(completions, **options)
    start = context()
    result = await engine.run(agent or Worker(), start, max_steps=max_steps)
    return result, engine, engine.store.load_events(start.run_id)


def types(events):
    """Return the types of events."""
    return [event.type for event in events]


def of_type(events, kind):
    """Return the events of one type."""
    return [event for event in events if event.type == kind]

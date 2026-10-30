"""The order of what the model sees."""

import pydantic

from geomind.agents import Agent, Output
from geomind.engine import Context
from geomind.prompts import Prompt
from geomind.types import Message


class Typed(pydantic.BaseModel):
    """A typed answer."""

    value: int


class Plain(Agent):
    """An agent with a prompt."""

    def __init__(self):
        """Declare the prompt."""
        super().__init__()

        # Prompt
        self.prompt = Prompt.text("Stable.")


class Structured(Plain):
    """An agent with a typed answer."""

    def __init__(self):
        """Declare the output."""
        super().__init__()

        # Output
        self.output = Output(Typed)


class Silent(Agent):
    """An agent without a prompt."""


HISTORY = [Message(role="user", content="q"), Message(role="assistant", content="a")]


def test_stable_prefix_then_history_then_dynamic():
    """The dynamic part comes last, so the prefix stays cacheable."""
    messages = Context("r", HISTORY, steps_left=3).messages_for(Plain())
    assert [message.content for message in messages] == ["Stable.", "q", "a", "Steps left: 3"]


def test_rendering_never_changes_the_history():
    """The dynamic part is rendered anew and not stored."""
    context = Context("r", list(HISTORY), steps_left=1)
    context.messages_for(Plain())
    assert context.messages == HISTORY


def test_no_prompt_no_system_message():
    """An agent without a prompt adds nothing."""
    assert Context("r", HISTORY).messages_for(Silent()) == tuple(HISTORY)


def test_typed_output_extends_the_prefix():
    """A typed answer adds its schema to the system message."""
    system = Context("r").messages_for(Structured())[0]
    assert system.role == "system" and "schema" in system.content


def test_a_new_context_gets_a_run_id():
    """Two contexts are two runs."""
    assert Context().run_id != Context().run_id

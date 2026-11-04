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


def test_old_results_and_long_inputs_become_short_forms_and_the_prefix_holds():
    """A design lead run of eight calls with 35k-character results: call 8 is at most 1.5x call 1.

    The input bound holds across the run.
    """
    from geomind.context.compaction import estimate_tokens
    from geomind.tools.stored import outline, stored_form
    from geomind.types import ToolCall

    big = {"plant": {"modules": [{"name": f"m{n}", "text": "t" * 300} for n in range(110)]}}
    messages = [Message(role="user", content="design")]
    stored = {}
    sizes = []
    for step in range(8):
        call = ToolCall(id=f"c{step}", name="read_plant", input={"design": "x" * 3000})
        messages.append(Message(role="assistant", tool_calls=(call,)))
        messages.append(Message(role="tool", content=str(big), tool_call_id=call.id))
        stored[call.id] = str(stored_form(big, f"result-{step}"))
        rendered = Context("r", messages, steps_left=1, stored=stored).messages_for(Plain())
        sizes.append(estimate_tokens(rendered))
    base = estimate_tokens(Context("r", messages[:1]).messages_for(Plain()))
    assert sizes[0] > 8000 and sizes[7] <= 1.5 * sizes[0]
    assert base < 100 and "result-0" in str(
        Context("r", messages, stored=stored)._history()[2].content
    )
    assert len(outline(big)) <= 601


def test_a_result_is_whole_in_the_step_after_its_call():
    """Only results before the last assistant message are replaced."""
    from geomind.types import ToolCall

    call = ToolCall(id="c", name="t", input={})
    messages = [
        Message(role="user", content="q"),
        Message(role="assistant", tool_calls=(call,)),
        Message(role="tool", content="WHOLE", tool_call_id="c"),
    ]
    history = Context("r", messages, stored={"c": "SHORT"})._history()
    assert history[2].content == "WHOLE"
    messages.append(Message(role="assistant", content="next"))
    assert Context("r", messages, stored={"c": "SHORT"})._history()[2].content == "SHORT"

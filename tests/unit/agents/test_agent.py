"""Declarations, listings and one agent call."""

import pydantic
import pytest

from geomind import agents, runtime
from geomind.agents import Agent, AgentResult, Model, Output
from geomind.engine import Context
from geomind.errors import DeclarationError, OutputError, RunError, UnknownNameError
from geomind.prompts import Prompt
from geomind.tools import ask_user, finish
from geomind.types import Action, Completion, Deny, Message, Usage
from tests.fixtures.sessions import StubSession


class Child(Agent):
    """A child."""

    def __init__(self):
        """Declare one tool."""
        super().__init__()

        # Tools
        self.finish = finish


class Parent(Agent):
    """A parent agent.

    More detail.
    """

    def __init__(self):
        """Declare one of each."""
        super().__init__()

        # Agents
        self.child = Child()

        # Prompt
        self.prompt = Prompt.text("Be brief.")

        # Tools
        self.ask = ask_user

        # Output
        self.output = Output(str)

        # Model
        self.model = Model("a/b", temperature=0.5, fallbacks=("c/d",))


class Stub:
    """A context with fixed messages."""

    def __init__(self, session):
        """Belong to a stand-in run."""
        self.session = session

    def messages_for(self, agent):
        """Return one message."""
        return (Message(role="user", content="hi"),)


class Answer(pydantic.BaseModel):
    """A typed answer."""

    value: int


def test_declarations_register_in_order():
    """Tools, children and slots land where they belong, tools under their attribute name."""
    parent = Parent()
    assert list(parent.tools()) == ["ask"] and parent.ask.name == "ask"
    assert [child.name for child in parent.children()] == ["child"]
    assert parent.prompt.render() == "Be brief."
    assert parent.model.name == "a/b"
    assert ask_user.name == "ask_user"


def test_paths_are_dotted_from_the_root():
    """Listings show the whole tree."""
    parent = Parent()
    assert parent.child.path == "parent.child"
    assert list(parent.named_agents()) == ["parent", "parent.child"]
    assert list(parent.tools(recurse=True)) == ["ask", "child.finish"]


def test_help_shows_the_declarations():
    """Help reads the first paragraph and the declarations."""
    text = Parent.help()
    assert text.startswith("A parent agent.") and "More detail" not in text
    assert "Tools: ask" in text and "Model: a/b" in text


def test_declaring_before_super_init_raises():
    """The registry does not exist yet."""

    class Early(Agent):
        def __init__(self):
            self.finish = finish
            super().__init__()

    with pytest.raises(DeclarationError, match="before super"):
        Early()


def test_a_declaration_after_init_registers():
    """Assignment is recognised at any time, as on a gemini module."""
    parent = Parent()
    parent.finish = finish
    assert list(parent.tools()) == ["ask", "finish"]


def test_duplicate_name_raises():
    """A name is declared once."""

    class Twice(Agent):
        def __init__(self):
            super().__init__()
            self.finish = finish
            self.finish = ask_user

    with pytest.raises(DeclarationError, match="already taken"):
        Twice()


def test_method_names_are_taken():
    """A declaration cannot hide a method."""

    class Hiding(Agent):
        def __init__(self):
            super().__init__()
            self.forward = finish

    with pytest.raises(DeclarationError, match="already taken"):
        Hiding()


def test_unknown_value_suggests_a_name():
    """A misspelled slot gets a close match."""

    class Typo(Agent):
        def __init__(self):
            super().__init__()
            self.promt = Prompt.text("x")

    with pytest.raises(DeclarationError, match="did you mean 'prompt'"):
        Typo()


def test_slot_takes_only_its_type():
    """A tool cannot be the model."""

    class Wrong(Agent):
        def __init__(self):
            super().__init__()
            self.model = finish

    with pytest.raises(DeclarationError, match="expected"):
        Wrong()


def test_a_model_comes_from_its_role_setting_with_no_default():
    """A role's setting names its model; with none set there is no model to fall back to."""
    with runtime.settings(designlead_model="x/y"):
        assert Model(setting="designlead_model").resolved_name() == "x/y"
    with runtime.settings(designlead_model=None):
        assert Model(setting="designlead_model").resolved_name() is None
    assert Model().resolved_name() is None
    assert Model("a", max_tokens=5).settings() == {"temperature": 0, "max_tokens": 5}


def test_text_output_refuses_other_answers():
    """A text answer is text."""
    assert Output().validate("hi") == "hi"
    with pytest.raises(OutputError, match="expected text"):
        Output().validate({"a": 1})


def test_typed_output_validates_json_and_objects():
    """The answer of ``finish`` or of the last message fits the model."""
    output = Output(Answer)
    assert output.validate('{"value": 1}') == {"value": 1}
    assert output.validate({"value": 2}) == {"value": 2}
    assert "value" in output.instructions()
    with pytest.raises(OutputError, match="Answer"):
        output.validate("not json")


async def test_complete_outside_a_run_raises():
    """There is no provider outside a run."""
    with pytest.raises(RunError, match="inside Engine.run"):
        await Parent().complete(Context(), [])


async def test_call_returns_the_action_messages_and_usage():
    """Hooks pass, ``forward`` asks the model and ``__call__`` builds the result."""
    session = StubSession()
    session.completion = Completion(text="ok", usage=Usage(input_tokens=3))
    result = await Parent()(Stub(session))
    assert isinstance(result, AgentResult)
    assert result.action == Action(text="ok")
    assert result.usage.input_tokens == 3 and result.messages[0].content == "hi"


async def test_call_stops_at_a_hook_decision():
    """A decision means ``forward`` never runs."""
    session = StubSession()
    session.decision = Deny(reason="budget")
    result = await Parent()(Stub(session))
    assert result.action is None and result.decision == session.decision


async def test_rule_based_forward_needs_no_model():
    """A step can be plain code."""

    class Rule(Agent):
        async def forward(self, context):
            return Action(text="fixed")

    assert (await Rule()(Stub(StubSession()))).action.text == "fixed"


def test_a_shipped_agent_is_found_by_name():
    """Skeletons too, so each can be tried as soon as it is filled."""
    assert type(agents.named("analysis_lead")) is agents.AnalysisLead
    assert type(agents.named("case_lead")) is agents.CaseLead
    assert type(agents.named("design_lead")) is agents.DesignLead
    assert type(agents.named("reviewer")) is agents.Reviewer


def test_an_unknown_agent_name_gets_a_close_match():
    """A typo in ``--agent`` says what was meant."""
    with pytest.raises(UnknownNameError, match="did you mean 'analysis_lead'"):
        agents.named("analist")


def test_an_empty_text_is_no_answer():
    """#46: the energy engineer ended with ''; the model is asked for its answer instead."""
    with pytest.raises(OutputError, match="expected the answer as text"):
        Output().validate("  ")

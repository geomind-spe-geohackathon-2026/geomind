"""The ``sourced`` criterion: every number an agent writes is one it read (#64)."""

from evals.run import Outcome, _read
from evals.tasks_format import SourcedCriterion
from geomind.types import Message

CRITERION = SourcedCriterion(kind="sourced", small=12)


def outcome(answer, read, questions=()):
    """Return an outcome with an answer, questions and the text the agent read."""
    return Outcome(name="t", answer=answer, questions=list(questions), read=read)


def test_numbers_the_agent_read_pass():
    """Values from a file, written with a thousands separator or not, are sourced."""
    read = "density 1,030 kg/m3 at 2500 m; supply 20 degC"
    assert CRITERION.problem(outcome("density 1030 kg/m3 at 2,500 m, supply 20 degC", read)) is None


def test_a_computed_number_in_a_question_fails():
    """A dew point the agent worked out itself is named."""
    problem = CRITERION.problem(
        outcome("", "room 26 degC, 50 % RH, return 14 degC", ["below the dew point 14.6 degC?"])
    )
    assert problem == "sourced: numbers no message holds [14.6]"


def test_small_whole_numbers_count_things():
    """Up to ``small``, a whole number numbers a list or counts questions."""
    assert CRITERION.problem(outcome("3 flaws: (1) a, (2) b, (12) c", "")) is None
    assert CRITERION.problem(outcome("13 flaws", "")) == "sourced: numbers no message holds [13.0]"


class Completed:
    """A stand-in for an ``llm.completed`` event."""

    type = "llm.completed"

    def __init__(self, *messages):
        """Keep the messages the model was sent."""
        self.messages = messages


def test_the_agent_s_own_messages_and_state_are_not_read():
    """What the agent wrote, in its turns or its problem state, is no source of a number."""
    text = _read(
        [
            Completed(
                Message(role="system", content="Problem state, version 2\nQ1: dew point 14.6"),
                Message(role="assistant", content="the dew point is 14.6"),
                Message(role="tool", content="room 26 degC"),
            )
        ]
    )
    assert "14.6" not in text and "26 degC" in text


def test_a_search_must_come_before_the_first_question():
    """The ``before`` criterion: the knowledge base is searched before the user is asked."""
    from evals.tasks_format import BeforeCriterion

    rule = BeforeCriterion(kind="before", tool="search_rag", then="ask_user")
    searched = Outcome(name="t", tools=["read_rag", "search_rag", "ask_user"])
    asked = Outcome(name="t", tools=["read_rag", "ask_user", "search_rag"])
    assert rule.problem(searched) is None
    assert rule.problem(Outcome(name="t", tools=["read_rag"])) is None
    assert rule.problem(asked).startswith("before: no search_rag before the first ask_user")


def test_names_and_list_markers_are_no_numbers():
    """``A14``, ``CO2`` and a list's ``13.`` are no values the agent states."""
    answer = "13. assumption A14 holds CO2 and CH4\n14) done"
    assert CRITERION.problem(outcome(answer, "")) is None


def test_a_number_after_a_line_break_of_a_json_result_is_read():
    r"""A tool's result reaches the model as JSON: ``\n3.1`` holds 3.1, not the name n3.1."""
    read = '{"text": "Fixed inputs\\n3.1  Geothermal reservoir"}'
    assert CRITERION.problem(outcome("section 3.1 says", read)) is None


def test_a_shortened_read_and_a_space_separator_are_sourced():
    """Track B: 34.6364 written as 34.64, and 111667.7 written as ``111 667.7``."""
    read = "flow 34.6364 m3/h, energy 111667.7 MWh"
    assert CRITERION.problem(outcome("flow 34.64 m3/h, energy 111 667.7 MWh", read)) is None
    assert CRITERION.problem(outcome("dew point 14.6", read)) is not None


def test_a_number_criterion_reads_a_thousands_separator():
    """Track C: ``111,667.68 MWh`` is one number, not 111 and 667.68."""
    from evals.tasks_format import NumberCriterion

    rule = NumberCriterion(kind="number", value=111667.68, tolerance=0.5, unit="MWh")
    assert rule.problem(outcome("heat 111,667.68 MWh", "")) is None
    assert rule.problem(outcome("heat 111 667.7 MWh", "")) is None


def test_the_case_line_of_the_problem_state_is_read():
    """Track C (#86): the case's span, set by ``set_case``, is no number the agent wrote."""
    state = "Problem state, version 3\nCase: time 2027-01-01 to 2028-01-01\nQ1: 14.6"
    text = _read([Completed(Message(role="system", content=state))])
    assert "2028-01-01" in text and "14.6" not in text

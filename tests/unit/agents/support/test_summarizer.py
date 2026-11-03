"""The agent that writes summaries."""

from geomind import runtime
from geomind.agents import Summarizer


def test_it_has_no_tools_and_a_cheap_model():
    """A summary needs neither."""
    agent = Summarizer()
    assert agent.tools() == {}
    assert agent.model.resolved_name() == runtime.get("summarizer_model")


def test_its_model_is_a_setting():
    """The role setting chooses it."""
    with runtime.settings(summarizer_model="fake/cheap"):
        assert Summarizer().model.resolved_name() == "fake/cheap"


def test_it_keeps_numbers_sources_and_open_questions_as_written():
    """A handover summary of the case lead kept every value; nothing rounded or converted."""
    from geomind.agents import Summarizer

    text = " ".join(Summarizer().prompt.content.split())
    assert "never round, convert, add or shorten one" in text
    assert "every open question or flaw" in text and "Don't: `Reservoir about 2.5 km deep.`" in text

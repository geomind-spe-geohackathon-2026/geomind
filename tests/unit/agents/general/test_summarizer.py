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

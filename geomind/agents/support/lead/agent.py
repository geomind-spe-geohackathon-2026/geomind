"""The agent that takes the other leads' support requests to its team."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.support.curator.agent import Curator
from geomind.agents.support.summarizer.agent import Summarizer
from geomind.prompts import Prompt
from geomind.tools import Delegate

MEMBER_TOKENS = 1500
"""The most tokens of a member's answer the support lead reads back."""


class SupportLead(Agent):
    """Take support requests from the other leads, route each to a member, check the result.

    NOTE: its members are the ``Summarizer`` (a summary of a text it is given) and the
    ``Curator`` (the run's lessons into experience). It checks a member's answer against the
    request before it goes back, and sends it back once with what is wrong.
    """

    def __init__(self):
        """Declare the prompt, the members and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("support/lead")

        # Tools
        self.summarizer = Delegate(Summarizer(), max_summary_tokens=MEMBER_TOKENS)
        self.curator = Delegate(Curator(), max_summary_tokens=MEMBER_TOKENS)
        self.read_stored = tools.read_stored
        self.finish = tools.finish

        # Model
        self.model = Model(setting="supportlead_model", temperature=0)

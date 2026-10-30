"""The agent that prices a proposal: a skeleton."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


class Economist(Agent):
    """Compute the cost and the CO2 of a proposal.

    NOTE: the structure is fixed now, so another person can fill the prompt, tools and tasks without
    changing the layout.
    """

    def __init__(self):
        """Declare the prompt, the tools that exist and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("economist")

        # Tools
        self.read_result = tools.read_result
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.finish = tools.finish

        # Model
        self.model = Model(setting="economist_model", temperature=0)

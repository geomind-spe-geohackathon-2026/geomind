"""The agent that writes the answer: a skeleton."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


class Explainer(Agent):
    """Write the answer for the user from the problem state and the results.

    NOTE: the structure is fixed now, so another person can fill the prompt, tools and tasks without
    changing the layout.
    """

    def __init__(self):
        """Declare the prompt, the tools that exist and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("explainer")

        # Tools
        self.read_result = tools.read_result
        self.finish = tools.finish

        # Model
        self.model = Model(setting="explainer_model", temperature=0)

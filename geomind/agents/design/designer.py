"""The agent that proposes configurations: a skeleton."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


class Designer(Agent):
    """Propose configurations and sizes that meet the requirements of the problem state.

    NOTE: the structure is fixed now, so another person can fill the prompt, tools and tasks without
    changing the layout.
    """

    def __init__(self):
        """Declare the prompt, the tools that exist and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("designer")

        # Tools
        self.read_result = tools.read_result
        self.search_documents = tools.search_documents
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="designer_model", temperature=0)

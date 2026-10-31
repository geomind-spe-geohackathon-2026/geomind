"""The agent that proposes configurations and sizes."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


class Designer(Agent):
    """Propose design families, then build, simulate and check one design that meets the brief.

    NOTE: it may check its own design with ``check_results`` before it hands over, which saves a
    round; the loop still verifies every design again, and the ``Verified`` hook once more.
    """

    def __init__(self):
        """Declare the prompt, the gemini tools, the state, questions, the answer and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("designer")

        # Tools
        self.list_plants = tools.gemini.list_plants
        self.read_plant = tools.gemini.read_plant
        self.list_modules = tools.gemini.list_modules
        self.describe_module = tools.gemini.describe_module
        self.evaluate_module = tools.gemini.evaluate_module
        self.build_plant = tools.gemini.build_plant
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.simulate = tools.gemini.simulate
        self.read_result = tools.read_result
        self.check_results = tools.gemini.check_results
        self.search_documents = tools.search_documents
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="designer_model", temperature=0)

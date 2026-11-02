"""The agent that proposes configurations and sizes."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


class Designer(Agent):
    """Size a plant for the case, simulate and check it, then optimise it and hand it over.

    NOTE: it checks its own designs with ``check_results`` and optimises directly: the search
    counts a trial as feasible only when gemini's verdict says so, so no ``Verifier`` round comes
    before it. With several buildable families it compares them in one ``run_study``. The
    ``Verifier`` checks the final design once.
    """

    def __init__(self):
        """Declare the prompt, the gemini tools, the state, questions, the answer and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("designer")

        # Tools
        self.read_case = tools.gemini.read_case
        self.set_case = tools.gemini.set_case
        self.save_profile = tools.gemini.save_profile
        self.list_plants = tools.gemini.list_plants
        self.read_plant = tools.gemini.read_plant
        self.list_modules = tools.gemini.list_modules
        self.describe_module = tools.gemini.describe_module
        self.evaluate_module = tools.gemini.evaluate_module
        self.build_plant = tools.gemini.build_plant
        self.set_ranges = tools.gemini.set_ranges
        self.size_plant = tools.gemini.size_plant
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.simulate = tools.gemini.simulate
        self.read_result = tools.read_result
        self.check_results = tools.gemini.check_results
        self.optimize = tools.gemini.optimize
        self.run_study = tools.gemini.run_study
        self.write_module = tools.gemini.write_module
        self.test_module = tools.gemini.test_module
        self.search_documents = tools.search_documents
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="designer_model", temperature=0)

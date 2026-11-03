"""The agent that proposes configurations and sizes."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt
from geomind.tools.gemini.skeleton import trees


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
        self.prompt = Prompt("designer", appendix=trees("plant", "study"))

        # Tools
        self.read_case = tools.gemini.read_case
        self.list_plants = tools.gemini.list_plants
        self.read_plant = tools.gemini.read_plant
        self.list_modules = tools.gemini.list_modules
        self.describe_module = tools.gemini.describe_module
        self.evaluate_module = tools.gemini.evaluate_module
        self.build_plant = tools.gemini.build_plant
        self.patch_plant = tools.gemini.patch_plant
        self.set_ranges = tools.gemini.set_ranges
        self.size_plant = tools.gemini.size_plant
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.simulate = tools.gemini.simulate
        self.read_result = tools.read_result
        self.list_studies = tools.gemini.list_studies
        self.read_study = tools.gemini.read_study
        self.check_results = tools.gemini.check_results
        self.optimize = tools.gemini.optimize
        self.run_study = tools.gemini.run_study
        self.write_module = tools.gemini.write_module
        self.test_module = tools.gemini.test_module
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.write_memory = tools.write_memory
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="designer_model", temperature=0)


class FamilyDesigner(Designer):
    """Design one family of a comparison, beside the runs of the others.

    NOTE: the ``CompareLoop`` sets the case first, and a designer never sets it, so this run asks
    nobody either: it records why it could not go on instead.
    """

    def __init__(self):
        """Declare the designer's tools, without the one that asks the user."""
        super().__init__()
        del self._tools["ask_user"]

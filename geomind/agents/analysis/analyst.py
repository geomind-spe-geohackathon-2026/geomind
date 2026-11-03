"""The sample agent: the reference for how an agent is built."""

from geomind import tools
from geomind.agents.agent import Agent, Model, Output
from geomind.prompts import Prompt


class Analyst(Agent):
    """Answer questions about a plant with numbers that come from gemini through tools."""

    def __init__(self):
        """Declare the prompt, the gemini tools and the rest, a text answer and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("analyst")

        # Tools
        self.list_files = tools.list_files
        self.read_document = tools.read_document
        self.read_case = tools.gemini.read_case
        self.set_case = tools.gemini.set_case
        self.list_modules = tools.gemini.list_modules
        self.describe_module = tools.gemini.describe_module
        self.evaluate_module = tools.gemini.evaluate_module
        self.list_plants = tools.gemini.list_plants
        self.read_plant = tools.gemini.read_plant
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.save_profile = tools.gemini.save_profile
        self.simulate = tools.gemini.simulate
        self.read_result = tools.read_result
        self.list_studies = tools.gemini.list_studies
        self.read_study = tools.gemini.read_study
        self.compute_kpis = tools.gemini.compute_kpis
        self.write_module = tools.gemini.write_module
        self.test_module = tools.gemini.test_module
        self.search_documents = tools.search_documents
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.read_stored = tools.read_stored
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Output
        self.output = Output(str)

        # Model
        self.model = Model(setting="analyst_model", temperature=0)

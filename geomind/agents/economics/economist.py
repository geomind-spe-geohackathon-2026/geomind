"""The agent that costs a design."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt
from geomind.tools.gemini.skeleton import trees


class Economist(Agent):
    """Cost a verified design with gemini, compare it and test its uncertainty; record the costs."""

    def __init__(self):
        """Declare the prompt, the tools that cost, compare and sample, and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("economist", appendix=trees("study"))

        # Tools
        self.compute_kpis = tools.gemini.compute_kpis
        self.estimate_costs = tools.gemini.estimate_costs
        self.compare = tools.gemini.compare
        self.run_study = tools.gemini.run_study
        self.sample_uncertainty = tools.gemini.sample_uncertainty
        self.sensitivity = tools.gemini.sensitivity
        self.read_result = tools.read_result
        self.list_studies = tools.gemini.list_studies
        self.read_study = tools.gemini.read_study
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.write_memory = tools.write_memory
        self.finish = tools.finish

        # Model
        self.model = Model(setting="economist_model", temperature=0)

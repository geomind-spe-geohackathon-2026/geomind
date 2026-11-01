"""The agent that explains a design."""

from geomind import tools
from geomind.agents.agent import Agent, Model, Output
from geomind.prompts import Prompt


class Explainer(Agent):
    """Explain the verified design: capacities, schematic, costs, checks and each major decision."""

    def __init__(self):
        """Declare the prompt, the tools that read the design and its results, and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("explainer")

        # Tools
        self.read_plant = tools.gemini.read_plant
        self.read_result = tools.read_result
        self.compute_kpis = tools.gemini.compute_kpis
        self.estimate_costs = tools.gemini.estimate_costs
        self.search_documents = tools.search_documents
        self.finish = tools.finish

        # Output
        self.output = Output(str)

        # Model
        self.model = Model(setting="explainer_model", temperature=0)

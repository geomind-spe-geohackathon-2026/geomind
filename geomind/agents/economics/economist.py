"""The agent that costs a design."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


class Economist(Agent):
    """Cost a verified design with gemini's economics; record the costs and their assumptions."""

    def __init__(self):
        """Declare the prompt, the tools that read the run and cost it, and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("economist")

        # Tools
        self.read_plant = tools.gemini.read_plant
        self.simulate = tools.gemini.simulate
        self.compute_kpis = tools.gemini.compute_kpis
        self.estimate_costs = tools.gemini.estimate_costs
        self.read_result = tools.read_result
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.finish = tools.finish

        # Model
        self.model = Model(setting="economist_model", temperature=0)

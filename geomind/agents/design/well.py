"""The well engineer of the design team."""

from geomind.agents.agent import Agent, Model, Output
from geomind.agents.design.proposal import Proposal, proposer_tools
from geomind.agents.design.reference import engineer_appendix
from geomind.prompts import Prompt


class WellEngineer(Agent):
    """Fill the wells: depth, well path and diameters, the pump and its setting depth.

    NOTE: it owns the well paths, the risers, the injectors and the pumps in them.
    It proposes changes to its modules from the lead's brief and writes no plant (only the design
    lead does). It asks nobody: what it cannot settle goes back to the design lead.
    """

    discipline = "well"

    def __init__(self):
        """Declare the prompt with the plant keys, the Knowledge tools, the output and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("design/well", appendix=engineer_appendix("well"))

        # Tools
        proposer_tools(self)

        # Output
        self.output = Output(Proposal)

        # Model
        self.model = Model(setting="wellengineer_model", temperature=0)

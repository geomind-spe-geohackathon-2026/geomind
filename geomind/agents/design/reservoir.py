"""The reservoir engineer of the design team."""

from geomind.agents.agent import Agent, Model, Output
from geomind.agents.design.proposal import Proposal, proposer_tools
from geomind.agents.design.reference import engineer_appendix
from geomind.prompts import Prompt


class ReservoirEngineer(Agent):
    """Fill the reservoir side: doublets, spacing, flow, reservoir cooling and the brine limits.

    NOTE: it owns the reservoir, the sink, the drainage and the degasser. It proposes changes to
    its modules from the lead's brief and writes no plant (only the design lead does). It asks
    nobody: what it cannot settle goes back to the design lead.
    """

    discipline = "reservoir"

    def __init__(self):
        """Declare the prompt with the plant keys, the Knowledge tools, the output and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("design/reservoir", appendix=engineer_appendix("reservoir"))

        # Tools
        # Only the design lead reads and writes the project's plants: the brief holds the plant
        # text, the case values and the missing paths, and the engineer returns proposed changes
        # (IMP-025, QA-145).
        proposer_tools(self)

        # Output
        self.output = Output(Proposal)

        # Model
        self.model = Model(setting="reservoirengineer_model", temperature=0)

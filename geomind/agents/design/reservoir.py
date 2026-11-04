"""The reservoir engineer of the design team."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.design.reference import engineer_appendix
from geomind.prompts import Prompt


class ReservoirEngineer(Agent):
    """Fill the reservoir side: doublets, spacing, flow, reservoir cooling and the brine limits.

    NOTE: it owns the reservoir, the sink, the drainage and the degasser. ``patch_plant``
    refuses a change to a part another discipline owns (``design.owners``). It asks nobody: what
    it cannot settle goes back to the design lead.
    """

    discipline = "reservoir"

    def __init__(self):
        """Declare the prompt with the plant keys, the plant tools, the memory and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("design/reservoir", appendix=engineer_appendix("reservoir"))

        # Tools
        self.read_case = tools.gemini.read_case.kept()
        self.read_plant = tools.gemini.read_plant.kept()
        self.describe_module = tools.gemini.describe_module.kept()
        self.evaluate_module = tools.gemini.evaluate_module
        self.read_profile = tools.gemini.read_profile
        self.patch_plant = tools.gemini.patch_plant
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.search_rag = tools.search_rag
        self.finish = tools.finish

        # Model
        self.model = Model(setting="reservoirengineer_model", temperature=0)

"""The well engineer of the design team."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.design.reference import engineer_appendix
from geomind.prompts import Prompt


class WellEngineer(Agent):
    """Fill the wells: depth, well path and diameters, the pump and its setting depth.

    NOTE: it owns the well paths, the risers, the injectors and the pumps in them.
    ``patch_plant`` refuses a change to a part another discipline owns (``design.owners``). It
    asks nobody: what it cannot settle goes back to the design lead.
    """

    discipline = "well"

    def __init__(self):
        """Declare the prompt with the plant keys, the plant tools, the memory and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("design/well", appendix=engineer_appendix("well"))

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
        self.model = Model(setting="wellengineer_model", temperature=0)

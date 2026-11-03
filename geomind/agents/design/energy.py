"""The energy engineer of the design team."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt
from geomind.tools.gemini.skeleton import trees


class EnergySystemsEngineer(Agent):
    """Fill the surface energy system: heat pump, chiller, boiler, storage, exchangers and network.

    NOTE: it owns the machines and the pipes above ground. ``patch_plant`` refuses a change to a
    part another discipline owns (``design.owners``). It asks nobody: what it cannot settle goes
    back to the design lead.
    """

    discipline = "energy"

    def __init__(self):
        """Declare the prompt with the plant keys, the plant tools, the memory and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("design/energy", appendix=trees("plant"))

        # Tools
        self.read_case = tools.gemini.read_case
        self.read_plant = tools.gemini.read_plant
        self.describe_module = tools.gemini.describe_module
        self.evaluate_module = tools.gemini.evaluate_module
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.patch_plant = tools.gemini.patch_plant
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.write_memory = tools.write_memory
        self.finish = tools.finish

        # Model
        self.model = Model(setting="energysystemsengineer_model", temperature=0)

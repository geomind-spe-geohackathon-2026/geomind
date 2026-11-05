"""The process engineer of the design team."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.design.reference import process_appendix
from geomind.prompts import Prompt


class ProcessEngineer(Agent):
    """Choose the modules for the case's services, a reason for each, and assign their owners.

    NOTE: it chooses the topology and the modules and records who owns each part.
    ``patch_plant`` refuses a change to a part another discipline owns (``design.owners``). It
    asks nobody: what it cannot settle goes back to the design lead.
    """

    discipline = "process"

    def __init__(self):
        """Declare the prompt with the plant keys, the plant tools, the memory and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("design/process", appendix=process_appendix)

        # Tools
        self.read_case = tools.gemini.read_case.kept()
        self.list_plants = tools.gemini.list_plants
        self.read_plant = tools.gemini.read_plant.kept()
        self.list_modules = tools.gemini.list_modules
        self.describe_module = tools.gemini.describe_module.kept()
        self.list_starts = tools.gemini.list_starts
        self.start_plant = tools.gemini.start_plant
        self.build_plant = tools.gemini.build_plant
        self.patch_plant = tools.gemini.patch_plant
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.calculate = tools.calculate
        self.run_python = tools.run_python
        self.web_search = tools.web_search
        self.read_web_page = tools.read_web_page
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.search_rag = tools.search_rag
        self.finish = tools.finish

        # Model
        self.model = Model(setting="processengineer_model", temperature=0)

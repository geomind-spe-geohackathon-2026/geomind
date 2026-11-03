"""The agent that proposes configurations and sizes."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.design.energy.agent import EnergySystemsEngineer
from geomind.agents.design.integration.agent import IntegrationEngineer
from geomind.agents.design.process.agent import ProcessEngineer
from geomind.agents.design.reservoir.agent import ReservoirEngineer
from geomind.agents.design.well.agent import WellEngineer
from geomind.agents.support.lead.agent import SupportLead
from geomind.prompts import Prompt
from geomind.tools import Delegate
from geomind.tools.delegate import Team
from geomind.tools.gemini.skeleton import trees

SIDE_BY_SIDE = ("reservoir_engineer", "well_engineer", "energy_systems_engineer")
"""The engineers who fill their parts at the same time, from one connected design."""
ENGINEER_TOKENS = 2000
"""The most tokens of an engineer's answer the design lead reads back."""
LIMIT = "design_concurrency"
"""The setting that bounds how many engineers fill their parts side by side."""
SUPPORT_TOKENS = 1500
"""The most tokens of the support lead's answer a lead reads back."""


def beside(agent):
    """Return the delegate of an engineer that fills its part beside others, within the limit."""
    return Delegate(agent, max_summary_tokens=ENGINEER_TOKENS, runs_beside=True, limit=LIMIT)


def team():
    """Return the design team as tools by name, in the order the lead calls them."""
    members = {
        "process_engineer": Delegate(ProcessEngineer(), max_summary_tokens=ENGINEER_TOKENS),
        "integration_engineer": Delegate(IntegrationEngineer(), max_summary_tokens=ENGINEER_TOKENS),
        "reservoir_engineer": beside(ReservoirEngineer()),
        "well_engineer": beside(WellEngineer()),
        "energy_systems_engineer": beside(EnergySystemsEngineer()),
    }
    return {**members, "fill_parts": side_by_side(members)}


def side_by_side(members):
    """Return the tool that has the side-by-side engineers fill their parts at the same time."""
    return Team(
        "fill_parts",
        "Have the reservoir, well and energy systems engineers fill their parts side by side: "
        "one brief each, by tool name; each answer, or its error, comes back by name.",
        {name: members[name] for name in SIDE_BY_SIDE},
    )


class DesignLead(Agent):
    """Lead the design team, review the assembled plant, then size, check and optimise it.

    NOTE: the process engineer chooses the modules and their owners, the integration engineer
    connects them, and the reservoir, well and energy systems engineers fill their parts side by
    side (at most ``design_concurrency`` at once), each patching only its own; the design lead
    merges, reviews and sends each problem back to its owner. It checks its own designs with
    ``check_results`` and optimises directly: the search counts a trial as feasible only when
    gemini's verdict says so, so no ``Reviewer`` round comes before it. With several buildable
    families it compares them in one ``run_study``. The ``Reviewer`` checks the final design once.
    """

    def __init__(self):
        """Declare the prompt, the team, the gemini tools, the state, questions and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("design/lead", appendix=trees("plant", "study"))

        # Tools
        for name, delegate in team().items():
            setattr(self, name, delegate)
        self.merge_designs = tools.gemini.merge_designs
        self.read_case = tools.gemini.read_case
        self.list_plants = tools.gemini.list_plants
        self.read_plant = tools.gemini.read_plant
        self.list_modules = tools.gemini.list_modules
        self.describe_module = tools.gemini.describe_module
        self.evaluate_module = tools.gemini.evaluate_module
        self.build_plant = tools.gemini.build_plant
        self.patch_plant = tools.gemini.patch_plant
        self.set_ranges = tools.gemini.set_ranges
        self.size_plant = tools.gemini.size_plant
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.simulate = tools.gemini.simulate
        self.read_result = tools.read_result
        self.list_studies = tools.gemini.list_studies
        self.read_study = tools.gemini.read_study
        self.check_results = tools.gemini.check_results
        self.optimize = tools.gemini.optimize
        self.run_study = tools.gemini.run_study
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.write_memory = tools.write_memory
        self.support_lead = Delegate(SupportLead(), max_summary_tokens=SUPPORT_TOKENS)
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="designlead_model", temperature=0)

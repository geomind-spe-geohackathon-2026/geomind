"""The agent that proposes configurations and sizes."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.design.energy import EnergySystemsEngineer
from geomind.agents.design.integration import IntegrationEngineer
from geomind.agents.design.process import ProcessEngineer
from geomind.agents.design.reservoir import ReservoirEngineer
from geomind.agents.design.well import WellEngineer
from geomind.agents.support.lead import SupportLead
from geomind.prompts import Prompt
from geomind.tools import Delegate
from geomind.tools.delegate import Team
from geomind.tools.gemini.skeleton import trees

GEMINI_TOOLS = (
    "merge_designs",
    "read_case",
    "list_plants",
    "read_plant",
    "list_modules",
    "describe_module",
    "evaluate_module",
    "build_plant",
    "patch_plant",
    "set_ranges",
    "size_plant",
    "list_profiles",
    "read_profile",
    "simulate",
    "read_result",
    "list_studies",
    "read_study",
    "check_results",
    "optimize",
    "evolve_structure",
    "run_study",
)
"""The gemini tools of the design lead, in the order it is offered them."""
SIDE_BY_SIDE = ("reservoir_engineer", "well_engineer", "energy_systems_engineer")
"""The engineers who fill their parts at the same time, from one connected design."""
ENGINEER_TOKENS = 2000
"""The most tokens of an engineer's answer the design lead reads back."""
STEPS = "engineer_max_steps"
"""The setting of an engineer's own step limit, at which it hands back what it has."""
LIMIT = "design_concurrency"
"""The setting that bounds how many engineers fill their parts side by side."""
SUPPORT_TOKENS = 1500
"""The most tokens of the support lead's answer a lead reads back."""


def engineer(agent):
    """Return the delegate of an engineer, with the engineers' own step limit."""
    return Delegate(agent, max_summary_tokens=ENGINEER_TOKENS, steps=STEPS)


def beside(agent):
    """Return the delegate of an engineer that fills its part beside others, within the limit."""
    return Delegate(
        agent, max_summary_tokens=ENGINEER_TOKENS, runs_beside=True, limit=LIMIT, steps=STEPS
    )


def team():
    """Return the design team as tools by name, in the order the lead calls them."""
    members = {
        "process_engineer": engineer(ProcessEngineer()),
        "integration_engineer": engineer(IntegrationEngineer()),
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
        for name in GEMINI_TOOLS:
            setattr(self, name, getattr(tools.gemini, name))
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.search_knowledge = tools.search_knowledge
        self.support_lead = Delegate(SupportLead(), max_summary_tokens=SUPPORT_TOKENS)
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="designlead_model", temperature=0)

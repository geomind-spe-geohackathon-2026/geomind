"""The agent that proposes configurations and sizes."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.design.energy import EnergySystemsEngineer
from geomind.agents.design.reservoir import ReservoirEngineer
from geomind.agents.design.well import WellEngineer
from geomind.agents.support.lead import SupportLead
from geomind.prompts import Prompt
from geomind.tools import Delegate
from geomind.tools.delegate import Team
from geomind.tools.gemini.skeleton import trees

GEMINI_TOOLS = (
    "merge_designs",
    "union_designs",
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
ENGINEER_TOKENS = 4000
"""The most tokens of an engineer's proposal the design lead reads back."""
STEPS = "engineer_max_steps"
"""The setting of an engineer's own step limit, at which it hands back what it has."""
LIMIT = "design_concurrency"
"""The setting that bounds how many engineers work side by side."""
SUPPORT_TOKENS = 1500
"""The most tokens of the support lead's answer a lead reads back."""


def beside(agent):
    """Return the delegate of an engineer that works beside others, within the limit."""
    return Delegate(
        agent, max_summary_tokens=ENGINEER_TOKENS, runs_beside=True, limit=LIMIT, steps=STEPS
    )


def team():
    """Return the design team as tools by name: the one team call of the engineers.

    Only the design lead reads and writes the project's plants (IMP-025): the engineers propose
    changes from the brief and the lead applies them in one ``patch_plant``. The single-engineer
    tools and the process and integration engineers are gone: the lead picks the plant class
    and its wiring from the handbook (``handbook-design.md`` chapter 0), and a brief to one
    engineer is a team call with one brief (QA-145: 27 hand patches in 70 minutes, no simulate).
    """
    members = {
        "reservoir_engineer": beside(ReservoirEngineer()),
        "well_engineer": beside(WellEngineer()),
        "energy_systems_engineer": beside(EnergySystemsEngineer()),
    }
    return {
        "fill_parts": Team(
            "fill_parts",
            "Run up to four engineers at once, each on its own module group: briefs is a list of "
            "{role, task} with role reservoir_engineer, well_engineer or energy_systems_engineer; "
            "each instance (Energy systems engineer I, II, ...) answers by its name with its "
            "proposed changes.",
            members,
        )
    }


class DesignLead(Agent):
    """Lead the design team, review the assembled plant, then size, check and optimise it.

    NOTE: the lead alone reads and writes the plant (IMP-025): it picks the family and the plant
    class, builds it once, splits the missing values among up to four engineers in one
    ``fill_parts`` call (at most ``design_concurrency`` at once), applies all their proposed
    changes in one ``patch_plant`` and simulates as soon as nothing is missing (QA-145). It checks its own designs with
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
        self.calculate = tools.calculate
        self.run_python = tools.run_python
        self.web_search = tools.web_search
        self.read_web_page = tools.read_web_page
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.search_rag = tools.search_rag
        self.read_rag = tools.read_rag
        self.support_lead = Delegate(SupportLead(), max_summary_tokens=SUPPORT_TOKENS)
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="designlead_model", temperature=0)

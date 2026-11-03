"""The agent that sets the case: demand, site, requirements and time, from the files."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.case.geoscientist import Geoscientist
from geomind.agents.support.lead import SupportLead
from geomind.prompts import Prompt
from geomind.tools import Delegate
from geomind.tools.gemini.skeleton import trees

FINDINGS_TOKENS = 8000
"""The most tokens of the geoscientist's findings the case lead reads back."""
SUPPORT_TOKENS = 1500
"""The most tokens of the support lead's answer a lead reads back."""


class CaseLead(Agent):
    """Set the case of a design from the project's files, with assumptions for what they lack.

    NOTE: the case lead owns the case and designs nothing; the design lead reads the case and never
    sets it. The design and compare loops run the case lead once before any design, and again only
    when a round reports that the case must change.
    """

    def __init__(self):
        """Declare the prompt, the geoscientist, the tools over files and the case, the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("case/lead", appendix=trees("case"))

        # Tools
        self.geoscientist = Delegate(Geoscientist(), max_summary_tokens=FINDINGS_TOKENS)
        self.list_files = tools.list_files
        self.rag_read = tools.rag_read
        self.rag_search = tools.rag_search
        self.read_case = tools.gemini.read_case
        self.set_case = tools.gemini.set_case
        self.save_profile = tools.gemini.save_profile
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.search_knowledge = tools.search_knowledge
        self.update_state = tools.update_state
        self.support_lead = Delegate(SupportLead(), max_summary_tokens=SUPPORT_TOKENS)
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="caselead_model", temperature=0)

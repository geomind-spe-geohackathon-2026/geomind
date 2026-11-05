"""The sample agent: the reference for how an agent is built."""

from geomind import tools
from geomind.agents.agent import Agent, Model, Output
from geomind.agents.analysis.economist import Economist
from geomind.agents.analysis.reference import analysis_reference
from geomind.agents.support.lead import SupportLead
from geomind.prompts import Prompt
from geomind.tools import Delegate

ECONOMIST_TOKENS = 2000
"""The most tokens of the economist's answer the analysis lead reads back."""
SUPPORT_TOKENS = 1500
"""The most tokens of the support lead's answer a lead reads back."""


class AnalysisLead(Agent):
    """Answer questions about a plant with numbers that come from gemini through tools."""

    def __init__(self):
        """Declare the prompt, the gemini tools and the rest, a text answer and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("analysis/lead", appendix=analysis_reference)

        # Tools
        self.economist = Delegate(Economist(), max_summary_tokens=ECONOMIST_TOKENS)
        self.list_files = tools.list_files
        self.read_rag = tools.read_rag
        self.read_case = tools.gemini.read_case
        self.set_case = tools.gemini.set_case
        self.list_modules = tools.gemini.list_modules
        self.describe_module = tools.gemini.describe_module
        self.evaluate_module = tools.gemini.evaluate_module
        self.list_plants = tools.gemini.list_plants
        self.read_plant = tools.gemini.read_plant
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.save_profile = tools.gemini.save_profile
        self.simulate = tools.gemini.simulate
        self.read_result = tools.read_result
        self.list_studies = tools.gemini.list_studies
        self.read_study = tools.gemini.read_study
        self.compute_kpis = tools.gemini.compute_kpis
        self.search_rag = tools.search_rag
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.calculate = tools.calculate
        self.run_python = tools.run_python
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.support_lead = Delegate(SupportLead(), max_summary_tokens=SUPPORT_TOKENS)
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Output
        self.output = Output(str)

        # Model
        self.model = Model(setting="analysislead_model", temperature=0)

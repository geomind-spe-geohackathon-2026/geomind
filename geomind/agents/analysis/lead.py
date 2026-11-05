"""The sample agent: the reference for how an agent is built."""

import re

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


RAW_IMPROVEMENT = re.compile(r"^\s*(?:[-*]\s*)?improvement:", re.IGNORECASE | re.MULTILINE)
"""A line of an answer that starts with the design loop's ``improvement:`` tag."""
TAGGED = "improvement tag in the answer"
"""The start of the analysis lead's one refusal of an answer to the user with the raw tag."""


def proposed(messages):
    """Return the answer the last assistant message proposes: its finish, else its text."""
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        for call in message.tool_calls:
            if call.name == "finish":
                return str((call.input or {}).get("answer", ""))
        return message.content or ""
    return ""


def raw_improvements(context):
    """Return the refusal of an answer to the user with ``improvement:`` lines, or ``None``.

    QA-300, QA-352: answers on costs, sensitivity and uncertainty ended with the design loop's
    raw tag. Only a run the user reads (no parent) is checked; a nested run hands its lines to
    the design lead, which reads the tag. Refused once.
    """
    state = getattr(context.session, "state", None)
    if getattr(state, "parent", None) is not None:
        return None
    messages = context.messages
    if any(TAGGED in (message.content or "") for message in messages):
        return None
    if not RAW_IMPROVEMENT.search(proposed(messages)):
        return None
    return (
        f"{TAGGED}: the user reads this answer, so write each improvement as a plain sentence "
        "in a short list headed 'What could improve it', never a line that starts with "
        "'improvement:'; then finish with the same answer otherwise"
    )


class AnalysisLead(Agent):
    """Answer questions about a plant with numbers that come from gemini through tools."""

    def __init__(self):
        """Declare the prompt, the gemini tools and the rest, a text answer and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("analysis/lead", appendix=analysis_reference)

        # Tools
        self.economist = Delegate(Economist(), max_summary_tokens=ECONOMIST_TOKENS)
        self._declare_gemini_tools()
        self._declare_shared_tools()

        # Output
        self.output = Output(str)

        # Model
        self.model = Model(setting="analysislead_model", temperature=0)

    def answer_problem(self, context):
        """Refuse once an answer to the user with the raw ``improvement:`` tag (QA-352)."""
        return raw_improvements(context)

    def _declare_gemini_tools(self):
        """Declare the tools over files, the case, the modules, plants, runs and studies."""
        self.list_files = tools.list_files
        self.read_rag = tools.read_rag
        self.read_case = tools.gemini.read_case
        self.set_case = tools.gemini.set_case
        self.ask_economics = tools.gemini.ask_economics
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

    def _declare_shared_tools(self):
        """Declare the knowledge, state, calculation, web, memory, support and question tools."""
        self.search_rag = tools.search_rag
        self.read_knowledge = tools.read_knowledge
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.calculate = tools.calculate
        self.run_python = tools.run_python
        self.web_search = tools.web_search
        self.read_web_page = tools.read_web_page
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.support_lead = Delegate(SupportLead(), max_summary_tokens=SUPPORT_TOKENS)
        self.ask_user = tools.ask_user
        self.finish = tools.finish

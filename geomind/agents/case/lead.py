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
NO_ECONOMICS = "economics not done"
"""The start of the case lead's one refusal of an answer without the economics step (#124)."""


def calls_of(messages, name):
    """Return the inputs of the calls of tool ``name`` in a run's messages, in order."""
    return [
        call.input
        for message in messages
        if message.role == "assistant"
        for call in message.tool_calls
        if call.name == name
    ]


def economics_missing(context):
    """Return the refusal of a case lead's answer that skipped the economics step, or ``None``.

    The step is required when this run set the case (a ``set_case`` call) and the stored case
    has no economics, unless the run asked the user about them (an ``ask_user`` naming
    ``economics``) or was refused once already. It holds in a run the project lead delegated
    too, where nemotron read the catalogue, set no economics and wrote its question as text.
    """
    case = context.problem.case
    messages = context.messages
    if not case or case.get("economics") or not calls_of(messages, "set_case"):
        return None
    if any(NO_ECONOMICS in (message.content or "") for message in messages):
        return None
    if any("economics" in str(item).lower() for item in calls_of(messages, "ask_user")):
        return None
    return (
        f"{NO_ECONOMICS}: the case is set and has no economics. Do step 5 of your workflow now: "
        "choose each key's rows of the cost catalogue (read knowledge/cost-sources.csv now if you "
        "did not), ask the ONE economics question with ask_user (options approve all, change "
        "some, stop), then set_case(economics={...}) with the approved values. Ask with "
        "ask_user, never in your answer's text; then finish"
    )


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
        self.prompt = Prompt("case/lead", appendix=trees("case_compact"))

        # Tools
        geoscientist = Delegate(Geoscientist(), max_summary_tokens=FINDINGS_TOKENS, once=True)
        geoscientist.keeps_result = "run"
        self.geoscientist = geoscientist
        self.list_files = tools.list_files
        self.read_rag = tools.read_rag
        self.search_rag = tools.search_rag
        self.read_case = tools.gemini.read_case
        self.describe_case = tools.gemini.describe_case
        self.set_case = tools.gemini.set_case
        self.save_profile = tools.gemini.save_profile
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.update_state = tools.update_state
        self.support_lead = Delegate(SupportLead(), max_summary_tokens=SUPPORT_TOKENS)
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="caselead_model", temperature=0)

    def answer_problem(self, context):
        """Refuse once an answer of a run that set the case without its economics (#124)."""
        return economics_missing(context)

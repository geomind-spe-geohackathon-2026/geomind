"""The agent that sets the case: demand, site, requirements and time, from the files."""

import ast

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.case.geoscientist import Geoscientist
from geomind.agents.support.lead import SupportLead
from geomind.prompts import Prompt
from geomind.tools import Delegate
from geomind.tools.delegate import Team
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
    if calls_of(messages, "ask_economics"):
        return None
    if any("economics" in str(item).lower() for item in calls_of(messages, "ask_user")):
        return None
    return (
        f"{NO_ECONOMICS}: the case is set and has no economics. Do step 5 of your workflow now: "
        "choose each key's rows of the cost catalogue (read knowledge/data-economics.csv now if you "
        "did not), then ask the ONE economics question with ask_economics, every key with its "
        "row id only, never its value or citation (discount_rate included); on approve all it sets "
        "them. "
        "Ask with the tool, never in your answer's text; then finish"
    )


QUESTION_TOOLS = ("ask_user", "ask_economics")
"""The tools of the case lead that ask the user."""
CHANGE_SOME = "change some"
"""The option of the case lead's questions after which the user must be asked for the values."""
NO_CHANGES = "changes not asked"
"""The start of the case lead's one refusal of an answer after ``change some`` with no follow-up."""


def last_reply(messages):
    """Return the text of the user's last answer to a question of this run, or ``None``.

    ``ask_economics`` gives back ``{"answer": text, ...}``; its ``answer`` is the text.
    """
    asked = {
        call.id
        for message in messages
        if message.role == "assistant"
        for call in message.tool_calls
        if call.name in QUESTION_TOOLS
    }
    replies = [m.content for m in messages if m.role == "tool" and m.tool_call_id in asked]
    if not replies:
        return None
    reply = replies[-1] or ""
    if reply.startswith("{"):
        try:
            parsed = ast.literal_eval(reply)
        except (ValueError, SyntaxError):
            return reply
        return parsed.get("answer", reply) if isinstance(parsed, dict) else reply
    return reply


def changes_not_asked(context):
    """Return the refusal of an answer after the user chose ``change some``, or ``None``.

    The run: the user answered ``change some`` and the case lead wrote its follow-up question as
    the text of an answer, so the user never gave the values. Once refused, it ends as it is.
    """
    messages = context.messages
    reply = last_reply(messages)
    if reply is None or reply.strip().lower() != CHANGE_SOME:
        return None
    if any(NO_CHANGES in (message.content or "") for message in messages):
        return None
    return (
        f"{NO_CHANGES}: the user chose 'change some'. Ask now with ask_user, without options, "
        "which values change and to what (each path with its new value and unit), never in your "
        "answer's text; set what they give, then go on"
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
        self.geoscientists = Team(
            "geoscientists",
            "Run several geoscientists at once, each on its own field group and files: briefs is "
            "a list of {role: 'geoscientist', task}; each instance (Geoscientist I, II, ...) "
            "answers by its name.",
            {"geoscientist": geoscientist},
        )
        self.list_files = tools.list_files
        self.read_rag = tools.read_rag
        self.search_rag = tools.search_rag
        self.read_case = tools.gemini.read_case
        self.describe_case = tools.gemini.describe_case
        self.set_case = tools.gemini.set_case
        self.ask_economics = tools.gemini.ask_economics
        self.save_profile = tools.gemini.save_profile
        self.list_profiles = tools.gemini.list_profiles
        self.read_profile = tools.gemini.read_profile
        self.read_stored = tools.read_stored
        self.read_skill = tools.read_skill
        self.calculate = tools.calculate
        self.web_search = tools.web_search
        self.read_web_page = tools.read_web_page
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.update_state = tools.update_state
        self.support_lead = Delegate(SupportLead(), max_summary_tokens=SUPPORT_TOKENS)
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="caselead_model", temperature=0)

    def answer_problem(self, context):
        """Refuse once an answer that skipped the values after ``change some``, or the economics."""
        return changes_not_asked(context) or economics_missing(context)

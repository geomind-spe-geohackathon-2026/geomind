"""The agent that sets the case: demand, site, requirements and time, from the files."""

import ast

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.agents.case.geoscientist import Geoscientist
from geomind.agents.support.lead import SupportLead
from geomind.prompts import Prompt
from geomind.tools import Delegate
from geomind.tools.delegate import Team
from geomind.tools.gemini.case import economics_leaves
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


BY_HAND = "economics not asked"
"""The start of the case lead's one refusal of an answer that set economics without asking."""


def _changes_economics(call):
    """Return the economics a ``set_case`` call sends inside its ``changes``, or ``None``."""
    changes = call.get("changes")
    return changes.get("economics") if isinstance(changes, dict) else None


def user_sourced(call):
    """Tell whether every economics key a ``set_case`` call sets is sourced to the user.

    QA-256: a price the user names in chat ("carbon price 80 EUR/t") is set in one ``set_case``
    whose ``about.sources`` names the user for each key; it needs no economics question again.
    """
    patch = call.get("economics") or _changes_economics(call) or {}
    sources = (patch.get("about") or {}).get("sources") or {}
    keys = economics_leaves(patch)
    return bool(keys) and all(
        isinstance(sources.get(key), dict) and sources[key].get("source") == "user" for key in keys
    )


def economics_by_hand(context):
    """Return the refusal of an answer that wrote economics with ``set_case`` unasked, or ``None``.

    QA-243: ``ask_economics`` was refused twice, then the lead wrote the economics with
    ``set_case`` and the user never saw the economics question. Economics sent to ``set_case``
    pass only after an answered ``ask_economics`` (``change some`` then gives the values).
    """
    messages = context.messages
    by_hand = [
        call
        for call in calls_of(messages, "set_case")
        if (call.get("economics") or _changes_economics(call)) and not user_sourced(call)
    ]
    if not by_hand or any(BY_HAND in (message.content or "") for message in messages):
        return None
    asked = {
        call.id
        for message in messages
        if message.role == "assistant"
        for call in message.tool_calls
        if call.name == "ask_economics"
    }
    answered = [
        message
        for message in messages
        if message.role == "tool"
        and message.tool_call_id in asked
        and "answer" in (message.content or "")
    ]
    if answered:
        return None
    return (
        f"{BY_HAND}: you wrote economics with set_case, but the user never answered the economics "
        "question. Economics enter the case only through ask_economics: call it now, fixing what "
        "its last refusal named (each row by an id from knowledge/data-economics.csv, each unit "
        "as the error lists it; a Knowledge document's value as {key, value, unit, source} with "
        "no row), then finish"
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


STOP = "stop"
"""The option of the case lead's questions that ends the request (QA-197)."""
STOPPED = "Stopped by the user"
"""The start of the case lead's answer after ``stop``; the project lead ends the request on it."""
NO_STOP = "stop not reported"
"""The start of the case lead's one refusal of an answer after ``stop`` that does not say so."""


def proposed_answer(messages):
    """Return the text of the ``finish`` call the last assistant message proposes, or ``""``."""
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        for call in message.tool_calls:
            if call.name == "finish":
                return str((call.input or {}).get("answer", ""))
        return message.content or ""
    return ""


def stop_not_reported(context):
    """Return the refusal of an answer after the user chose ``stop`` that hides it, or ``None``.

    QA-197: after ``stop`` the project lead sent the case lead again, which wrote the case seven
    times. The answer must start with ``STOPPED`` so the project lead ends the request by rule.
    """
    messages = context.messages
    reply = last_reply(messages)
    if reply is None or reply.strip().lower() != STOP:
        return None
    if any(NO_STOP in (message.content or "") for message in messages):
        return None
    if proposed_answer(messages).lstrip().startswith(STOPPED):
        return None
    return (
        f"{NO_STOP}: the user chose 'stop'. Set nothing more and ask nothing more. Finish now with "
        f"an answer that starts with '{STOPPED}:', then says what the case holds as stored (from "
        "the last set_case result or read_case, never from your plan) and what is open"
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
        # The case lead always splits the case among up to four geoscientists in one call, and
        # again for what is left, so the single geoscientist tool is gone (QA-140, IMP-025).
        geoscientist = Delegate(Geoscientist(), max_summary_tokens=FINDINGS_TOKENS)
        geoscientist.keeps_result = "run"
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
        """Refuse once an answer hiding a ``stop``, or skipping ``change some`` or the economics."""
        return (
            stop_not_reported(context)
            or changes_not_asked(context)
            or economics_by_hand(context)
            or economics_missing(context)
        )

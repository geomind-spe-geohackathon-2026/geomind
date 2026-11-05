"""The agent that leads the project: plans the teams' work, routes failures, decides the end."""

from geomind import runtime, tools
from geomind.agents.agent import Agent, Model
from geomind.agents.analysis.lead import AnalysisLead
from geomind.agents.case.lead import STOPPED, CaseLead
from geomind.agents.design.lead import DesignLead
from geomind.agents.project.comparison import ComparisonDriver
from geomind.agents.project.explainer import Explainer
from geomind.agents.project.review import Review
from geomind.agents.support.lead import SupportLead
from geomind.prompts import Prompt
from geomind.tools import Delegate, suggestions
from geomind.types import Action, Message, ToolCall

TEAM_TOKENS = 1500
"""The most tokens of a team lead's answer the project lead reads back."""
EXPLANATION_TOKENS = 6000
"""The most tokens of the explanation, which is most of the final answer."""
LOAD_CASE = "load-project-case"
"""The id of the call that loads the project's case by rule before the first model call."""
STOP_CASE = "finish-on-stop"
"""The id of the finish call that ends the request by rule after the user's ``stop`` (QA-197)."""


def has_project_case(context):
    """Tell whether the project's case must be loaded: none in the state yet, or a newer one.

    QA-266: the user saved the case form again (150 to 175 mD); the chat's case still held the
    old value and the run answered from it. A project case that differs from the state's is the
    user's own saved case, so it is loaded by rule before the first model call.
    """
    workspace = context.session.workspace
    if workspace is None or context.project is None or not hasattr(workspace, "case"):
        return False
    found = workspace.case(context.project)
    if found is None:
        return False
    return context.problem.case is None or bool(project_case_changes(context, found))


def project_case_changes(context, found=None):
    """Return ``path old -> new`` lines where the project's saved case differs from the state's.

    ``about`` (notes and sources) is left out: only values count. Empty when either is missing.
    """
    from geomind.engine.session import _differing, _leaf

    workspace = context.session.workspace
    current = context.problem.case
    if found is None:
        if workspace is None or context.project is None or not hasattr(workspace, "case"):
            return []
        found = workspace.case(context.project)
    if found is None or not isinstance(current, dict):
        return []
    saved = found[0]
    paths = [
        path
        for path in _differing(current, saved)
        if path != "about" and not path.startswith("about.")
    ]
    return [f"{path} {_leaf(current, path)} -> {_leaf(saved, path)}" for path in paths]


def case_stopped(messages):
    """Return the case lead's last answer when it says the user chose ``stop``, or ``None``.

    QA-197: a ``stop`` to the case lead's question ends the request; the project lead must not
    send the case lead again, so its answer goes to the user as it is.
    """
    if not messages or messages[-1].role != "tool":
        return None
    asked = {
        call.id
        for message in messages
        if message.role == "assistant"
        for call in message.tool_calls
        if call.name == "case_lead"
    }
    last = messages[-1]
    if last.tool_call_id in asked and STOPPED in (last.content or ""):
        return last.content
    return None


REPEATED = "earlier answer repeated"
"""The start of the project lead's one refusal of an answer that prints an earlier one again."""
REPEATED_LINES = 15
"""How many long lines of an earlier answer a new answer may hold before it is refused."""
LONG_LINE = 40
"""The characters a line needs to count: headings and short table rows repeat by nature."""


def proposed_text(messages):
    """Return the text the last assistant message proposes as the answer, or ``""``."""
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        for call in message.tool_calls:
            if call.name == "finish":
                return str((call.input or {}).get("answer", ""))
        return message.content or ""
    return ""


def earlier_answer_repeated(context):
    """Return the refusal of an answer that prints an earlier answer of the chat again, or None.

    QA-289: asked for a short comparison for a manager, the answer re-printed the whole earlier
    design report (360 lines) before the table. An answer is an assistant message of an
    earlier turn, before the last user message; refused once.
    """
    messages = context.messages
    if any(REPEATED in (message.content or "") for message in messages):
        return None
    last_user = max(
        (index for index, message in enumerate(messages) if message.role == "user"), default=0
    )
    earlier = {
        line.strip()
        for message in messages[:last_user]
        if message.role == "assistant" and not message.tool_calls
        for line in (message.content or "").splitlines()
        if len(line.strip()) >= LONG_LINE
    }
    if not earlier:
        return None
    lines = [line.strip() for line in proposed_text(messages).splitlines()]
    repeated = sum(1 for line in lines if line in earlier)
    if repeated <= REPEATED_LINES:
        return None
    return (
        f"{REPEATED}: your answer prints {repeated} lines of an earlier answer of this chat again. "
        "Answer only the new message, in the form the user asked for (short, one table, for a "
        "manager): name the earlier answer ('the report above') instead of repeating it"
    )


DENIALS = "Denied by the user in this request"
"""The start of the note that tells the project lead each card the user denied (QA-288)."""


def request_denials(context):
    """Return ``(tool, what it would do, the user's words)`` of each card denied in this request.

    QA-288: the user denied a design lead's ``set_ranges`` with words; the denial lived in the
    nested run, the project lead read only the design lead's pick and briefed the same search
    again, twice. Every run of the request tree logs under the root, so the lead sees them all.
    """
    from geomind.engine.session import DENIED_BY_USER, call_summary

    session = context.session
    store = getattr(getattr(session, "engine", None), "store", None)
    root = getattr(getattr(session, "state", None), "root", None)
    if store is None or root is None:
        return []
    inputs, found = {}, []
    for event in store.load_events(root):
        call = getattr(event, "call", None)
        if event.type == "request" and call is not None:
            inputs[call.id] = call.input
        if event.type == "permission" and event.decision == "deny" and event.rule == "user":
            words = event.reason if event.reason and event.reason != DENIED_BY_USER else None
            done = call_summary(event.tool, inputs.get(event.call_id) or {}) or event.tool
            found.append((event.tool, done, words))
    return found


def denials_note(denials):
    """Return the note the project lead reads after its teams' answers, or ``None``."""
    if not denials:
        return None
    lines = [
        f"- {tool}: {done}" + (f" -- the user's words: {words!r}" if words else "")
        for tool, done, words in denials
    ]
    return (
        f"{DENIALS} (the user's own instruction, which holds for the rest of the request; never "
        "brief a team to do the denied work again, under any name, and follow the user's words):\n"
        + "\n".join(lines)
    )


def comparison():
    """Return the rule-driven comparison of families as a delegate of the project lead.

    NOTE: the driver plans with the design lead, designs each family in a nested run, verifies
    each with gemini and has them compared and explained; a user cannot answer inside it.
    """
    driver = ComparisonDriver()
    driver.load_loop_state(
        {
            "concurrency": runtime.get("compare_concurrency"),
            "retries": runtime.get("compare_retries"),
            "asks": False,
        }
    )
    return Delegate(driver, max_summary_tokens=EXPLANATION_TOKENS)


class ProjectLead(Agent):
    """Plan the teams' work, write each a brief, route each failure to its owner, decide the end.

    NOTE: it is a model. The guards are code: the project's case file is loaded by rule before
    its first call, the ``reviewer`` tool runs gemini's check again after the reviewer and keeps a
    passed design as experience, the ``Verified`` hook keeps an unverified design from the user,
    and the budget, the step limit, the output limit and the stop on repeated identical failures
    are the engine's.
    """

    def __init__(self):
        """Declare the prompt, the teams, the comparison, the state and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("project/lead")

        # Tools
        self.case_lead = Delegate(CaseLead(), max_summary_tokens=TEAM_TOKENS)
        self.design_lead = Delegate(DesignLead(), max_summary_tokens=TEAM_TOKENS)
        self.reviewer = Review()
        self.analysis_lead = Delegate(AnalysisLead(), max_summary_tokens=TEAM_TOKENS)
        self.explainer = Delegate(Explainer(), max_summary_tokens=EXPLANATION_TOKENS)
        self.support_lead = Delegate(SupportLead(), max_summary_tokens=TEAM_TOKENS)
        self.comparison = comparison()
        self.list_plants = tools.gemini.list_plants
        self.list_studies = tools.gemini.list_studies
        self.list_files = tools.list_files
        self.read_case = tools.gemini.read_case
        self.set_case = tools.gemini.set_case
        self.case_changes = tools.gemini.case_changes
        self.accept_case = tools.gemini.accept_case
        self.update_state = tools.update_state
        self.read_stored = tools.read_stored
        self.read_knowledge = tools.read_knowledge
        self.ask_user = tools.ask_user
        self.finish = suggestions.finish

        # Model
        self.model = Model(setting="projectlead_model", temperature=0)

    def answer_problem(self, context):
        """Refuse once an answer that prints an earlier answer of the chat again (QA-289)."""
        return earlier_answer_repeated(context)

    async def forward(self, context):
        """End on the user's ``stop``; load the project's case file by rule first; else ask."""
        stopped = case_stopped(context.messages)
        if stopped is not None:
            call = ToolCall(id=STOP_CASE, name="finish", input={"answer": stopped})
            return Action(text="", tool_calls=(call,))
        if not context.messages or context.messages[-1].role != "user":
            note = denials_note(request_denials(context))
            if note is None:
                return await super().forward(context)
            messages = [*context.messages_for(self), Message(role="user", content=note)]
            return await self.complete(context, messages)
        if has_project_case(context) and not any(
            message.role == "tool" for message in context.messages
        ):
            call = ToolCall(id=LOAD_CASE, name="set_case", input={"source": "project"})
            return Action(text="", tool_calls=(call,))
        return await super().forward(context)

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
from geomind.types import Action, ToolCall

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

    async def forward(self, context):
        """End on the user's ``stop``; load the project's case file by rule first; else ask."""
        stopped = case_stopped(context.messages)
        if stopped is not None:
            call = ToolCall(id=STOP_CASE, name="finish", input={"answer": stopped})
            return Action(text="", tool_calls=(call,))
        if not context.messages or context.messages[-1].role != "user":
            return await super().forward(context)
        if has_project_case(context) and not any(
            message.role == "tool" for message in context.messages
        ):
            call = ToolCall(id=LOAD_CASE, name="set_case", input={"source": "project"})
            return Action(text="", tool_calls=(call,))
        return await super().forward(context)

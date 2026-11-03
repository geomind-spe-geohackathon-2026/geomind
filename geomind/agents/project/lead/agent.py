"""The agent that leads the project: plans the teams' work, routes failures, decides the end."""

from geomind import runtime, tools
from geomind.agents.agent import Agent, Model
from geomind.agents.analysis.lead.agent import AnalysisLead
from geomind.agents.case.lead.agent import CaseLead
from geomind.agents.design.lead.agent import DesignLead
from geomind.agents.project.explainer.agent import Explainer
from geomind.agents.project.lead.comparison_driver import ComparisonDriver
from geomind.agents.project.lead.review import Review
from geomind.agents.support.lead.agent import SupportLead
from geomind.prompts import Prompt
from geomind.tools import Delegate
from geomind.types import Action, ToolCall

TEAM_TOKENS = 1500
"""The most tokens of a team lead's answer the project lead reads back."""
EXPLANATION_TOKENS = 6000
"""The most tokens of the explanation, which is most of the final answer."""
LOAD_CASE = "load-project-case"
"""The id of the call that loads the project's case by rule before the first model call."""


def has_project_case(context):
    """Tell whether the run's project holds a case file and the state has no case yet."""
    workspace = context.session.workspace
    if context.problem.case is not None or workspace is None or context.project is None:
        return False
    return hasattr(workspace, "case") and workspace.case(context.project) is not None


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
        self.read_case = tools.gemini.read_case
        self.set_case = tools.gemini.set_case
        self.case_changes = tools.gemini.case_changes
        self.accept_case = tools.gemini.accept_case
        self.update_state = tools.update_state
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Model
        self.model = Model(setting="projectlead_model", temperature=0)

    async def forward(self, context):
        """Load the project's case file by rule first; then ask the model."""
        if not context.messages or context.messages[-1].role != "user":
            return await super().forward(context)
        if has_project_case(context) and not any(
            message.role == "tool" for message in context.messages
        ):
            call = ToolCall(id=LOAD_CASE, name="set_case", input={"source": "project"})
            return Action(text="", tool_calls=(call,))
        return await super().forward(context)

"""The agent that routes a message: a skeleton."""

from typing import Literal

from geomind.agents.agent import Agent, Model, Output
from geomind.prompts import Prompt
from geomind.types import Action, Record


class Route(Record):
    """Where a message goes: a short direct answer, or a loop with an agent.

    ``loop`` and ``agent`` name rows of ``LOOPS`` and ``AGENTS`` in ``run.py``, which sits to the
    right of this package, so a test keeps the two lists equal. The delegate reads the user's
    message itself, never a retelling of it; ``task`` is the coordinator's brief beside it, for
    a message that is an event of the app (a form saved, a file added) rather than words.
    ``preferences`` are what the user said about how they work, such as the units they read,
    kept in the problem state for every agent.
    """

    kind: Literal["answer", "loop"]
    answer: str | None = None
    loop: Literal["tool", "project", "design", "compare"] = "tool"
    agent: Literal["analysis_lead"] = "analysis_lead"
    task: str | None = None
    preferences: dict[str, str] | None = None


ROUTE_OPTIONS = {
    "kind": {
        "answer": "a short answer in `answer`, by you: a greeting, what the team can do, or "
        "what the conversation already says; never a number",
        "loop": "the message goes to a loop and its agents, named by `loop` (and `agent`)",
    },
    "loop": {
        "tool": "one agent answers with its tools, the one `agent` names: a question about the "
        "case, a plant, a module, a profile, a result or a cost",
        "project": "the project lead plans the teams' work: setting or changing the case, "
        "designing, sizing, optimising, checking, explaining, and every app event",
        "design": "the design team alone on the case as it is (design lead and reviewer, no "
        "case work, analysis or explanation): only when the user asks for exactly a new design "
        "round on a case already set",
        "compare": "two or more design families the user names, designed side by side on the "
        "case as it is, then compared",
    },
    "agent": {
        "analysis_lead": "the analysis team: reads the case, plants, modules, profiles and "
        "results, simulates a what-if, and gives KPIs, costs and sensitivities",
    },
}
"""What each value of a ``Route`` field means; a test keeps the keys equal to ``Route``'s."""


def route_options():
    """Return the prompt text of every option of a route, with what it means."""
    lines = ["## Route options", ""]
    for field, options in ROUTE_OPTIONS.items():
        lines.append(f"`{field}`:")
        lines += [f"- `{value}`: {meaning}" for value, meaning in options.items()]
    return "\n".join(lines)


class Coordinator(Agent):
    """Route each message: answer it directly, or choose the loop and the agent."""

    def __init__(self):
        """Declare the prompt, the typed route and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("project/coordinator", appendix=route_options)

        # Output
        self.output = Output(Route)

        # Model
        self.model = Model(setting="coordinator_model", temperature=0)

    async def forward(self, context):
        """Route by rule to the project loop when the project's saved case is newer (QA-266).

        The coordinator reads only the conversation, so a second hand-saved case change read as
        a repeated question and went to the analysis lead, which answered from the old case.
        """
        from geomind.agents.project.lead import project_case_changes

        changes = project_case_changes(context)
        if not changes:
            return await super().forward(context)
        listed = "; ".join(changes[:8]) + ("; ..." if len(changes) > 8 else "")
        route = Route(
            kind="loop",
            loop="project",
            task=(
                "The project's saved case differs from the chat's case (the user saved it by "
                f"hand): {listed}. Load it with set_case(source='project'), then answer the "
                "user's message on that case: earlier results are of the old case."
            ),
        )
        return Action(text=route.model_dump_json(exclude_none=True))


class Answer(Agent):
    """Give the short answer a route holds, by rule: the run of an ``answer`` route."""

    def __init__(self, answer=""):
        """Keep the answer."""
        super().__init__()

        # Model
        self.model = Model(name="rule")
        self._answer = answer

    async def forward(self, context):
        """Answer with the route's text."""
        return Action(text=self._answer)

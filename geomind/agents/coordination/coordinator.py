"""The agent that routes a message: a skeleton."""

from typing import Literal

from geomind.agents.agent import Agent, Model, Output
from geomind.prompts import Prompt
from geomind.types import Action, Record


class Route(Record):
    """Where a message goes: a short direct answer, or a loop with an agent and a brief.

    ``loop`` and ``agent`` name rows of ``LOOPS`` and ``AGENTS`` in ``run.py``, which sits to the
    right of this package, so a test keeps the two lists equal.
    """

    kind: Literal["answer", "loop"]
    answer: str | None = None
    loop: Literal["tool", "design", "makerchecker", "compare"] = "tool"
    agent: Literal["analyst", "code_assistant"] = "analyst"
    brief: str | None = None


class Coordinator(Agent):
    """Route each message: answer it directly, or choose the loop and the agent."""

    def __init__(self):
        """Declare the prompt, the typed route and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("coordinator")

        # Output
        self.output = Output(Route)

        # Model
        self.model = Model(setting="coordinator_model", temperature=0)


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

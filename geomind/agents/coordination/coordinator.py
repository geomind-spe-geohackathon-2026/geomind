"""The agent that routes a message: a skeleton."""

from typing import Literal

from geomind.agents.agent import Agent, Model, Output
from geomind.prompts import Prompt
from geomind.types import Record


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

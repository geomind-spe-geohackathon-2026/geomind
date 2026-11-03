"""The agent that writes the summary of older turns."""

from geomind.agents.agent import Agent, Model, Output
from geomind.prompts import Prompt


class Summarizer(Agent):
    """Compress older turns into one summary, on its own model.

    NOTE: it has no tools and no steps of its own: ``engine/compaction.py`` makes its one call, and
    the summary is a ``compaction`` event instead of a turn of the conversation.
    """

    def __init__(self):
        """Declare the prompt, a text answer and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("support/summarizer")

        # Output
        self.output = Output(str)

        # Model
        self.model = Model(setting="summarizer_model")

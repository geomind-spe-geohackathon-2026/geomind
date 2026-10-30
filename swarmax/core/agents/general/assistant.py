"""The general assistants."""

from swarmax import tools
from swarmax.core.agents.agent import Agent, Model, Output
from swarmax.core.prompts import Prompt


class Assistant(Agent):
    """General assistant that answers with the tools it has."""

    def __init__(self):
        """Declare the prompt, the built-in tools, a text answer and the default model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("assistant")

        # Tools
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Output
        self.output = Output(str)

        # Model
        self.model = Model(temperature=0)


class CodeAssistant(Assistant):
    """General assistant that can also write and run Python in a sandbox.

    NOTE: ``Run`` uses it when a sandbox is configured. ``Assistant`` stays as agreed, without code
    tools, so a run without a sandbox offers the model no tool that can only fail.
    """

    def __init__(self):
        """Add the code tools to the assistant."""
        super().__init__()

        # Tools
        self.run_python = tools.run_python
        self.read_file = tools.read_file
        self.write_file = tools.write_file

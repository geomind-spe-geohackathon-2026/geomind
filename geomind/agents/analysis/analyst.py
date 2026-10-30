"""The sample agent: the reference for how an agent is built."""

from geomind import tools
from geomind.agents.agent import Agent, Model, Output
from geomind.prompts import Prompt


class Analyst(Agent):
    """Answer questions about a plant with numbers that come from tools.

    NOTE: the gemini tools (``list_modules``, ``describe_module``, ``evaluate_module``,
    ``read_plant``, ``simulate``) are declared here, and named in its prompt, once gemini provides
    what they need; until then it reads results and documents and keeps the problem state.
    """

    def __init__(self):
        """Declare the prompt, the tools that exist, a text answer and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("analyst")

        # Tools
        self.read_result = tools.read_result
        self.search_documents = tools.search_documents
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.ask_user = tools.ask_user
        self.finish = tools.finish

        # Output
        self.output = Output(str)

        # Model
        self.model = Model(setting="analyst_model", temperature=0)

"""The agent that checks a proposal."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


class Verifier(Agent):
    """Simulate the current design afresh, run gemini's checks and record them in the state.

    NOTE: the checks are gemini's, never the model's judgement; the loop and the ``Verified`` hook
    run them again on the result this agent records.
    """

    def __init__(self):
        """Declare the prompt, the tools that run and read the checks, and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("verifier")

        # Tools
        self.read_plant = tools.gemini.read_plant
        self.simulate = tools.gemini.simulate
        self.check_results = tools.gemini.check_results
        self.compute_kpis = tools.gemini.compute_kpis
        self.read_result = tools.read_result
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.finish = tools.finish

        # Model
        self.model = Model(setting="verifier_model", temperature=0)

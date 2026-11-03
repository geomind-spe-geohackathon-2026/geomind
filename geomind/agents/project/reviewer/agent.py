"""The agent that checks a proposal."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


class Reviewer(Agent):
    """Run gemini's checks once on the final design and review what gemini cannot see.

    NOTE: the checks are gemini's, never the model's judgement; the loop and the ``Verified`` hook
    run them again on the result this agent records. What this agent adds is the review gemini
    does not do: changes of the case since the user gave it, a result that is not the design's
    whole year, and assumptions the user has not confirmed. The explainer reads its report.
    """

    def __init__(self):
        """Declare the prompt, the tools that run and read the check, and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("project/reviewer")

        # Tools
        self.check_results = tools.gemini.check_results
        self.case_changes = tools.gemini.case_changes
        self.read_case = tools.gemini.read_case
        self.compute_kpis = tools.gemini.compute_kpis
        self.read_result = tools.read_result
        self.update_state = tools.update_state
        self.read_skill = tools.read_skill
        self.read_stored = tools.read_stored
        self.search_knowledge = tools.search_knowledge
        self.read_knowledge = tools.read_knowledge
        self.finish = tools.finish

        # Model
        self.model = Model(setting="reviewer_model", temperature=0)

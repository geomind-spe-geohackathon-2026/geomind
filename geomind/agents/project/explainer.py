"""The agent that explains a design."""

from geomind import tools
from geomind.agents.agent import Agent, Model, Output
from geomind.prompts import Prompt
from geomind.tools.gemini.verdict_text import metrics_reference


def for_run(tool):
    """Return a copy of ``tool`` whose results stay whole for the whole run.

    The explainer writes one answer from everything it read: a result that shrank after a few
    turns was read again, the whole set three times in one run (#106).
    """
    kept = tool.kept()
    kept.keeps_result = "run"
    return kept


class Explainer(Agent):
    """Explain the verified design: capacities, schematic, costs, checks and each major decision."""

    def __init__(self):
        """Declare the prompt, the tools that read the design and its results, and the model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("project/explainer", appendix=metrics_reference)

        # Tools
        self.read_case = for_run(tools.gemini.read_case)
        self.case_changes = for_run(tools.gemini.case_changes)
        self.read_plant = for_run(tools.gemini.read_plant)
        self.read_result = for_run(tools.read_result)
        self.list_studies = for_run(tools.gemini.list_studies)
        self.read_study = for_run(tools.gemini.read_study)
        self.compute_kpis = for_run(tools.gemini.compute_kpis)
        self.estimate_costs = for_run(tools.gemini.estimate_costs)
        self.search_rag = tools.search_rag
        self.read_skill = tools.read_skill
        self.finish = tools.finish

        # Output
        self.output = Output(str)

        # Model
        self.model = Model(setting="explainer_model", temperature=0)

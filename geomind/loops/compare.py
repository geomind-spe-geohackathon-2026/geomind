"""Compare alternative plant families: each designed, verified, then compared and explained."""

from geomind import runtime
from geomind.agents.project.lead.comparison_driver import CompareDriver, ComparisonDriver
from geomind.loops.design import DesignLoop


class StudyCompareLoop(DesignLoop):
    """Design by comparing families in one study: the ``compare`` loop up to 0.4.5.

    It is a ``DesignLoop`` whose design_lead is asked for two or three families and compares them
    with one ``run_study``. NOTE: a log and a recording of 0.4.5 and before name this driver, so
    they run on it; a new run takes ``CompareLoop``.
    """

    name = "compare"
    driver = CompareDriver


class CompareLoop(DesignLoop):
    """Compare families: plan, design each alone, verify each, compare, explain.

    The families come from the request or the case, else the ``DesignLead`` proposes them, and a
    user confirms them unless the run is ``auto``, where they are unconfirmed assumptions. One
    family's ``DesignLead`` nested run per family designs it, ``concurrency`` of them side by side
    (the setting ``compare_concurrency``; unset, one at a time); a failed or infeasible family
    stops nothing and keeps its reason. The ``Reviewer`` checks each feasible design; one gemini
    rejects runs again, told why, up to ``retries`` times (setting ``compare_retries``; unset, no
    retry). The
    ``Economist`` compares the verified ones and the ``Explainer`` writes the comparison.
    Budgets and time limits are hooks of the run, shared by its nested runs. A stop gives a
    partial answer listing the finished alternatives.
    """

    name = "compare"
    driver = ComparisonDriver

    def __init__(self, design_lead, reviewer, max_rounds=5, concurrency=None, retries=None):
        """Keep the agents and the limits; the settings give what is not given."""
        super().__init__(design_lead, reviewer, max_rounds)
        self.concurrency = concurrency or runtime.get("compare_concurrency")
        self.retries = retries if retries is not None else runtime.get("compare_retries")
        self.asks = False
        self.agent.load_loop_state(self.state_dict())

    def guard(self, engine):
        """Register the hook, and note whether a user can answer in this run."""
        super().guard(engine)
        self.asks = engine.permissions.mode == "ask"
        self.agent.load_loop_state(self.state_dict())

    def state_dict(self):
        """Return the limit, the concurrency and whether a user can answer."""
        return {
            **super().state_dict(),
            "concurrency": self.concurrency,
            "asks": self.asks,
            "retries": self.retries,
        }

    def load_state_dict(self, state):
        """Take the logged settings; a log without one keeps this loop's."""
        super().load_state_dict(state)
        self.concurrency = state.get("concurrency", self.concurrency)
        self.asks = state.get("asks", self.asks)
        self.retries = state.get("retries", self.retries)

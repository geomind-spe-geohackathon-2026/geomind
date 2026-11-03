"""Size, optimise, verify and repeat until a design passes, driven by rule."""

from geomind.agents.project.lead.design_driver import DesignDriver
from geomind.engine.hooks import Verified
from geomind.loops.loop import Loop


class DesignLoop(Loop):
    """Let ``design_lead`` propose and ``reviewer`` check, for at most ``max_rounds`` rounds.

    A rule-based ``DesignDriver`` runs the rounds in one root run: each delegated agent is a nested
    run in the same log. The ``DesignLead`` sizes, simulates, checks and optimises; the ``Reviewer``
    checks its final design once; only a failure sends it back. A design that passes is costed by
    the ``Economist`` and explained by the ``Explainer``. The loop stops when gemini's checks pass,
    at ``max_rounds``, when one round fails exactly as the one before, or when an agent asks the
    user; a token or cost budget is a hook of the run. Each stop is written in the driver's step
    text and in the answer as ``stop: <reason>``.
    A design run needs a case with a demand in the problem state: when it has none the driver asks
    the user before designing and hands the answer to the design lead, and stops with ``no_case`` at
    ``max_rounds`` when the design lead still leaves none.
    """

    name = "design"
    driver = DesignDriver

    def __init__(self, design_lead, reviewer, max_rounds=5):
        """Keep the two agents and the limit; a run starts with the design lead."""
        self.design_lead = design_lead
        self.reviewer = reviewer
        self.max_rounds = max_rounds
        self.agent = self.driver(design_lead, reviewer, max_rounds)

    def guard(self, engine):
        """Register the ``Verified`` hook once, so no design reaches the user unverified."""
        if not any(isinstance(hook, Verified) for hook in engine.hooks()):
            engine.register_hook(Verified())

    async def run(self, engine, task):
        """Drive the rounds from the context ``task``."""
        self.guard(engine)
        return await engine.run(self.agent, task, loop=self)

    async def resume(self, engine, run_id, request_id=None, answer=None):
        """Continue the rounds where the log left them."""
        self.guard(engine)
        return await engine.resume(run_id, request_id, answer, agent=self.agent, loop=self)

    def state_dict(self):
        """Return the limit of this loop; its position is the run's own history."""
        return {"max_rounds": self.max_rounds}

    def load_state_dict(self, state):
        """Take the logged limit; a log without one keeps this loop's."""
        self.max_rounds = state.get("max_rounds", self.max_rounds)

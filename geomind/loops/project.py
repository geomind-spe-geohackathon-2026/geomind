"""The project: the project lead plans and leads the teams until the design passes, or stops."""

from geomind.engine.hooks import Verified
from geomind.loops.tool import ToolLoop


class ProjectLoop(ToolLoop):
    """Run the ``ProjectLead`` until it answers, with the ``Verified`` hook on.

    NOTE: the order of the teams is the project lead's decision, a model's; what stays code is
    the hook that keeps an unverified design from the user, the review's check by gemini, the
    budget, the step limit and the stop on repeated identical failures.
    """

    name = "project"

    def guard(self, engine):
        """Register the ``Verified`` hook once, so no design reaches the user unverified."""
        if not any(isinstance(hook, Verified) for hook in engine.hooks()):
            engine.register_hook(Verified())

    async def run(self, engine, task):
        """Lead the project from the context ``task``."""
        self.guard(engine)
        return await super().run(engine, task)

    async def resume(self, engine, run_id, request_id=None, answer=None):
        """Continue the project where the log left it."""
        self.guard(engine)
        return await super().resume(engine, run_id, request_id, answer)

"""A loop decides which run comes next and when the goal is met."""


class Loop:
    """Base class: ``run`` drives the engine, as gemini's ``optim`` drives ``Engine.replay``.

    The state of a loop is logged on ``run.started`` and ``step.finished``, so a pause inside a loop
    resumes at the same place in another process. NOTE: loops are written as resumable steps, never
    with state held only in local variables.
    """

    name = "loop"

    async def run(self, engine, task):
        """Drive the engine toward the goal in ``task`` and return a ``RunResult``."""
        raise NotImplementedError

    async def resume(self, engine, run_id, request_id=None, answer=None):
        """Continue a run, with this loop receiving its logged state."""
        return await engine.resume(run_id, request_id, answer, loop=self)

    def state_dict(self):
        """Return the JSON-safe position of this loop."""
        return {}

    def load_state_dict(self, state):
        """Take the position a ``state_dict`` returned."""

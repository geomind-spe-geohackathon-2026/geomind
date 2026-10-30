"""One engine run of one agent."""

from swarmax.errors import LoopError
from swarmax.loops.loop import Loop


class ToolLoop(Loop):
    """Run ``agent`` until it stops; ``max_steps`` defaults to the runtime setting."""

    name = "tool"

    def __init__(self, agent, max_steps=None):
        """Keep the agent and the limit."""
        self.agent = agent
        self.max_steps = max_steps

    async def run(self, engine, task):
        """Run the agent from the context ``task``."""
        return await engine.run(self.agent, task, max_steps=self.max_steps, loop=self)

    async def resume(self, engine, checkpoint, request_id=None, answer=None):
        """Continue the agent of this loop."""
        return await engine.resume(checkpoint, request_id, answer, agent=self.agent, loop=self)

    def state_dict(self):
        """Return which agent this loop runs."""
        return {"agent": self.agent.path}

    def load_state_dict(self, state):
        """Refuse a state of another agent."""
        if state.get("agent") != self.agent.path:
            raise LoopError(
                f"ToolLoop: agent = {state.get('agent')!r}; expected {self.agent.path!r}"
            )

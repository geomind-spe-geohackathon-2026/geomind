"""A stand-in for the engine's session, for tests below the engine."""

from swarmax.core.types import Usage
from swarmax.errors import SandboxError
from swarmax.sandbox import LocalSandbox, Manifest


class StubState:
    """The part of the run state that agents and hooks read."""

    def __init__(self):
        """Start with no usage."""
        self.step_usage = Usage()
        self.usage = Usage()
        self.step = 1


class StubSession:
    """Records what tools and agents ask of the run."""

    def __init__(self, sandbox_root=None):
        """Use a local sandbox below ``sandbox_root``; ``None`` means no sandbox is configured."""
        self.state = StubState()
        self.artifacts = {}
        self.errors = []
        self.sandbox_root = sandbox_root
        self.current_sandbox = None
        self.lost = 0
        self.decision = None
        self.completion = None
        self.result = None

    async def save_artifact(self, key, data):
        """Keep an artifact."""
        self.artifacts[key] = data

    async def report_error(self, error, where):
        """Keep an internal error."""
        self.errors.append((error, where))

    async def sandbox(self):
        """Return the run's sandbox, as the engine does, or raise when none is configured."""
        if self.sandbox_root is None:
            raise SandboxError("no sandbox is configured")
        if self.current_sandbox is None:
            self.current_sandbox = await LocalSandbox(self.sandbox_root).provision(Manifest())
        return self.current_sandbox

    async def lose_sandbox(self):
        """Forget the sandbox."""
        self.lost += 1
        self.current_sandbox = None

    async def delegate(self, agent, task):
        """Return the scripted nested result."""
        self.delegated = (agent, task)
        return self.result

    async def before_llm_call(self, agent, messages):
        """Return the scripted hook decision."""
        return self.decision

    async def complete(self, agent, messages):
        """Return the scripted completion and count it in the step."""
        self.state.step_usage = self.completion.usage
        return self.completion

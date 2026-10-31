"""A stand-in for the engine's session, for tests below the engine."""

from geomind.errors import SandboxError
from geomind.sandbox import LocalSandbox, Manifest
from geomind.types import Usage


class StubState:
    """The part of the run state that agents and hooks read."""

    def __init__(self):
        """Start with no usage."""
        self.step_usage = Usage()
        self.usage = Usage()
        self.step = 1
        self.parent = None


class StubSession:
    """Records what tools and agents ask of the run."""

    def __init__(self, sandbox_root=None, workspace=None):
        """Use a local sandbox below ``sandbox_root``; ``None`` means no sandbox is configured."""
        self.state = StubState()
        self.workspace = workspace
        self.artifacts = {}
        self.changes = []
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

    def load_artifact(self, key):
        """Return a kept artifact, or ``None``."""
        return self.artifacts.get(key)

    async def change_state(self, changes):
        """Keep a change of the problem state; return the version it gives."""
        self.changes.append(list(changes))
        return len(self.changes)

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

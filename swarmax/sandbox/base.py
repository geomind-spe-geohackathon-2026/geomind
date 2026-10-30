"""What every sandbox offers, what goes in and the limits."""

import importlib.util
from pathlib import Path, PurePosixPath
from typing import Protocol

from swarmax import runtime
from swarmax.errors import SandboxError
from swarmax.types import Record

TIMED_OUT = 124
"""The exit code of a command stopped by its time limit, as the ``timeout`` command uses."""
NOT_FOUND = 127
"""The exit code of a command that does not exist, as a shell uses."""


class ExecutionResult(Record):
    """The outcome of one command."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0


class Manifest(Record):
    """What goes into a sandbox: ``files`` by path, ``packages`` read-only, and the limits."""

    files: dict[str, str] = {}
    packages: tuple[str, ...] = ("gemini",)
    python: str = "3.11"
    cpu: float = 1
    memory: str = "1g"
    disk: str = "1g"
    timeout: str = "10min"
    network: bool = False

    @classmethod
    def from_runtime(cls):
        """Return the manifest of the current runtime settings."""
        return cls(
            cpu=runtime.get("sandbox_cpu"),
            memory=runtime.get("sandbox_memory"),
            disk=runtime.get("sandbox_disk"),
            timeout=runtime.get("sandbox_timeout"),
        )


class Sandbox(Protocol):
    """One provisioned place to run code. A lost one raises ``SandboxError``."""

    async def execute(self, command, *, timeout):
        """Run a command in the working folder and return its ``ExecutionResult``."""

    async def write(self, path, data):
        """Write bytes to a path inside the sandbox."""

    async def read(self, path):
        """Return the bytes at a path inside the sandbox."""

    async def close(self):
        """Remove the sandbox."""


class SandboxProvider(Protocol):
    """Makes sandboxes; the engine calls it on the first tool that needs one."""

    async def provision(self, manifest):
        """Return a new ``Sandbox`` for ``manifest``."""


def package_root(name):
    """Return the folder holding an installed package, without importing it."""
    spec = importlib.util.find_spec(name)
    if spec is None or spec.origin is None:
        raise SandboxError(f"sandbox: package = {name!r}; expected an installed package")
    return Path(spec.origin).parent.parent


def checked_path(path):
    """Return a relative path that cannot leave the sandbox's working folder."""
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise SandboxError(f"sandbox: path = {path!r}; expected a path inside the sandbox")
    return pure

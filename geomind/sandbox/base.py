"""What goes into a sandbox, what comes out, and the limits from the runtime settings."""

from pathlib import PurePosixPath

from geomind import runtime
from geomind.errors import SandboxError
from geomind.types import Record

TIMED_OUT = 124
"""The exit code of a command stopped by its time limit, as the ``timeout`` command uses."""


class ExecutionResult(Record):
    """The outcome of one command."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0


class Manifest(Record):
    """The image and limits of one sandbox; every field comes from a setting, none has a default."""

    image: str
    cpu: float
    memory: str
    disk: str
    timeout: str
    network: bool = False

    @classmethod
    def from_runtime(cls):
        """Return the manifest of the current settings; an unset one raises and names it."""
        missing = [
            variable
            for name, variable in runtime.SANDBOX_SETTINGS.items()
            if runtime.get(name) is None
        ]
        if missing:
            raise SandboxError(f"sandbox: settings unset: {', '.join(missing)}; expected each set")
        return cls(
            image=runtime.get("sandbox_image"),
            cpu=float(runtime.get("sandbox_cpu")),
            memory=runtime.get("sandbox_memory"),
            disk=runtime.get("sandbox_disk"),
            timeout=runtime.get("sandbox_timeout"),
        )


def checked_path(path):
    """Return a relative path that cannot leave the sandbox's working folder."""
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise SandboxError(f"sandbox: path = {path!r}; expected a path inside the sandbox")
    return pure

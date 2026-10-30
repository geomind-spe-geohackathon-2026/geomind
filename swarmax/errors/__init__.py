"""Every swarmax exception class, available as ``sx.errors.<Name>``.

Each class also derives from the matching built-in exception, so ``except ValueError`` keeps
catching, for example, ``sx.errors.RequestError``. Nothing in this package imports from the rest
of ``swarmax``.
"""

from swarmax.errors.agent import DeclarationError, OutputError, UnknownNameError
from swarmax.errors.base import SwarmaxError
from swarmax.errors.run import CheckpointError, LoopError, ReplayError, RequestError, RunError
from swarmax.errors.services import ProviderError, SandboxError, ToolError

__all__ = [
    "SwarmaxError",
    "DeclarationError",
    "UnknownNameError",
    "OutputError",
    "RunError",
    "RequestError",
    "CheckpointError",
    "ReplayError",
    "LoopError",
    "ProviderError",
    "ToolError",
    "SandboxError",
]

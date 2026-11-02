"""Every geomind exception class, available as ``gd.errors.<Name>``.

Each class also derives from the matching built-in exception, so ``except ValueError`` keeps
catching, for example, ``gd.errors.RequestError``. Nothing in this package imports from the rest
of ``geomind``.
"""

from geomind.errors.agent import DeclarationError, OutputError, UnknownNameError
from geomind.errors.base import GeomindError
from geomind.errors.run import (
    BudgetError,
    LoopError,
    ReplayError,
    RequestError,
    RunError,
    StateError,
)
from geomind.errors.services import NotImplementedYet, ProviderError, SandboxError, ToolError

__all__ = [
    "GeomindError",
    "DeclarationError",
    "UnknownNameError",
    "OutputError",
    "RunError",
    "RequestError",
    "StateError",
    "ReplayError",
    "LoopError",
    "BudgetError",
    "ProviderError",
    "ToolError",
    "SandboxError",
    "NotImplementedYet",
]

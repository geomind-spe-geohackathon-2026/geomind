"""swarmax: agents, an engine over an event log, tools and the Run facade the backend uses."""

from swarmax import errors, providers, sandbox, tools
from swarmax.core import runtime
from swarmax.core.types import Action, Allow, Deny, Message, Request, RunResult
from swarmax.core.types.runlog import runlog
from swarmax.tools import Tool, tool

__version__ = "0.1.0"
__all__ = [
    "Tool",
    "tool",
    "Message",
    "Action",
    "Request",
    "Allow",
    "Deny",
    "RunResult",
    "runlog",
    "tools",
    "providers",
    "sandbox",
    "runtime",
    "errors",
    "__version__",
]


def __dir__():
    """Expose only the documented API in interactive completion."""
    return sorted(__all__)

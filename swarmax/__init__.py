"""swarmax: agents, an engine over an event log, tools and the Run facade the backend uses."""

from swarmax import errors, providers, sandbox, tools
from swarmax.core import agents, runtime
from swarmax.core.agents import Agent, Model, Output
from swarmax.core.engine import Context, Engine, Permissions, callbacks, hooks
from swarmax.core.prompts import Prompt
from swarmax.core.types import Action, Allow, Deny, Message, Request, RunResult
from swarmax.core.types.runlog import runlog
from swarmax.tools import Tool, tool

__version__ = "0.1.0"
__all__ = [
    "Agent",
    "Engine",
    "Context",
    "Permissions",
    "hooks",
    "callbacks",
    "Prompt",
    "Model",
    "Output",
    "Tool",
    "tool",
    "Message",
    "Action",
    "Request",
    "Allow",
    "Deny",
    "RunResult",
    "runlog",
    "agents",
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

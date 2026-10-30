"""geomind: agents, an engine over an event log, tools and the Run facade the backend uses."""

from geomind import agents, errors, loops, providers, runtime, sandbox, stores, testing, tools
from geomind.agents import Agent, Model, Output
from geomind.engine import Context, Engine, Permissions, callbacks, hooks
from geomind.prompts import Prompt
from geomind.run import Run
from geomind.tools import Tool, tool
from geomind.types import Action, Allow, Deny, Message, Request, RunResult
from geomind.types.runlog import runlog

__version__ = "0.1.0"
__all__ = [
    "Run",
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
    "loops",
    "stores",
    "testing",
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

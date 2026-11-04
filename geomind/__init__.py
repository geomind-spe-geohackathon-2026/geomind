"""geomind: agents, an engine over an event log, tools and the Run facade the backend uses."""

from geomind import (
    agents,
    errors,
    loops,
    mcp,
    providers,
    runtime,
    stores,
    testing,
    tools,
    verify,
)
from geomind.agents import Agent, Model, Output
from geomind.engine import Context, Engine, Permissions, callbacks, hooks
from geomind.prompts import Prompt
from geomind.run import Run
from geomind.tools import Tool, tool
from geomind.tools.suggestions import suggest
from geomind.types import Action, Allow, Deny, Message, Request, RunResult
from geomind.types.events import event_from_dict
from geomind.types.runlog import runlog

__version__ = "0.4.22.dev55"
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
    "suggest",
    "event_from_dict",
    "agents",
    "loops",
    "mcp",
    "stores",
    "testing",
    "tools",
    "verify",
    "providers",
    "runtime",
    "errors",
    "__version__",
]


def __dir__():
    """Expose only the documented API in interactive completion."""
    return sorted(__all__)

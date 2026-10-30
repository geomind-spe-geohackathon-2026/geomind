"""``Agent`` and the shipped agents.

Imports ``tools`` and everything to its left; never the engine.
"""

from geomind.agents.agent import Agent, AgentResult, Model, Output
from geomind.agents.analysis.analyst import Analyst
from geomind.agents.coordination.coordinator import Coordinator, Route
from geomind.agents.design.designer import Designer
from geomind.agents.economics.economist import Economist
from geomind.agents.general.assistant import Assistant, CodeAssistant
from geomind.agents.general.summarizer import Summarizer
from geomind.agents.reporting.explainer import Explainer
from geomind.agents.verification.verifier import Verifier
from geomind.errors import UnknownNameError
from geomind.utils.strings import did_you_mean, snake_case

__all__ = [
    "Agent",
    "AgentResult",
    "Analyst",
    "Assistant",
    "CodeAssistant",
    "Coordinator",
    "Designer",
    "Economist",
    "Explainer",
    "Model",
    "Output",
    "named",
    "Route",
    "Summarizer",
    "Verifier",
]


def named(name):
    """Return a new agent by its snake_case name, for trying one agent by hand or by tasks."""
    classes = {
        snake_case(item.__name__): item
        for item in globals().values()
        if isinstance(item, type) and issubclass(item, Agent) and item is not Agent
    }
    if name not in classes:
        raise UnknownNameError(
            f"agents: name = {name!r}; expected a shipped agent{did_you_mean(name, classes)}"
        )
    return classes[name]()

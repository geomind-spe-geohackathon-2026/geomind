"""``Agent`` and the shipped agents, one folder per team: ``<team>/<name>/agent.py``.

Imports ``tools`` and everything to its left; never the engine.
"""

from geomind.agents.agent import Agent, AgentResult, Model, Output
from geomind.agents.analysis.economist.agent import Economist
from geomind.agents.analysis.lead.agent import AnalysisLead
from geomind.agents.case.geoscientist.agent import Geoscientist
from geomind.agents.case.lead.agent import CaseLead
from geomind.agents.design.energy.agent import EnergySystemsEngineer
from geomind.agents.design.integration.agent import IntegrationEngineer
from geomind.agents.design.lead.agent import DesignLead
from geomind.agents.design.process.agent import ProcessEngineer
from geomind.agents.design.reservoir.agent import ReservoirEngineer
from geomind.agents.design.well.agent import WellEngineer
from geomind.agents.project.coordinator.agent import Coordinator, Route
from geomind.agents.project.explainer.agent import Explainer
from geomind.agents.project.lead.agent import ProjectLead
from geomind.agents.project.reviewer.agent import Reviewer
from geomind.agents.support.curator.agent import Curator
from geomind.agents.support.lead.agent import SupportLead
from geomind.agents.support.summarizer.agent import Summarizer
from geomind.errors import UnknownNameError
from geomind.utils.strings import did_you_mean, snake_case

__all__ = [
    "Agent",
    "AgentResult",
    "AnalysisLead",
    "CaseLead",
    "Coordinator",
    "Curator",
    "DesignLead",
    "Economist",
    "EnergySystemsEngineer",
    "Explainer",
    "Geoscientist",
    "IntegrationEngineer",
    "Model",
    "Output",
    "ProcessEngineer",
    "ProjectLead",
    "ReservoirEngineer",
    "named",
    "Reviewer",
    "Route",
    "Summarizer",
    "SupportLead",
    "WellEngineer",
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

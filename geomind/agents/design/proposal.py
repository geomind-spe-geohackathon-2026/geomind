"""What a design engineer hands the design lead: proposed plant changes, never a stored plant.

Only the design lead reads and writes the project's plants (IMP-025, user rule: a team lead alone
reads and writes project files). An engineer works from the plant text, the case values and the
missing paths the lead puts into its brief, and returns each change it proposes with its source;
the lead applies all engineers' changes in one ``patch_plant`` (QA-145: 27 hand patches, one plant
version each, in a 70-minute run).
"""

from typing import Any

from geomind import tools
from geomind.types import Record


class Change(Record):
    """One plant value the engineer proposes, as the plant file writes it at ``path``.

    ``path`` is a dotted plant path (``params.d0.depth``); ``value`` is what the plant file holds
    there, such as ``{"value": 2500, "unit": "m"}`` or ``"peak"``. ``source`` is the case path, the
    brief's file and page, the Knowledge document and section, or ``assumption`` with ``reason``.
    """

    path: str
    value: Any
    source: str
    reason: str | None = None


class Evaluation(Record):
    """A number only gemini gives, which the lead should evaluate for the engineer.

    ``module`` is the module id or class; ``point`` the operating point in words with its values
    (inlet temperature and flow, outlet temperature); ``why`` what the number decides.
    """

    module: str
    point: str
    why: str


class Proposal(Record):
    """The engineer's answer: its changes, numbers to evaluate, case changes and couplings.

    ``case_changes`` holds ``<case path>: <why>`` for a value that belongs to the case;
    ``couplings`` a value that another group or the lead must agree, with the engineer's value.
    """

    changes: list[Change]
    evaluations: list[Evaluation] = []
    case_changes: list[str] = []
    couplings: list[str] = []
    note: str | None = None


def proposer_tools(agent):
    """Give a design engineer its tools: the module catalogue, the Knowledge, memory and finish.

    No tool reads or writes the project's case, plants, profiles or results: the brief holds what
    the engineer needs (IMP-025).
    """
    agent.describe_module = tools.gemini.describe_module.kept()
    agent.search_knowledge = tools.search_knowledge
    agent.read_knowledge = tools.read_knowledge
    agent.search_memory = tools.search_memory
    agent.read_memory = tools.read_memory
    agent.finish = tools.finish

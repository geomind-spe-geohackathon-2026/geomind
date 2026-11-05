"""The agent that reads the reports for the ground, the reservoir, the brine and its gas."""

from typing import Literal

from geomind import tools
from geomind.agents.agent import Agent, Model, Output
from geomind.prompts import Prompt
from geomind.tools.gemini.skeleton import trees
from geomind.types import Record


class Source(Record):
    """Where a value stands: the file, and its page, table and depth when the file gives them."""

    file: str
    page: int | None = None
    table: str | None = None
    depth: str | None = None
    quote: str | None = None


class Finding(Record):
    """One value a report gives, as the report gives it, with its source and quality.

    ``base`` is the value the report takes as its base case; ``low`` and ``high`` its range when
    it gives one. ``path`` is the case path the value would set, from the case key tree, or
    ``None`` when the case has no key for it. ``quality`` says how the report got it.
    """

    quantity: str
    path: str | None = None
    base: float | str | None = None
    low: float | None = None
    high: float | None = None
    unit: str | None = None
    quality: Literal["measured", "tested", "interpreted", "estimated", "unknown"]
    source: Source
    note: str | None = None


class Missing(Record):
    """A value the case needs that no report gives, and why it matters."""

    quantity: str
    path: str | None = None
    why: str


class Disagreement(Record):
    """One quantity two sources give differently: each value with its own source."""

    quantity: str
    path: str | None = None
    values: list[Finding]


class Findings(Record):
    """What the geoscientist hands the case lead: proposals only, never a case it set."""

    values: list[Finding]
    missing: list[Missing]
    disagreements: list[Disagreement]
    files_read: list[str]


class Geoscientist(Agent):
    """Extract the ground, reservoir, brine and dissolved-gas data from the project's reports.

    NOTE: it proposes values to the ``CaseLead`` with their page and quality and never sets the
    case; a value no report gives is reported missing, never filled with a typical value. It
    reads no file: the lead's brief holds the report text it works on (IMP-025: only a team lead
    reads and writes the project's files).
    """

    def __init__(self):
        """Declare the prompt with the case keys, the tools over files, the findings and model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("case/geoscientist", appendix=trees("case_compact"))

        # Tools
        self.describe_case = tools.gemini.describe_case
        self.search_knowledge = tools.search_knowledge
        self.read_knowledge = tools.read_knowledge
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.finish = tools.finish

        # Output
        self.output = Output(Findings)

        # Model
        self.model = Model(setting="geoscientist_model", temperature=0)

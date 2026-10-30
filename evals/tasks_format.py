"""The task files: a message, what the run may use, and criteria checked by code."""

import re
from typing import Annotated, Literal

import yaml
from pydantic import Field

import geomind as gd
from geomind.types import Record

NUMBER = r"-?\d+(?:\.\d+)?"


class NumberCriterion(Record):
    """The answer holds a number within ``tolerance`` of ``value``, in ``unit`` if one is given."""

    kind: Literal["number"]
    value: float
    tolerance: float
    unit: str | None = None

    def problem(self, outcome):
        """Return what is wrong, or ``None``."""
        suffix = rf"\s*{re.escape(self.unit)}(?![\w/])" if self.unit else ""
        found = [float(item) for item in re.findall(f"({NUMBER}){suffix}", outcome.answer)]
        if any(abs(item - self.value) <= self.tolerance for item in found):
            return None
        return f"number: expected {self.value} ± {self.tolerance} {self.unit or ''}, found {found}"


class ToolCriterion(Record):
    """A tool was called, or with ``called: false`` was not."""

    kind: Literal["tool"]
    tool: str
    called: bool = True

    def problem(self, outcome):
        """Return what is wrong, or ``None``."""
        if (self.tool in outcome.tools) == self.called:
            return None
        return f"tool: {self.tool} called = {not self.called}; expected {self.called}"


class QuestionCriterion(Record):
    """The agent asked the user a question holding ``contains``."""

    kind: Literal["question"]
    contains: str

    def problem(self, outcome):
        """Return what is wrong, or ``None``."""
        if any(self.contains.lower() in question.lower() for question in outcome.questions):
            return None
        return f"question: none holds {self.contains!r}; asked {outcome.questions}"


class StateCriterion(Record):
    """A field of the final problem state is set; ``path`` is a JSON Pointer, by id in lists."""

    kind: Literal["state"]
    path: str

    def problem(self, outcome):
        """Return what is wrong, or ``None``."""
        node = outcome.state
        for token in self.path.split("/")[1:]:
            if isinstance(node, list):
                node = next((item for item in node if item.get("id") == token), None)
            else:
                node = node.get(token) if isinstance(node, dict) else None
        return None if node not in (None, "", [], {}) else f"state: {self.path} is not set"


Criterion = Annotated[
    NumberCriterion | ToolCriterion | QuestionCriterion | StateCriterion,
    Field(discriminator="kind"),
]


class Task(Record):
    """One task file; ``plant`` is a project folder and ``answers`` reply to questions in order."""

    message: str
    plant: str | None = None
    history: tuple[gd.Message, ...] = ()
    answers: tuple[str, ...] = ()
    criteria: tuple[Criterion, ...]


def load_task(path):
    """Return the task of one YAML file."""
    return Task.model_validate(yaml.safe_load(path.read_text()))

"""The task files: a message, what the run may use, and criteria checked by code."""

import re
from typing import Annotated, Any, Literal

import yaml
from pydantic import Field

import geomind as gd
from geomind.types import Record

NUMBER = r"-?\d+(?:\.\d+)?"
UNSIGNED = r"(?<![\d.])\d+(?:\.\d+)?"
THOUSANDS = r"(?<=\d)[,\u00a0\u202f](?=\d{3}(?!\d))"


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
    """A field of the final problem state is set, to ``equals`` if given.

    ``path`` is a JSON Pointer, by id in lists.
    """

    kind: Literal["state"]
    path: str
    equals: Any = None

    def problem(self, outcome):
        """Return what is wrong, or ``None``."""
        node = outcome.state
        for token in self.path.split("/")[1:]:
            if isinstance(node, list):
                node = next((item for item in node if item.get("id") == token), None)
            else:
                node = node.get(token) if isinstance(node, dict) else None
        if node in (None, "", [], {}):
            return f"state: {self.path} is not set"
        if self.equals is not None and node != self.equals:
            return f"state: {self.path} = {node!r}; expected {self.equals!r}"
        return None


class VerifiedCriterion(Record):
    """gemini's checks pass again on the final design and its result, on the case it ran on.

    ``checks`` names checks that must be among them and pass, such as a limit of the case.
    """

    kind: Literal["verified"]
    checks: tuple[str, ...] = ()

    def problem(self, outcome):
        """Return what is wrong, or ``None``."""
        verdict = outcome.verdict or {"passed": False, "failures": [], "checks": []}
        if not verdict["passed"]:
            failed = [item["name"] for item in verdict["failures"]]
            return f"verified: failed {failed} {verdict.get('reason', '')}".rstrip()
        passed = {item["name"] for item in verdict["checks"] if item["passed"] is True}
        missing = [name for name in self.checks if name not in passed]
        return f"verified: checks {missing} not among the passed checks" if missing else None


def _numbers(text):
    """Return the numbers of a text, without sign, reading ``1,030`` as one thousand and thirty."""
    return {float(item) for item in re.findall(UNSIGNED, re.sub(THOUSANDS, "", text))}


class SourcedCriterion(Record):
    """Every number of the answer and the questions is one the agent read: the agent computed none.

    What the agent read is every message it was sent that it did not write itself: the prompt,
    the user's messages and answers, and the tools' results. A whole number up to ``small``
    counts things or numbers a list, so it needs no source.
    """

    kind: Literal["sourced"]
    small: int

    def problem(self, outcome):
        """Return what is wrong, or ``None``."""
        read = _numbers(outcome.read)
        found = _numbers(" ".join([outcome.answer, *outcome.questions]))
        unread = sorted({item for item in found if item not in read and not self._is_small(item)})
        return f"sourced: numbers no message holds {unread}" if unread else None

    def _is_small(self, number):
        """Tell whether a number is a whole one up to ``small``."""
        return number.is_integer() and number <= self.small


class BeforeCriterion(Record):
    """``tool`` was called before the first call of ``then``; a run without ``then`` passes.

    The order of the run's own tool results, so a search comes before the question it spares.
    """

    kind: Literal["before"]
    tool: str
    then: str

    def problem(self, outcome):
        """Return what is wrong, or ``None``."""
        if self.then not in outcome.tools:
            return None
        if self.tool in outcome.tools[: outcome.tools.index(self.then)]:
            return None
        return f"before: no {self.tool} before the first {self.then}; tools {outcome.tools}"


Criterion = Annotated[
    NumberCriterion
    | ToolCriterion
    | QuestionCriterion
    | StateCriterion
    | VerifiedCriterion
    | SourcedCriterion
    | BeforeCriterion,
    Field(discriminator="kind"),
]


class SetupCall(Record):
    """One tool call run by code before the task's agent, so the task starts from a fixed state."""

    tool: str
    input: dict[str, Any] = {}


class AnswerRule(Record):
    """A user's answer by rule: the first rule whose ``match`` (a regex) is in the question.

    For a question with options, ``answer`` must be one of their values; ``only_options`` keeps
    a rule off the questions that ask for typed text.
    """

    match: str
    answer: str
    only_options: bool = False


class Task(Record):
    """One task file; ``plant`` is a project folder and ``answers`` reply to questions in order.

    The folder is gemini's project layout: ``case.json``, ``economics.json``, ``data/`` and, when
    the task starts from a plant, one file in ``plants/``. ``max_steps`` caps the steps of every
    agent of the run, for a task about a tight budget.
    """

    message: str
    plant: str | None = None
    history: tuple[gd.Message, ...] = ()
    answers: tuple[str | AnswerRule, ...] = ()
    setup: tuple[SetupCall, ...] = ()
    max_steps: int | None = None
    criteria: tuple[Criterion, ...]


def load_task(path):
    """Return the task of one YAML file."""
    return Task.model_validate(yaml.safe_load(path.read_text()))

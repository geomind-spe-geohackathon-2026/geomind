"""Declarative rules and a mode, decided in one fixed order."""

from geomind.errors import UnknownNameError
from geomind.tools.base import EFFECTS
from geomind.types import Allow, Deny, Request
from geomind.utils.strings import did_you_mean, join_names

MODES = ("auto", "ask", "readonly", "plan")
PLAN_FEEDBACK = "plan mode: describe what you would do"
DEFAULT_ALLOW = ("update_state",)


def _check_rule(rule):
    """Refuse an ``effect:`` rule with an unknown effect."""
    effect = rule.removeprefix("effect:")
    if rule.startswith("effect:") and effect not in EFFECTS:
        raise UnknownNameError(
            f"Permissions: rule = {rule!r}; expected an effect of {join_names(EFFECTS)}"
            f"{did_you_mean(effect, EFFECTS)}"
        )


def _matching(rules, tool):
    """Return the first rule naming this tool or its effect, or ``None``."""
    names = (tool.name, f"effect:{tool.effect}")
    return next((rule for rule in rules if rule in names), None)


class Permissions:
    """Decide tool calls: ``allow``, ``ask`` and ``deny`` are tool names or ``effect:<effect>``.

    After the ``before_tool_call`` hooks, a call is decided in this order: deny rules, the limits
    of ``readonly`` and ``plan``, ask rules, allow rules, then the rest of the mode.

    NOTE: allow rules come before the mode because the mode decides every remaining call, so an
    allow rule after it could never apply. NOTE: ``readonly`` and ``plan`` are checked before ask
    rules, because otherwise an approval could run a tool those modes promise never to run.
    NOTE: ``update_state`` is allowed by default, after ask rules, because it only touches the
    run's own notes and an approval for each note would make ``ask`` unusable.
    """

    def __init__(self, mode="ask", allow=(), ask=(), deny=(), answers_questions=True):
        """Check the mode and the rules.

        ``answers_questions``: in ``auto`` mode the engine also answers every question itself
        with its proposal, so nobody is asked (QA-339); ``False`` keeps questions for the user.
        """
        if mode not in MODES:
            raise UnknownNameError(
                f"Permissions: mode = {mode!r}; expected one of {join_names(MODES)}"
                f"{did_you_mean(mode, MODES)}"
            )
        for rule in (*allow, *ask, *deny):
            _check_rule(rule)
        self.mode = mode
        self.answers_questions = answers_questions
        self.allow = tuple(allow)
        self.ask = tuple(ask)
        self.deny = tuple(deny)

    def _limit(self, tool):
        """Return the refusal of ``plan`` and ``readonly``, or ``None``."""
        if self.mode == "plan":
            return Deny(reason=PLAN_FEEDBACK)
        if self.mode == "readonly" and tool.effect not in ("read", "compute"):
            return Deny(reason=f"readonly mode: {tool.name} has effect {tool.effect}")
        return None

    def decide(self, tool, *, ask=()):
        """Return ``(decision, rule that made it)``; ``ask`` adds rules from hooks."""
        rule = _matching(self.deny, tool)
        if rule is not None:
            return Deny(reason=f"{tool.name} is denied by rule {rule}"), f"deny:{rule}"
        limit = self._limit(tool)
        if limit is not None:
            return limit, f"mode:{self.mode}"
        rule = _matching((*self.ask, *ask), tool)
        if rule is not None:
            return self._approval(tool), f"ask:{rule}"
        rule = _matching((*self.allow, *DEFAULT_ALLOW), tool)
        if rule is not None:
            return Allow(), f"allow:{rule}"
        if self.mode == "ask" and tool.effect not in ("read", "compute"):
            return self._approval(tool), "mode:ask"
        return Allow(), f"mode:{self.mode}"

    def _approval(self, tool):
        """Return the request of one call."""
        return Request(kind="approval", message=f"Allow {tool.name} ({tool.effect})?")

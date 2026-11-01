"""Verify a design against its requirements and limits."""

from geomind.context.state import Requirement
from geomind.tools.gemini.verification import assess


def requirement_limits(requirements):
    """Return the limits of the requirements gemini can check, and the others as not assessed.

    A requirement whose ``metric`` names ``<path>.<output>`` and that has a ``target`` becomes a
    limit of ``target`` ± ``tolerance`` on every day of the run.
    """
    import gemini as gm

    limits, skipped = gm.checks.Limits(), []
    for item in requirements:
        requirement = item if isinstance(item, Requirement) else Requirement.model_validate(item)
        if (
            requirement.metric is None
            or "." not in requirement.metric
            or requirement.target is None
        ):
            skipped.append(
                {
                    "id": requirement.id,
                    "status": "NOT_ASSESSED",
                    "reason": "its metric is not '<path>.<output>' with a target, so no gemini "
                    "check judges it",
                    "limit": requirement.target,
                }
            )
            continue
        spread = requirement.tolerance or 0.0
        target = requirement.target
        limits.add(requirement.metric, min=target - spread, max=target + spread)
    return limits.to_dict()["limits"], skipped


def verify(plant, results, *, requirements=(), limits=None, brief=None):
    """Return ``{passed, checks, failures, not_assessed, not_given, brief}`` for a plant and run.

    ``checks`` holds one gemini Check per balance, limit and requirement, the limits of ``brief``
    (a ``Brief``, or its JSON) always among them; without one, those of the ``hackathon_2027``
    preset, and ``brief`` of the result says so. ``requirements`` are items of the problem state,
    and ``limits`` is what ``gm.checks.Limits.to_dict`` returns. ``failures`` names the domain of
    each failed check, ``not_assessed`` what gemini cannot judge yet, with the reason, and
    ``not_given`` the limits the brief does not give, which are not checked.
    """
    from_requirements, skipped = requirement_limits(requirements)
    extra = {"limits": [*(limits or {}).get("limits", []), *from_requirements]}
    found = assess(plant, results, extra, brief)
    found["not_assessed"] = [*found["not_assessed"], *skipped]
    return found

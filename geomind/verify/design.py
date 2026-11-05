"""Verify the design the problem state names, on the stored run that verifies it."""

from geomind.errors import ToolError
from geomind.tools.gemini.case import digests, file_contents
from geomind.tools.gemini.origin import changes_of
from geomind.tools.gemini.stored import RESULT, load_design, load_run
from geomind.verify.verify import verify


def unverified(name, reason, **details):
    """Return a verdict that failed before gemini's checks could run, saying why."""
    return {
        "passed": False,
        "checks": [],
        "failures": [{"name": name, "domain": "coupled", "detail": reason, **details}],
        "reason": reason,
    }


def case_changed(context):
    """Return the verdict of a case that differs from the one the user gave, or ``None``.

    NOTE: a geomind process rule, not physics: a design that meets a weakened case has not met
    the user's, so every difference waits for the user's approval.
    """
    changes = changes_of(context)
    if not changes:
        return None
    paths = ", ".join(sorted({change["path"] for change in changes}))
    reason = (
        f"the case differs from the one the user gave ({paths}); the user must approve the "
        "change, or the case goes back with set_case(source='origin')"
    )
    return unverified("case_changed", reason, changes=changes)


def result_off_case(context, result):
    """Return why ``result`` did not run on the state's case, or ``None``.

    NOTE: a geomind process rule, not physics: a run is verified only against the case it ran on,
    so a case changed since (a limit, the demand, the schedule, the content of a file it names)
    makes the run stale.
    """
    identifier = result.removeprefix(RESULT)
    data = context.problem.case
    ran_on = context.session.load_artifact(f"{identifier}.case")
    kept = context.session.load_artifact(f"{identifier}.files")
    current = digests(file_contents(context, data, {})) if data is not None else None
    if ran_on == data and kept == current:
        return None
    return (
        f"{result} ran on another case than the problem state's; simulate the design on the "
        "state's case and check it again"
    )


def same_plant(context, plant, design):
    """Tell whether ``plant`` (of a stored run) is the plant of ``design``.

    Both sides are gemini's form of the plant (``to_dict(structure=True)``) built by gemini: a
    project plant version ``design/v<N>`` is no chat artifact, and its saved dict (nulls, key
    order) differs from gemini's form, so a fresh run of it was called stale (QA-233).
    """
    try:
        stored = load_design(context, design, "verification")
    except ToolError:
        return False
    return plant.to_dict(structure=True) == stored.to_dict(structure=True)


def verify_design(context):
    """Return the verdict of ``design.reference`` on ``verification.result`` of the problem state.

    The run is loaded from the store and judged by gemini on the case it ran on. NOTE: a
    ``passed`` written in the state is never read, a result whose plant is not the design's is
    stale, and one that ran on another case than the state's is off the case.
    """
    problem = context.problem
    design = (problem.design or {}).get("reference")
    result = (problem.verification or {}).get("result")
    if design is None or result is None:
        return unverified(
            "verification_missing",
            "the design and its result are not both in the problem state; simulate the design, "
            "run check_results, and record design.reference and verification.result",
        )
    try:
        plant, case, results = load_run(context, result, "verification")
    except ToolError as error:
        return unverified("result_unknown", str(error))
    if not same_plant(context, plant, design):
        return unverified(
            "stale_result",
            f"{result} is stale: it ran another plant than {design}; simulate the current design "
            "and check it",
        )
    mismatch = result_off_case(context, result)
    if mismatch is not None:
        return unverified("result_off_case", mismatch)
    return case_changed(context) or verify(plant, results, case)

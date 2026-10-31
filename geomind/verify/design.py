"""Verify the design the problem state names, on the stored run that verifies it."""

from geomind.errors import ToolError
from geomind.tools.gemini.assessment import stored_run
from geomind.verify.verify import verify


def unverified(name, reason):
    """Return a verdict that failed before gemini's checks could run, saying why."""
    return {
        "passed": False,
        "checks": [],
        "failures": [{"name": name, "domain": "coupled"}],
        "not_assessed": [],
        "reason": reason,
    }


def verify_design(context):
    """Return the verdict of ``design.reference`` on ``verification.result`` of the problem state.

    The run is loaded from the store and checked again with gemini, with the state's requirements
    and the limits of its brief.
    NOTE: a ``passed`` written in the state is never read, and a result whose plant is not the
    design's is stale.
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
        plant, results = stored_run(context, result, "verification")
    except ToolError as error:
        return unverified("result_unknown", str(error))
    if plant.to_dict() != context.session.load_artifact(design):
        return unverified(
            "stale_result",
            f"{result} is stale: it ran another plant than {design}; simulate the current design "
            "and check it",
        )
    return verify(plant, results, requirements=problem.requirements, brief=problem.brief)

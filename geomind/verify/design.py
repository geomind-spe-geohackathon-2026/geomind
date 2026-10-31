"""Verify the design the problem state names, on the stored run that verifies it."""

from geomind.errors import ToolError
from geomind.tools.gemini.assessment import stored_run
from geomind.tools.gemini.brief import schedule_rules
from geomind.tools.gemini.runs import demand_names
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


def off_brief(context, result, brief):
    """Return why ``result`` did not run on the brief's demand and rules, or ``None``.

    A result from before ``<id>.run`` was kept, or a state without a brief, is not compared.
    """
    run = context.session.load_artifact(f"{result.removeprefix('result/')}.run")
    if brief is None or run is None:
        return None
    try:
        expected = {"demand": demand_names(brief, None), "rules": schedule_rules(brief)}
    except ToolError as error:
        return f"the brief cannot be simulated: {error}"
    for name, value in expected.items():
        if run[name] != value:
            return (
                f"{result} ran with {name} {run[name]}, the brief's is {value}; simulate the "
                "design on the brief and check it again"
            )
    return None


def verify_design(context):
    """Return the verdict of ``design.reference`` on ``verification.result`` of the problem state.

    The run is loaded from the store and checked again with gemini, with the state's requirements
    and the limits of its brief.
    NOTE: a ``passed`` written in the state is never read, a result whose plant is not the
    design's is stale, and one that ran on another demand or rules than the brief's is off the
    brief.
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
    mismatch = off_brief(context, result, problem.brief)
    if mismatch is not None:
        return unverified("result_off_brief", mismatch)
    return verify(plant, results, requirements=problem.requirements, brief=problem.brief)

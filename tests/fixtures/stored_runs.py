"""A design simulated on an example's case and stored in a run, for tests of assessment."""

import asyncio
import functools
import io

import pandas as pd

from geomind.context import ProblemState
from geomind.tools.gemini.case import case_of, merge_patch
from geomind.tools.gemini.stored import save_design, save_run
from tests.fixtures.cases import case_context, example_plant

PEAK_COOLING_SCALE = 1.5
"""The factor on the cooling column that takes the hackathon cooling peak from 10 to 15 MW."""


def scaled_column(content, column, factor):
    """Return the CSV bytes ``content`` with ``column`` multiplied by ``factor``."""
    frame = pd.read_csv(io.BytesIO(content))
    frame[column] = frame[column] * factor
    return frame.to_csv(index=False).encode()


async def stored_run(name, changes=None, scale=None, plant=None):
    """Return ``(context, design, result)``: the example's passing design run on its case.

    ``changes`` is a merge patch on the case, as ``set_case`` takes it, and ``scale`` is
    ``(column, factor)`` for the case's demand file; both are applied before the run, and the
    state holds the case the run used.
    """
    import gemini as gm

    context = await case_context(name)
    data = merge_patch(context.problem.case, changes or {})
    if scale is not None:
        file = data["demand"]["file"]
        content = context.session.load_artifact(f"case/{file}")
        await context.session.save_artifact(f"case/{file}", scaled_column(content, *scale))
    context.problem = ProblemState(case=data)
    design = plant or example_plant(name)
    results = gm.simulate(design, case_of(context))
    reference = await save_design(context, "candidate", design)
    result = await save_run(context, design, results, {"steps": len(results.names())}, {})
    return context, reference, result


COLDER = {"environment": {"ground": {"gradient": {"value": 25, "unit": "K/km"}}}}
"""The colder-reservoir variant of the hackathon case: its lowest declared gradient."""
COOLING_COLUMN = "cooling_demand_MWcool"

VARIANTS = {
    "base": {},
    "colder": {"changes": COLDER},
    "cooling_peak": {"scale": (COOLING_COLUMN, PEAK_COOLING_SCALE)},
}


@functools.cache
def variant_run(name, variant):
    """Return ``stored_run`` of a variant, run once per process; the context is read only."""
    return asyncio.run(stored_run(name, **VARIANTS[variant]))


def warm_runs():
    """Run the variants that tests read, from a synchronous fixture; the runs are then cached."""
    for name in ("hackathon_2026", "shallow_district"):
        variant_run(name, "base")
    for variant in ("colder", "cooling_peak"):
        variant_run("hackathon_2026", variant)

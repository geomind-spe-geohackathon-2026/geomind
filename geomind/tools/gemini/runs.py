"""The tools that read profiles and run a plant."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.brief import SCHEDULE_RULES
from geomind.tools.gemini.plants import load_plant

SHOWN_ERRORS = 5


def parse_time(value, field, where):
    """Return an ISO 8601 text as an aware UTC time, a naive one taken as UTC, or ``None``."""
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise ToolError(
            f"{where}: {field} = {value!r}; expected an ISO 8601 time such as '2027-01-28'",
            path=field,
        ) from None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def demand(names, start, end, where):
    """Return the run input of gemini profiles side by side, from ``start`` to ``end``."""
    import gemini as gm
    import pandas as pd

    frame = pd.concat([gm.profiles.get(name) for name in names], axis=1)
    return frame.loc[parse_time(start, "start", where) : parse_time(end, "end", where)]


@tool(effect="read")
def list_profiles():
    """List the demand profiles, with their name, quantity, unit, start and end."""
    import gemini as gm

    rows = []
    for name in gm.profiles.names():
        frame = gm.profiles.get(name)
        rows.append(
            {
                "name": name,
                "quantity": frame.attrs.get("quantities", {}).get(name),
                "unit": frame.attrs["units"][name],
                "start": frame.index[0].isoformat(),
                "end": frame.index[-1].isoformat(),
            }
        )
    return rows


@tool(effect="read")
def read_profile(name: str, start: str | None = None, end: str | None = None):
    """Return a demand profile as a series; ``start`` and ``end`` are ISO 8601 times."""
    frame = demand([name], start, end, "read_profile")
    return {
        "time": [moment.isoformat() for moment in frame.index],
        "value": frame[name].tolist(),
        "unit": frame.attrs["units"][name],
    }


def stored_series(results):
    """Return results in the stored result format, ``{path: {field: {unit, values}}}``.

    NOTE: the times are left out of each series; they are the same for every series and would
    triple the stored size. ``read_result`` positions are sample numbers, and every failed row
    keeps its time in the summary's errors.
    """
    series = results.to_dict()["series"]
    return {
        path: {
            field: {"unit": item["unit"], "values": item["value"]} for field, item in fields.items()
        }
        for path, fields in series.items()
    }


def run_plant(context, design, changes, profile, start, end):
    """Schedule and simulate a plant on the demand; return what ``simulate`` stores and says."""
    import gemini as gm

    plant = load_plant(context, design, "simulate")
    for path, params in (changes or {}).items():
        plant.set_params(path, params)
    names = [profile] if profile else gm.profiles.names()
    plan = gm.schedule(plant, demand(names, start, end, "simulate"), SCHEDULE_RULES)
    results = gm.simulate(plant, plan, on_error="record")
    spec = plant.to_dict()
    key = json.dumps([spec, names, start, end], sort_keys=True, default=str)
    identifier = hashlib.sha256(key.encode()).hexdigest()[:16]
    errors = results.errors()
    summary = {
        "steps": len(plan),
        "start": plan.index[0].isoformat() if len(plan) else None,
        "end": plan.index[-1].isoformat() if len(plan) else None,
        "failed_steps": len(errors),
        "errors": errors[:SHOWN_ERRORS],
        "totals": gm.kpi.totals(plant, results),
    }
    return identifier, stored_series(results), results.to_bytes(), spec, summary


@tool(effect="compute")
async def simulate(
    context,
    design: str | None = None,
    changes: dict[str, dict[str, Any]] | None = None,
    profile: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Simulate a plant and store the full results; return their reference and a summary.

    ``design`` is a stored design, or the project's plant without one. ``changes`` holds parameters
    by module path, for this run only. ``profile`` names a demand profile.

    NOTE: a run is ``gm.schedule`` with the brief's rules, then ``gm.simulate`` with
    ``on_error="record"``, so a day that fails is one of gemini's problems and the year still
    runs. Without ``profile`` the run takes every demand profile. Beside ``result/<id>`` it keeps
    ``<id>.results`` (``Results.to_bytes()``) and ``<id>.plant`` (the spec that ran).
    """
    identifier, stored, data, spec, summary = await asyncio.to_thread(
        run_plant, context, design, changes, profile, start, end
    )
    reference = f"result/{identifier}"
    await context.session.save_artifact(reference, stored)
    await context.session.save_artifact(f"{identifier}.results", data)
    await context.session.save_artifact(f"{identifier}.plant", spec)
    return {"reference": reference, "summary": summary}

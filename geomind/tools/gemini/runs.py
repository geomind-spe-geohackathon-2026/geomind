"""The tools that read profiles and run a plant."""

import asyncio
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.brief import brief_of, schedule_rules
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


PROFILE = "profile/"
PROFILE_INDEX = "profiles"
"""The artifact that lists the names of the profiles stored in a run."""
QUANTITIES = ("heating_demand", "cooling_demand")
PROFILE_NAME = re.compile(r"[A-Za-z0-9._-]+")


def stored_frame(context, name, where):
    """Return a stored profile ``profile/<name>`` as gemini's profiles are: a UTC frame in W."""
    import pandas as pd

    stored = context.session.load_artifact(name)
    if stored is None:
        raise ToolError(f"{where}: profile = {name!r}; no such stored profile", path="profile")
    index = pd.date_range(stored["start"], periods=len(stored["values"]), freq=stored["step"])
    frame = pd.DataFrame({stored["quantity"]: stored["values"]}, index=index)
    frame.attrs["units"] = {stored["quantity"]: stored["unit"]}
    frame.attrs["quantities"] = {stored["quantity"]: stored["quantity"]}
    return frame


def profile_frame(context, name, where):
    """Return one profile: a stored ``profile/<name>``, else gemini's profile ``name``."""
    import gemini as gm

    if name.startswith(PROFILE):
        return stored_frame(context, name, where)
    return gm.profiles.get(name)


def demand(context, names, start, end, where):
    """Return the run input of profiles side by side, from ``start`` to ``end``."""
    import pandas as pd

    frames = [profile_frame(context, name, where) for name in names]
    frame = pd.concat(frames, axis=1)
    frame.attrs["units"] = {k: v for item in frames for k, v in item.attrs["units"].items()}
    return frame.loc[parse_time(start, "start", where) : parse_time(end, "end", where)]


def profile_row(name, frame):
    """Return the listing of one profile."""
    column = frame.columns[0]
    return {
        "name": name,
        "quantity": frame.attrs.get("quantities", {}).get(column, column),
        "unit": frame.attrs["units"][column],
        "start": frame.index[0].isoformat(),
        "end": frame.index[-1].isoformat(),
    }


@tool(effect="read")
def list_profiles(context):
    """List the demand profiles, with their name, quantity, unit, start and end.

    gemini's named profiles come first, then the profiles stored in this run as ``profile/<name>``.
    """
    import gemini as gm

    rows = [profile_row(name, gm.profiles.get(name)) for name in gm.profiles.names()]
    for name in context.session.load_artifact(PROFILE_INDEX) or []:
        rows.append(profile_row(name, stored_frame(context, name, "list_profiles")))
    return rows


@tool(effect="read")
def read_profile(context, name: str, start: str | None = None, end: str | None = None):
    """Return a demand profile as a series; ``start`` and ``end`` are ISO 8601 times.

    ``name`` is a gemini profile or a stored ``profile/<name>``.
    """
    frame = demand(context, [name], start, end, "read_profile")
    column = frame.columns[0]
    return {
        "time": [moment.isoformat() for moment in frame.index],
        "value": frame[column].tolist(),
        "unit": frame.attrs["units"][column],
    }


def profile_problem(name, values, quantity, step):
    """Return ``(field, message)`` of what makes a user's profile unusable, or ``None``."""
    import pandas as pd

    if not PROFILE_NAME.fullmatch(name) or set(name) == {"."}:
        return "name", f"name = {name!r}; expected letters, digits, '.', '_' or '-'"
    if quantity not in QUANTITIES:
        return "quantity", f"quantity = {quantity!r}; expected heating_demand or cooling_demand"
    if not values:
        return "values", "values = []; expected at least one value, one per step"
    if min(values) < 0 or not all(math.isfinite(value) for value in values):
        return "values", "values: expected finite, non-negative demand on every step"
    try:
        pd.tseries.frequencies.to_offset(step)
    except ValueError:
        return "step", f"step = {step!r}; expected a pandas frequency such as '1D'"
    return None


def stored_profile(name, values, unit, start, step, quantity):
    """Return the stored form of a user's profile: its values converted to W by ``gm.units``."""
    import gemini as gm

    problem = profile_problem(name, values, quantity, step)
    if problem is not None:
        raise ToolError(f"save_profile: {problem[1]}", path=problem[0])
    if not gm.units.fits(unit, "power"):
        raise ToolError(f"save_profile: unit = {unit!r}; expected a unit of power", path="unit")
    moment = parse_time(start, "start", "save_profile")
    return {
        "quantity": quantity,
        "unit": "W",
        "start": moment.isoformat(),
        "step": step,
        "values": [gm.units.convert(value, unit, "W") for value in values],
    }


@tool(effect="write")
async def save_profile(
    context,
    name: str,
    values: list[float],
    unit: str,
    start: str,
    step: str = "1D",
    quantity: str = "heating_demand",
):
    """Store a demand profile the user gave as values, one per step; return its reference.

    ``unit`` is a unit of power (such as ``MW``), ``start`` the ISO 8601 time of the first value
    and ``step`` a pandas frequency. ``quantity`` is heating_demand or cooling_demand. The profile
    is stored as ``profile/<name>`` in W, for ``simulate(profile=...)`` and the brief's demand.
    """
    stored = await asyncio.to_thread(stored_profile, name, values, unit, start, step, quantity)
    reference = f"{PROFILE}{name}"
    await context.session.save_artifact(reference, stored)
    known = context.session.load_artifact(PROFILE_INDEX) or []
    if reference not in known:
        await context.session.save_artifact(PROFILE_INDEX, [*known, reference])
    count = len(stored["values"])
    return {"profile": reference, "steps": count, "start": stored["start"], "unit": "W"}


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


def demand_names(brief, profile):
    """Return the profiles to run on: ``profile``, else the brief's demand, which must be given."""
    if profile:
        return [profile]
    given = brief.demand
    names = [name for name in (given.heating, given.cooling) if name] if given else []
    if not names:
        raise ToolError(
            "simulate: brief = no demand; expected the heating or cooling profile in the brief's "
            "demand, or profile. Ask the user for the demand",
            path="profile",
        )
    return names


def run_plant(context, design, changes, profile, start, end):
    """Schedule and simulate a plant on the demand; return what ``simulate`` stores and says."""
    import gemini as gm

    brief, source = brief_of(context)
    rules = schedule_rules(brief)
    names = demand_names(brief, profile)
    plant = load_plant(context, design, "simulate")
    for path, params in (changes or {}).items():
        plant.set_params(path, params)
    plan = gm.schedule(plant, demand(context, names, start, end, "simulate"), rules)
    results = gm.simulate(plant, plan, on_error="record")
    spec = plant.to_dict()
    key = json.dumps([spec, names, start, end, rules], sort_keys=True, default=str)
    identifier = hashlib.sha256(key.encode()).hexdigest()[:16]
    errors = results.errors()
    summary = {
        "steps": len(plan),
        "start": plan.index[0].isoformat() if len(plan) else None,
        "end": plan.index[-1].isoformat() if len(plan) else None,
        "failed_steps": len(errors),
        "errors": errors[:SHOWN_ERRORS],
        "totals": gm.kpi.totals(plant, results),
        "brief": source,
        "demand": names,
        "rules": rules,
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
    by module path, for this run only. ``profile`` names a demand profile, gemini's or a stored
    ``profile/<name>``.

    NOTE: a run is ``gm.schedule`` with the rules of the state's brief, then ``gm.simulate`` with
    ``on_error="record"``, so a day that fails is one of gemini's problems and the year still
    runs. Without ``profile`` the run takes the brief's demand. A state without a brief runs on the
    ``hackathon_2027`` preset, as before briefs were data, and the summary says which brief, demand
    and rules ran. Beside ``result/<id>`` it keeps ``<id>.results`` (``Results.to_bytes()``) and
    ``<id>.plant`` (the spec that ran); the id covers the rules too.
    """
    identifier, stored, data, spec, summary = await asyncio.to_thread(
        run_plant, context, design, changes, profile, start, end
    )
    reference = f"result/{identifier}"
    await context.session.save_artifact(reference, stored)
    await context.session.save_artifact(f"{identifier}.results", data)
    await context.session.save_artifact(f"{identifier}.plant", spec)
    return {"reference": reference, "summary": summary}

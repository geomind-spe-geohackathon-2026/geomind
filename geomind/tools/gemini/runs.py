"""The tools that read profiles and run a plant."""

import asyncio
from datetime import datetime, timezone
from typing import Any

from geomind.errors import ToolError
from geomind.tools.base import tool

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
    raise ToolError("simulate: not_implemented until the case replaces the brief")


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
    ``<id>.plant`` (the spec that ran) and ``<id>.run`` (the demand, rules and window it ran on);
    the id covers the rules too.
    """
    identifier, stored, data, spec, run, summary = await asyncio.to_thread(
        run_plant, context, design, changes, profile, start, end
    )
    reference = f"result/{identifier}"
    await context.session.save_artifact(reference, stored)
    await context.session.save_artifact(f"{identifier}.results", data)
    await context.session.save_artifact(f"{identifier}.plant", spec)
    await context.session.save_artifact(f"{identifier}.run", run)
    return {"reference": reference, "summary": summary}

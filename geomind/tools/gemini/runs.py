"""The tools that read the demand of the case and run a plant on it."""

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.case import CASE_FILE, build_case, case_of
from geomind.tools.gemini.plants import load_plant
from geomind.tools.gemini.references import reference_schema
from geomind.tools.gemini.stored import ran_case, save_run

SHOWN_GROUPS = 5
SERVICES = ("heating", "cooling")
POWER_UNIT = "MW"
TEMPERATURE_UNIT = "degC"
REPORT_KEYS = (
    "heat_delivered",
    "cold_delivered",
    "boiler_heat",
    "electricity_bought",
    "gas_bought",
    "capex",
    "opex",
    "lcts",
    "lcoh",
    "lcoc",
    "co2",
    "passed",
    "failed_steps",
)
COVERAGE_KEYS = ("heating_coverage", "cooling_coverage", "cop")
CURVE_STEPS = 400
"""The steps the flows from zero to an ESP's ``maximum_flow`` are checked in (``curve_ranges``)."""


def parse_time(value, field, where):
    """Return an ISO 8601 text as an aware UTC time, a naive one taken as UTC, or ``None``."""
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise ToolError(
            f"{where}: {field} = {value!r}; expected an ISO 8601 time such as '2026-01-28'",
            path=field,
        ) from None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def readable_step(seconds):
    """Return a time step as ``{value, unit}`` in whole days, whole hours or seconds.

    gemini converts (``gm.units.convert``); geomind only picks the unit.
    """
    import gemini as gm

    for unit in ("d", "h"):
        value = gm.units.convert(seconds, "s", unit)
        if float(value).is_integer():
            return {"value": type(seconds)(value), "unit": unit}
    return {"value": seconds, "unit": "s"}


def case_span(case):
    """Return the start, end and step of the case's time, readable."""
    time = case.time
    return {
        "start": time.start.isoformat(),
        "end": time.end.isoformat(),
        "step": readable_step(time.step),
    }


def service_demand(case, service, where):
    """Return ``(Service, column name of the case's demand frame)`` or raise what exists."""
    demand = case.demand
    chosen = getattr(demand, service, None) if demand is not None and service in SERVICES else None
    if chosen is None:
        given = [item for item in SERVICES if demand is not None and getattr(demand, item)]
        raise ToolError(
            f"{where}: service = {service!r}; expected one of {given or 'none'} in the case's "
            "demand. Set it with set_case or save_profile",
            code="unknown_name",
            path="service",
        )
    return chosen, f"{service}_demand"


def temperature(kelvin):
    """Return a temperature in K as ``{value, unit}`` in degrees Celsius; ``None`` when unset.

    A case may leave a return temperature open (the designers' choice); the listing says so.
    """
    import gemini as gm

    if kelvin is None:
        return None
    return gm.units.Quantity(kelvin, "K").to(TEMPERATURE_UNIT).to_dict()


def profile_row(case, service):
    """Return the listing of one service; ``power`` names the file and column of its series."""
    import gemini as gm

    chosen, column = service_demand(case, service, "list_profiles")
    series = case.demand.frame[column]
    peak = gm.units.Quantity(float(series.max()), "W").to(POWER_UNIT)
    return {
        "service": service,
        "power": case.to_dict()["demand"][service]["power"],
        "supply_temperature": temperature(chosen.supply_temperature),
        "return_temperature": temperature(chosen.return_temperature),
        "start": series.index[0].isoformat(),
        "end": series.index[-1].isoformat(),
        "steps": len(series),
        "peak": peak.to_dict(),
    }


@tool(effect="read")
def list_profiles(context):
    """List the demand of the case: its heating and cooling services, with unit, window and peak."""
    case = case_of(context)
    if case.demand is None:
        raise ToolError(
            "list_profiles: the case has no demand; expected one. Set it with set_case or "
            "save_profile, or ask_user",
            path="demand",
        )
    return [profile_row(case, service) for service in SERVICES if getattr(case.demand, service)]


@tool(effect="read")
def read_profile(context, service: str, start: str | None = None, end: str | None = None):
    """Return the demand of a service (heating or cooling) of the case as a series in MW.

    ``start`` and ``end`` are ISO 8601 times, both inclusive. ``summary`` gives the ``peak`` and
    ``minimum`` with their time, the ``mean`` and the ``energy`` of the window, computed by
    gemini's units: take a size from it, never from adding the series by hand.
    """
    import gemini as gm

    case = case_of(context)
    _, column = service_demand(case, service, "read_profile")
    first, last = parse_time(start, "start", "read_profile"), parse_time(end, "end", "read_profile")
    series = case.demand.frame[column].loc[first:last]
    values = [gm.units.convert(float(item), "W", POWER_UNIT) for item in series]
    return {
        "service": service,
        "summary": profile_summary(series.index, values),
        "time": [moment.isoformat() for moment in series.index],
        "value": values,
        "unit": POWER_UNIT,
        "case_time": {**case_span(case), "end_is": "exclusive", "steps": len(case.demand.frame)},
        "file": file_extent(context, service),
    }


def profile_summary(times, values):
    """Return the peak, minimum, mean and energy of a power series in ``POWER_UNIT`` (#71).

    The energy is each value held for its step, the step being the series' own interval.
    """
    import gemini as gm

    if not values:
        return None
    peak = max(range(len(values)), key=values.__getitem__)
    low = min(range(len(values)), key=values.__getitem__)
    seconds = (times[1] - times[0]).total_seconds() if len(times) > 1 else None
    hours = gm.units.convert(seconds, "s", "h") if seconds else None
    energy = sum(values) * hours if hours else None
    return {
        "peak": {"value": values[peak], "time": times[peak].isoformat()},
        "minimum": {"value": values[low], "time": times[low].isoformat()},
        "mean": sum(values) / len(values),
        "energy": {"value": energy, "unit": f"{POWER_UNIT}h"} if energy is not None else None,
        "unit": POWER_UNIT,
    }


def file_extent(context, service):
    """Return the rows of the data file a service's power comes from, its first and last time.

    The series above is the case's demand over the case's time; a file may hold more or fewer
    rows, which this shows. ``None`` when the power names no stored file.
    """
    power = ((context.problem.case or {}).get("demand") or {}).get(service, {}).get("power")
    name = power.get("file") if isinstance(power, dict) else None
    data = context.session.load_artifact(f"{CASE_FILE}{name}") if name else None
    if not isinstance(data, (bytes, str)):
        return None
    text = data.decode() if isinstance(data, bytes) else data
    rows = [line.split(",", 1)[0] for line in text.splitlines()[1:] if line.strip()]
    return {
        "name": name,
        "rows": len(rows),
        "first": rows[0] if rows else None,
        "last": rows[-1] if rows else None,
    }


def planned(plant, case, start, end):
    """Return the plan of a window, ``gm.schedule`` cut to ``start`` and ``end``, else ``None``."""
    import gemini as gm

    first, last = parse_time(start, "start", "simulate"), parse_time(end, "end", "simulate")
    if first is None and last is None:
        return None
    plan = gm.schedule(plant, case).loc[first:last]
    if len(plan) == 0:
        raise ToolError(
            f"simulate: start = {start!r}, end = {end!r}; expected a window inside the case's time "
            f"{case_span(case)['start']} to {case_span(case)['end']}",
            path="start",
        )
    return plan


def cut_to_window(data, plan, step):
    """Return the case dict ``data`` with its time cut to the steps of ``plan``.

    gemini judges a run against the case's time, so a window is a case of its own: the run, its
    report and every later tool of the run read the same steps.
    """
    window = copy.deepcopy(data)
    window["time"]["start"] = plan.index[0].isoformat()
    window["time"]["end"] = (plan.index[-1] + timedelta(seconds=step)).isoformat()
    return window


def quantified(value):
    """Return a value of ``{"value", "unit"}`` as a gemini ``Quantity``, any other as it is."""
    import gemini as gm

    if isinstance(value, dict) and {"value", "unit"} <= value.keys():
        return gm.units.Quantity(value["value"], value["unit"])
    return value


def check_unit_given(plant, path, name, value):
    """Raise when ``value`` is a bare number for a parameter that has a unit."""
    module = plant.get_submodule(path)
    unit = module.describe()["parameters"].get(name, {}).get("unit")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and unit not in (None, "-"):
        raise ToolError(
            f"simulate: changes[{path!r}][{name!r}] = {value!r}; expected "
            f'{{"value": number, "unit": "..."}} since the parameter is in {unit}',
            path="changes",
        )


def apply_changes(plant, changes):
    """Set ``{module path: {parameter: {value, unit}}}`` on the plant, for this run only."""
    for path, params in (changes or {}).items():
        for name, value in params.items():
            check_unit_given(plant, path, name, value)
        plant.set_params(path, {name: quantified(value) for name, value in params.items()})


def negative_ranges(flows, values):
    """Return ``[[first, last], ...]``: the runs of ``flows`` where ``values`` are below zero."""
    ranges, start = [], None
    for index, (flow, value) in enumerate(zip(flows, values, strict=True)):
        if value < 0 and start is None:
            start = flow
        if start is not None and (value >= 0 or index == len(flows) - 1):
            ranges.append([start, flows[index - 1] if value >= 0 else flow])
            start = None
    return ranges


def curve_ranges(module):
    """Return where an ESP's curves are below zero, flows from zero to its ``maximum_flow``.

    Evaluated by gemini's own curves (``head_function`` and ``power_function``) at its reference
    frequency: the sign of the polynomials does not depend on the speed (E2E-15: a curve with a
    negative head at low flows failed 450 of 504 steps, and its message named one flow).
    """
    import gemini as gm
    import numpy as np

    largest = float(module.maximum_flow)
    frequency = float(gm.physics.constants.ESP_REFERENCE_FREQUENCY)
    flows = [float(flow) for flow in np.linspace(0.0, largest, CURVE_STEPS + 1)]
    head = np.asarray(module.head_function(np.asarray(flows), frequency))
    power = np.asarray(module.power_function(np.asarray(flows), frequency))
    return {
        "unit": "m3/s",
        "flows": [0.0, largest],
        "resolution": largest / CURVE_STEPS,
        "negative_head": negative_ranges(flows, head.tolist()),
        "negative_power": negative_ranges(flows, power.tolist()),
    }


def with_curve(plant, group):
    """Return a failure group; an ESP outside its curves also says where the curves are negative."""
    import gemini as gm

    if group.get("code") != "out_of_range" or not group.get("path"):
        return group
    try:
        module = plant.get_submodule(group["path"])
    except AttributeError:
        return group
    if not isinstance(module, gm.modules.ESP):
        return group
    curve = curve_ranges(module)
    said = [
        f"negative {name} at flows "
        + ", ".join(f"{start:.4g} to {end:.4g}" for start, end in curve[f"negative_{name}"])
        for name in ("head", "power")
        if curve[f"negative_{name}"]
    ]
    if not said:
        return {**group, "curve": curve}
    message = (
        f"{group['message']}. The curves give {' and '.join(said)} m3/s of 0 to "
        f"{curve['flows'][1]:.4g} m3/s (maximum_flow): take the curves from their source"
    )
    return {**group, "message": message, "curve": curve}


def run_summary(plant, case, results, label):
    """Return what the model reads of a run: steps, failures, totals in display units."""
    import gemini as gm

    failures = gm.evaluate.failures(results).to_dict()
    report = gm.evaluate.report(plant, case, results).to_dict()
    totals = gm.evaluate.totals(plant, case, results)
    times = results.to_frame().index
    return {
        "plant": label,
        "case_time": case_span(case),
        "window": {"start": times[0].isoformat(), "end": times[-1].isoformat()},
        "steps": len(times),
        "failed_steps": failures["total"],
        "failures": [with_curve(plant, group) for group in failures["groups"][:SHOWN_GROUPS]],
        "report": {key: report[key] for key in REPORT_KEYS if key in report},
        "verdict": report["verdict"],
        "unmet": [item for item in report["requirements"] if item["passed"] is False],
        "coverage": {key: totals[key].to_dict() for key in COVERAGE_KEYS if key in totals},
    }


def run_plant(context, design, changes, start, end):
    """Simulate a plant on the case; return ``(plant, results, summary, options, ran)``.

    ``ran`` is the case dict and files the run read, which ``save_run`` stores.
    """
    import gemini as gm

    plant = load_plant(context, design, "simulate")
    apply_changes(plant, changes)
    data, files = ran_case(context)
    whole = build_case(data, files)
    plan = planned(plant, whole, start, end)
    if plan is not None:
        data = cut_to_window(data, plan, whole.time.step)
    ran = (data, files)
    case = build_case(*ran)
    results = gm.simulate(plant, case, plan=plan)
    summary = run_summary(plant, case, results, design or "project")
    return plant, results, summary, {"start": start, "end": end}, ran


@tool(effect="compute", late_schemas={"design": reference_schema("design", optional=True)})
async def simulate(
    context,
    design: str | None = None,
    changes: dict[str, dict[str, Any]] | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Simulate a plant on the state's case and store the results; return a reference and summary.

    ``design`` is a stored design (``design/<name>``), or the project's plant without one.
    ``changes`` holds parameters by module path for this run only, each a ``{"value", "unit"}``
    (a dimensionless parameter may be a number). ``start`` and ``end`` are ISO 8601 times that cut
    the case's time to a window, both inclusive: the run, its summary and its stored case are those
    of the window (the case's ``time`` cut to it); to change the case's time itself use set_case.

    The plan comes from gemini's schedule over the case. A step that fails is a failed row in the
    summary and the run goes on. What ``gm.check`` finds wrong with the plant on this case (a
    parameter without a value, equipment without a cost in the economics, a role a requirement
    names) is a gemini error with each issue's path and message, and nothing runs.

    The summary gives the steps, the failed steps with their first groups, the report's totals in
    display units (MWh, MEUR, EUR/MWh, kt), gemini's ``verdict``, the requirements that are not met
    (``unmet``), the coverage of the demand, the plant and the case's time span.
    """
    plant, results, summary, options, ran = await runtime.in_gemini_thread(
        run_plant, context, design, changes, start, end
    )
    reference = await save_run(context, plant, results, summary, options, ran)
    return {"reference": reference, "summary": summary}

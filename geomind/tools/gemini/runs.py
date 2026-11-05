"""The tools that read the demand of the case and run a plant on it."""

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.case import CASE_FILE, build_case, case_of
from geomind.tools.gemini.plants import load_plant, project_designs, version_plant
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
    """List the demand of the case: its heating and cooling services, with unit, window and peak.

    Skill `setting-the-case`.
    """
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

    Skill `setting-the-case`.
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


PLANT_LEVEL = ("control", "params.control", "params", "plant")
"""The keys of ``changes`` that name the plant itself: its options, as ``params.control.dispatch``
and ``params.backup`` sit in the plant file (QA-082)."""
PLANT_OPTIONS = ("backup", "dispatch", "outages")
"""The plant's own options; a change may name one as a key with a ``{"value": ...}``."""


def _option(value):
    """Return an option change as gemini takes it: ``{"value": "least_cost"}`` is the text."""
    return value["value"] if isinstance(value, dict) and set(value) == {"value"} else value


def plant_level(changes):
    """Return ``(module changes, plant option changes)`` of a simulate ``changes`` (QA-082).

    ``{"control": {"dispatch": ...}}``, ``{"params": {"backup": ...}}`` or ``{"backup": {"value":
    "none"}}`` set the plant's own options; any other key is a module path.
    """
    modules, options = {}, {}
    for path, params in (changes or {}).items():
        if path in PLANT_LEVEL and isinstance(params, dict):
            inner = params.get("control") if path == "params" and "control" in params else None
            items = {**{k: v for k, v in params.items() if k != "control"}, **(inner or {})}
            options |= {name: _option(value) for name, value in items.items()}
        elif path in PLANT_OPTIONS and isinstance(params, dict) and "value" in params:
            options[path] = _option(params)
        else:
            modules[path] = params
    return modules, options


def apply_changes(plant, changes):
    """Set ``{module path: {parameter: {value, unit}}}`` on the plant, for this run only.

    The plant's own options (``control.dispatch``, ``control.outages``, ``backup``) are set
    from a ``control``, ``params`` or option key (QA-082: the agent could not set them).
    """
    modules, options = plant_level(changes)
    if options:
        plant.set_params("", options)
    for path, params in modules.items():
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
    try:
        curve = curve_ranges(module)
    except gm.errors.ValidationError:
        # NOTE: the plant here holds the plant file's values only (the case is applied to the
        # run's own copy); reading a curve it lacks raised gemini's whole-plant "uninitialized
        # parameters" error, which listed the case's values as missing and failed a simulate
        # that had run (QA-082). The group is then given without the curve.
        return group
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


def explained_report(report):
    """Return a report dict whose requirements with no value say why when steps failed (QA-104).

    A figure of the whole period (``unmet_share``) has no value when any step failed, and gemini
    says only "no value"; the Results page showed that as a missing rule. The reason now names
    the failed steps, which are what to fix.
    """
    failed = report.get("failed_steps") or 0
    if not failed:
        return report
    reason = (
        f"no value: {failed} steps of the run failed, so the run holds no figure for the whole "
        "period; fix the failed steps (failures) first"
    )
    items = []
    for item in report.get("requirements") or ():
        value = item.get("value")
        if isinstance(value, dict) and value.get("value") is None and value.get("reason") == "no value":
            item = {**item, "value": {**value, "reason": reason}}
        items.append(item)
    return {**report, "requirements": items}


def run_summary(plant, case, results, label):
    """Return what the model reads of a run: steps, failures, totals in display units."""
    import gemini as gm

    failures = gm.evaluate.failures(results).to_dict()
    report = explained_report(gm.evaluate.report(plant, case, results).to_dict())
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


def single_choices(plant):
    """Fill each plant-level choice that is unset and that gemini allows exactly one value of.

    Returns the notes, one per value set. IMP-019 (user-approved): such a value is no choice and
    no default, gemini allows nothing else (``params.control.dispatch`` = ``least_cost``,
    ``params.control.outages`` = ``lowest_demand``). When gemini allows more than one, nothing is
    filled and the agent must choose.
    """
    from gemini.modules._utils import description
    from gemini.plants._utils.form import file_path

    notes = []
    for name, declaration in plant.named_parameters():
        if "." in name or getattr(plant, name, None) is not None:
            continue
        options = [item for item in (description._enum(declaration) or []) if item is not None]
        if len(options) == 1:
            plant.set_params("", {name: options[0]})
            notes.append(
                f"params.{file_path(name)} was unset; set to {options[0]!r}, the only value "
                "gemini allows"
            )
    return notes


def simulated_plant(context, design, plant_version):
    """Return ``(plant, label)`` of what ``simulate`` runs: a design, a plant version or the latest.

    Without either, the project's plant file is its LATEST plant version; the label says which,
    so an agent that read version 1 never reports a run of version 2 as version 1 (QA-166).
    """
    if design is not None and plant_version is not None:
        raise ToolError(
            f"simulate: design = {design!r} and plant_version = {plant_version}; expected one "
            "of them, not both",
            path="plant_version",
        )
    if plant_version is not None:
        return version_plant(context, "simulate", plant_version), f"plant version {plant_version}"
    plant = load_plant(context, design, "simulate")
    if design is not None:
        return plant, design
    versions = [item.get("version") for item in project_designs(context)["plants"]]
    versions = [item for item in versions if isinstance(item, int)]
    if not versions:
        return plant, "project"
    return plant, f"plant version {max(versions)} (the project's latest)"


def run_plant(context, design, changes, start, end, plant_version=None):
    """Simulate a plant on the case; return ``(plant, results, summary, options, ran)``.

    ``ran`` is the case dict and files the run read, which ``save_run`` stores.
    """
    import gemini as gm

    plant, label = simulated_plant(context, design, plant_version)
    apply_changes(plant, changes)
    filled = single_choices(plant)
    data, files = ran_case(context)
    whole = build_case(data, files)
    plan = planned(plant, whole, start, end)
    if plan is not None:
        data = cut_to_window(data, plan, whole.time.step)
    ran = (data, files)
    case = build_case(*ran)
    results = gm.simulate(plant, case, plan=plan)
    summary = run_summary(plant, case, results, label)
    if filled and isinstance(summary, dict):
        summary = {**summary, "filled": filled}
    return plant, results, summary, {"start": start, "end": end}, ran


@tool(effect="compute", late_schemas={"design": reference_schema("design", optional=True)})
async def simulate(
    context,
    design: str | None = None,
    changes: dict[str, dict[str, Any]] | None = None,
    start: str | None = None,
    end: str | None = None,
    plant_version: int | None = None,
):
    """Simulate a plant on the state's case and store the results; return a reference and summary.

    ``design`` a stored design, ``plant_version`` a saved plant version of the project
    (``list_plants`` project_versions); neither runs the project's latest plant version.
    Skill `simulating-a-plant`.
    """
    plant, results, summary, options, ran = await runtime.in_gemini_thread(
        run_plant, context, design, changes, start, end, plant_version
    )
    reference = await save_run(context, plant, results, summary, options, ran)
    return {"reference": reference, "summary": summary}

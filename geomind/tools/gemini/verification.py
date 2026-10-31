"""Verification of a design against a brief, built only from gemini's checks.

The checks are gemini's: ``gm.checks.run_all``, ``gm.checks.plant_balance`` and
``gm.checks.limits`` over the limits the brief gives. More come from the plant's structure and the
run's failed rows, in gemini's Check shape: the number of doublets, a heating and a cooling grid
for the demand the brief gives, the failed days, and whether the co-produced gas reaches a burner.
NOTE: the base design must meet the demand without the co-produced methane; burning it is a
separate scenario, never the base. A limit the brief does not give is listed under ``not_given``,
never checked or passed; what gemini cannot judge yet is listed under ``not_assessed``.
"""

from geomind.context import preset
from geomind.errors import ToolError
from geomind.tools.gemini.brief import FALLBACK, TOLERANCE, schedule_rules, si, text

HEATING_GRID = "HeatingGrid"
COOLING_GRID = "CoolingGrid"
DOUBLET = "Doublet"
WHOLE_PLANT = {"energy_balance", "mass_balance", "bounds", "failed_days"}
UNMET = ("unmet_demand", "unmet_sensible", "unmet_latent")
DEGASSER = "Degasser"
BURNERS = {"GasMakeup", "Boiler", "CHP"}
LIMITS = (
    "demand",
    "doublets",
    "doublet_flow",
    "max_brine_cooling",
    "heating.supply",
    "cooling.supply",
    "operating_days",
    "pump_efficiency",
    "volume_balance",
)
"""The limits a brief can give, by the name ``not_given`` lists them under."""


def module_types(plant):
    """Return ``{path: type}`` of the plant's modules, groups opened, from its spec."""
    found = {}
    pending = list(plant.to_dict()["modules"].items())
    while pending:
        path, entry = pending.pop(0)
        found[path] = entry["type"]
        children = entry.get("modules", {}) if entry["type"] in ("ModuleDict", "ModuleList") else {}
        pending.extend((f"{path}.{name}", child) for name, child in children.items())
    return found


def paths_of(types, kind):
    """Return the paths of one module type, in plant order."""
    return [path for path, found in types.items() if found == kind]


def bounds(span, unit, tolerance):
    """Return ``(min, max)`` of a span of amounts in ``unit``, widened by ``tolerance``."""
    low = si(span.min, unit) - tolerance if span.min is not None else None
    high = si(span.max, unit) + tolerance if span.max is not None else None
    return low, high


def doublet_limits(limits, path, brief):
    """Add the flow and brine-cooling limits the brief gives to one doublet."""
    span = brief.doublet_flow
    if span is not None and (span.min, span.max) != (None, None):
        low, high = bounds(span, "m3/s", TOLERANCE["volume_flow"])
        limits.add(f"{path}.flow", min=low, max=high)
    if brief.max_brine_cooling is not None:
        cooling = si(brief.max_brine_cooling, "K") + TOLERANCE["temperature"]
        limits.add(f"{path}.brine_cooling", max=cooling)


def grid_limits(limits, path, network, unmet):
    """Add the fixed supply temperature the brief gives, and the met demand, to one grid."""
    if network is not None and network.supply is not None:
        fixed, tolerance = si(network.supply, "K"), TOLERANCE["temperature"]
        limits.add(f"{path}.supply_in.temperature", min=fixed - tolerance, max=fixed + tolerance)
    for output in unmet:
        limits.add(f"{path}.{output}", max=TOLERANCE["power"])


def challenge_limits(plant, brief):
    """Return ``gm.checks.Limits`` of the brief's limits for the plant's doublets and grids.

    The demand must be met on every day of every grid, whatever the brief gives.
    """
    import gemini as gm

    types = module_types(plant)
    limits = gm.checks.Limits()
    for path in paths_of(types, DOUBLET):
        doublet_limits(limits, path, brief)
    for kind, network, unmet in (
        (HEATING_GRID, brief.heating, UNMET[:1]),
        (COOLING_GRID, brief.cooling, UNMET[1:]),
    ):
        for path in paths_of(types, kind):
            grid_limits(limits, path, network, unmet)
    return limits


def check(name, passed, value, limit, unit="-"):
    """Return a Check in gemini's shape, for a count gemini gives but does not judge."""
    return {
        "name": name,
        "passed": passed,
        "value": {"value": value, "unit": unit},
        "limit": {"value": limit, "unit": unit},
    }


def burned_gas(plant, types):
    """Return how many burners the co-produced gas reaches: a degasser's ``gas_out`` feeding one."""
    sources = {f"{path}.gas_out" for path in paths_of(types, DEGASSER)}
    targets = [
        item["target"].split(".")[0]
        for item in plant.to_dict()["connections"]
        if item["source"] in sources
    ]
    return sum(types.get(target) in BURNERS for target in targets)


def grid_check(name, types, kind):
    """Return the check that the plant has at least one grid of ``kind``."""
    count = len(paths_of(types, kind))
    return check(name, count > 0, count, [1, None])


def structure_checks(plant, types, results, brief):
    """Return the checks of the doublet count and the grids the brief gives, and the failed days."""
    count = len(paths_of(types, DOUBLET))
    failed = len(results.errors())
    burned = burned_gas(plant, types)
    checks = []
    if brief.doublets is not None:
        low, high = brief.doublets.min, brief.doublets.max
        passed = (low is None or count >= low) and (high is None or count <= high)
        checks.append(check("doublets", passed, count, [low, high]))
    demand = brief.demand
    if demand is not None and demand.heating:
        checks.append(grid_check("heating_grid", types, HEATING_GRID))
    if demand is not None and demand.cooling:
        checks.append(grid_check("cooling_grid", types, COOLING_GRID))
    checks.append(check("failed_days", failed == 0, failed, 0))
    checks.append(check("co_produced_gas_burned", burned == 0, burned, 0))
    return checks


def operating_days_reason(plant, brief):
    """Return why the brief's operating days cannot be checked: gemini's own message."""
    import gemini as gm

    demand = gm.profiles.get(gm.profiles.names()[0]).iloc[:1]
    try:
        rules = schedule_rules(brief, "check_results")
        gm.schedule(plant, demand, {**rules, "operating_days": brief.operating_days})
    except gm.errors.NotImplementedYet as error:
        return "BLOCKED", f"gm.schedule raises NotImplementedYet: {error}"
    except (gm.errors.GeminiError, ToolError) as error:
        return "BLOCKED", f"gm.schedule refused operating_days = {brief.operating_days}: {error}"
    return "NOT_ASSESSED", "gm.schedule takes operating_days now; geomind does not check it yet"


def return_items(brief):
    """Return the return temperatures the brief gives, as not assessed: they are design inputs."""
    items = []
    for name, network in (("heating", brief.heating), ("cooling", brief.cooling)):
        if network is None or network.return_temperature is None:
            continue
        items.append(
            {
                "id": f"{name}.return_temperature",
                "status": "NOT_ASSESSED",
                "reason": "a return temperature is a design input of the grid, not an output "
                "gemini's limits check; the design must set it to the brief's value",
                "limit": text(network.return_temperature),
            }
        )
    return items


def not_assessed(plant, types, brief):
    """Return the brief's limits gemini cannot judge yet, each with its status and reason."""
    items = []
    if brief.operating_days is not None:
        status, reason = operating_days_reason(plant, brief)
        limit = f"{brief.operating_days} days"
        items.append({"id": "operating_days", "status": status, "reason": reason, "limit": limit})
    if brief.volume_balance:
        items.append(
            {
                "id": "volume_balance",
                "status": "NOT_ASSESSED",
                "reason": "no gemini output gives the produced minus the injected liquid volume "
                "of a doublet (gemini request 5)",
                "limit": "equal volumes",
            }
        )
    if brief.pump_efficiency is not None:
        efficiency = {
            path: plant.params_at(path).get("pump_efficiency") for path in paths_of(types, DOUBLET)
        }
        items.append(
            {
                "id": "pump_efficiency",
                "status": "NOT_ASSESSED",
                "reason": "gm.checks.Limits checks outputs, and the pump efficiency is a "
                "parameter (gemini request 6); the value is the design's",
                "limit": text(brief.pump_efficiency),
                "value": efficiency,
            }
        )
    return items + return_items(brief)


def not_given(brief):
    """Return the names of the limits the brief does not give: none of them is checked."""
    flow = brief.doublet_flow
    given = {
        "demand": brief.demand is not None and bool(brief.demand.heating or brief.demand.cooling),
        "doublets": brief.doublets is not None,
        "doublet_flow": flow is not None and (flow.min, flow.max) != (None, None),
        "max_brine_cooling": brief.max_brine_cooling is not None,
        "heating.supply": brief.heating is not None and brief.heating.supply is not None,
        "cooling.supply": brief.cooling is not None and brief.cooling.supply is not None,
        "operating_days": brief.operating_days is not None,
        "pump_efficiency": brief.pump_efficiency is not None,
        "volume_balance": brief.volume_balance is not None,
    }
    return [name for name in LIMITS if not given[name]]


def domain_of(name, types):
    """Return the domain of a check: ``subsurface``, ``surface``, ``sizing`` or ``coupled``.

    Doublets and their wells are subsurface, unmet demand is sizing (the topology works, the sizes
    do not), every other module is surface, and the whole plant is coupled.
    """
    if name == "doublets":
        return "subsurface"
    if name in ("heating_grid", "cooling_grid", "co_produced_gas_burned"):
        return "surface"
    if name in WHOLE_PLANT or name.startswith("plant "):
        return "coupled"
    if name.endswith(UNMET):
        return "sizing"
    top = name.split(" ")[0].split(".")[0]
    return "subsurface" if types.get(top) == DOUBLET else "surface"


def unjudged(item, reason):
    """Return the check of a limit with nothing to judge, saying why."""
    return {
        "name": f"{item['pattern']}.{item['output']}",
        "passed": None,
        "value": {"value": None, "unit": "-", "reason": reason},
        "limit": {"value": [item["min"], item["max"]], "unit": "-"},
    }


def limit_checks(plant, results, limits):
    """Return one check per limit; a limit the results cannot judge has ``passed`` ``None``.

    NOTE: ``gm.checks.limits`` raises when an output has no column, and a bare ``KeyError`` on a
    run with no rows at all (gemini request 17). Each limit is judged alone, so one missing column
    does not hide the others, and a run where every day failed is not judged at all: its
    ``failed_days`` check fails it.
    """
    import gemini as gm

    if not results.names():
        return [
            unjudged(item, "the run has no rows: every day failed") for item in limits["limits"]
        ]
    checks = []
    for item in limits["limits"]:
        try:
            checks += gm.checks.limits(
                plant, results, gm.checks.Limits.from_dict({"limits": [item]})
            )
        except gm.errors.ValidationError as error:
            checks.append(unjudged(item, str(error)))
    return checks


def assess(plant, results, limits=None, brief=None, source=None):
    """Return ``{passed, checks, failures, not_assessed, not_given, brief}`` of a plant and its run.

    ``brief`` gives the limits; without one, the ``hackathon_2027`` preset does, as before briefs
    were data, and ``brief`` of the result says so. ``limits`` (``Limits.to_dict()``) are checked
    beside the brief's, never instead of them. A check whose ``passed`` is ``None`` had nothing to
    judge and does not fail the design.
    """
    import gemini as gm

    if brief is None:
        brief, source = preset(FALLBACK), f"no brief in the state: the {FALLBACK} preset"
    types = module_types(plant)
    merged = challenge_limits(plant, brief).to_dict()
    merged["limits"] += (limits or {}).get("limits", [])
    checks = [
        *gm.checks.run_all(plant, results)["checks"],
        *gm.checks.plant_balance(plant, results),
        *limit_checks(plant, results, merged),
        *structure_checks(plant, types, results, brief),
    ]
    failures = [
        {"name": item["name"], "domain": domain_of(item["name"], types)}
        for item in checks
        if item["passed"] is False
    ]
    return {
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "not_assessed": not_assessed(plant, types, brief),
        "not_given": not_given(brief),
        "brief": source or f"the brief ({brief.source or 'no source'})",
    }

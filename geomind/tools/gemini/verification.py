"""Verification of a design against the brief, built only from gemini's checks.

The checks are gemini's: ``gm.checks.run_all``, ``gm.checks.plant_balance`` and
``gm.checks.limits`` over the brief's hard limits. Five more come from the plant's structure and the
run's failed rows, in gemini's Check shape: the number of doublets, a heating and a cooling grid,
the failed days, and whether the co-produced gas reaches a burner. NOTE: the base design must meet
the demand without the co-produced methane; burning it is a separate scenario, never the base. What
gemini cannot judge yet is listed under ``not_assessed``, never passed.
"""

from geomind.tools.gemini import brief
from geomind.tools.gemini.brief import TOLERANCE

HEATING_GRID = "HeatingGrid"
COOLING_GRID = "CoolingGrid"
DOUBLET = "Doublet"
WHOLE_PLANT = {"energy_balance", "mass_balance", "bounds", "failed_days"}
UNMET = ("unmet_demand", "unmet_sensible", "unmet_latent")
DEGASSER = "Degasser"
BURNERS = {"GasMakeup", "Boiler", "CHP"}


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


def si(amount):
    """Return a ``(value, unit)`` of the brief in SI, through ``gm.units``."""
    import gemini as gm

    value, unit = amount
    target = {"m3/h": "m3/s", "degC": "K", "K": "K"}[unit]
    return gm.units.convert(value, unit, target)


def challenge_limits(plant):
    """Return ``gm.checks.Limits`` of the brief's hard limits for the plant's doublets and grids."""
    import gemini as gm

    types = module_types(plant)
    limits = gm.checks.Limits()
    low, high = (si(flow) for flow in brief.DOUBLET_FLOW)
    for path in paths_of(types, DOUBLET):
        tolerance = TOLERANCE["volume_flow"]
        limits.add(f"{path}.flow", min=low - tolerance, max=high + tolerance)
        limits.add(
            f"{path}.brine_cooling", max=si(brief.MAX_BRINE_COOLING) + TOLERANCE["temperature"]
        )
    for kind, supply, unmet in (
        (HEATING_GRID, brief.HEATING_SUPPLY, UNMET[:1]),
        (COOLING_GRID, brief.COOLING_SUPPLY, UNMET[1:]),
    ):
        for path in paths_of(types, kind):
            fixed, tolerance = si(supply), TOLERANCE["temperature"]
            limits.add(
                f"{path}.supply_in.temperature", min=fixed - tolerance, max=fixed + tolerance
            )
            for output in unmet:
                limits.add(f"{path}.{output}", max=TOLERANCE["power"])
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


def structure_checks(plant, types, results):
    """Return the checks of the doublet count, the two grids and the failed days."""
    count = len(paths_of(types, DOUBLET))
    low, high = brief.DOUBLETS
    failed = len(results.errors())
    return [
        check("doublets", low <= count <= high, count, [low, high]),
        check(
            "heating_grid",
            bool(paths_of(types, HEATING_GRID)),
            len(paths_of(types, HEATING_GRID)),
            [1, None],
        ),
        check(
            "cooling_grid",
            bool(paths_of(types, COOLING_GRID)),
            len(paths_of(types, COOLING_GRID)),
            [1, None],
        ),
        check("failed_days", failed == 0, failed, 0),
        check("co_produced_gas_burned", burned_gas(plant, types) == 0, burned_gas(plant, types), 0),
    ]


def operating_days_reason(plant):
    """Return why the 330 operating days cannot be checked: gemini's own message, when it raises."""
    import gemini as gm

    demand = gm.profiles.get("heating_demand").iloc[:1]
    try:
        gm.schedule(plant, demand, {**brief.SCHEDULE_RULES, "operating_days": 330})
    except gm.errors.NotImplementedYet as error:
        return "BLOCKED", f"gm.schedule raises NotImplementedYet: {error}"
    except gm.errors.GeminiError as error:
        return "BLOCKED", f"gm.schedule refused operating_days = 330: {error}"
    return "NOT_ASSESSED", "gm.schedule takes operating_days now; geomind does not check it yet"


def not_assessed(plant, types):
    """Return the brief's limits gemini cannot judge yet, each with its status and reason."""
    status, reason = operating_days_reason(plant)
    efficiency = {
        path: plant.params_at(path).get("pump_efficiency") for path in paths_of(types, DOUBLET)
    }
    return [
        {"id": "operating_days", "status": status, "reason": reason, "limit": "330 days"},
        {
            "id": "volume_balance",
            "status": "NOT_ASSESSED",
            "reason": "no gemini output gives the produced minus the injected liquid volume of a "
            "doublet (gemini request 5)",
            "limit": "equal volumes",
        },
        {
            "id": "pump_efficiency",
            "status": "NOT_ASSESSED",
            "reason": "gm.checks.Limits checks outputs, and the pump efficiency is a parameter "
            "(gemini request 6); the value is the design's",
            "limit": brief.PUMP_EFFICIENCY,
            "value": efficiency,
        },
    ]


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


def assess(plant, results, limits=None):
    """Return ``{passed, checks, failures, not_assessed}`` of a plant and its run.

    ``limits`` (``Limits.to_dict()``) are checked beside the brief's, never instead of them. A
    check whose ``passed`` is ``None`` had nothing to judge and does not fail the design.
    """
    import gemini as gm

    types = module_types(plant)
    merged = challenge_limits(plant).to_dict()
    merged["limits"] += (limits or {}).get("limits", [])
    checks = [
        *gm.checks.run_all(plant, results)["checks"],
        *gm.checks.plant_balance(plant, results),
        *limit_checks(plant, results, merged),
        *structure_checks(plant, types, results),
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
        "not_assessed": not_assessed(plant, types),
    }

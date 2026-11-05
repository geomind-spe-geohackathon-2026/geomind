"""Every value a plant still needs, from each stage of gemini's checks at once (QA-175, QA-171).

gemini checks a plant a stage at a time: the design values of a doublet once its depth is set,
the supply setpoints only when it schedules, the simulation inputs and tear streams only when it
runs. A design lead then patched once per stage, 6 or 7 times for one plant. These functions
name the later stages' values beside the earlier ones, so one patch fills them all.
"""

import copy

PROBE_SETPOINTS = {"heating": 333.15, "cooling": 280.15, "cooler": 303.15}
"""The supply setpoints [K] a probe copy of the plant gets, only to reach the run's checks."""
RUN_CODES = ("missing_value", "missing_assumption", "invalid_binding")
"""The codes of a probe run's issues that name a value the plant lacks, not a probe value."""


def doublet_issues(plant, found):
    """Return a ``missing`` issue for each design value of a doublet that gemini asks only later.

    gemini asks the flow path and pump values of a doublet (``well_diameter``, ``nominal_flow``,
    ``pump_efficiency``, ``nominal_wellhead_pressure`` ...) only once its depth group is complete.
    They are named with the rest when gemini already asks a design value of that doublet (its
    depth): a doublet whose child values are stated by hand needs none.
    """
    from gemini.plants._utils import doublet_design
    from gemini.plants.doublet import Doublet

    known = {issue.get("path") for issue in found}
    params = plant.to_dict(structure=True)["params"]
    names = (*doublet_design.COLUMN, *doublet_design.FLOW_PATH, *doublet_design.PUMP)
    issues = []
    for path, module in plant.named_modules():
        prefix = f"params.{path}."
        if not isinstance(module, Doublet) or not known & {f"{prefix}{name}" for name in names}:
            continue
        parameters = module.describe()["parameters"]
        stated = params.get(path) or {}
        for name in (*doublet_design.FLOW_PATH, *doublet_design.PUMP):
            if name not in parameters or f"{prefix}{name}" in known:
                continue
            value = stated.get(name)
            if (value.get("value") if isinstance(value, dict) else value) is not None:
                continue
            issues.append(design_issue(path, name, parameters[name]))
    return issues


def design_issue(path, name, parameter):
    """Return the ``missing`` issue of the design value ``name`` of the doublet at ``path``."""
    item = {
        "path": f"params.{path}.{name}",
        "code": "missing_value",
        "kind": "missing",
        "message": (
            f"no value: {parameter['description']}; the doublet's design needs it with its depth, "
            "or give its child values by hand"
        ),
    }
    if parameter.get("unit"):
        item["units"] = parameter["unit"]
    return item


def setpoint_paths(plant):
    """Return ``{module path: role}`` of the units whose supply setpoint gemini's schedule reads.

    Every heating unit, the cooling unit that ends the chilled water chain, the compression
    chiller, and the cooler of its condenser (role ``cooler``).
    """
    from gemini.engine.schedule import fleet
    from gemini.engine.schedule import schedule as planner
    from gemini.modules.grids import CoolingGrid
    from gemini.modules.heating import Boiler, ElectricBoiler

    heating = (
        fleet.heat_pumps(plant)[0],
        planner._single(plant, Boiler)[0],
        planner._single(plant, ElectricBoiler)[0],
    )
    roles = {path: "heating" for path in heating if path is not None}
    units = fleet.cooling_units(plant)
    if units:
        grid = planner._single(plant, CoolingGrid)[0]
        roles[planner._in_series(plant, grid, list(units.values()))[-1]] = "cooling"
    compression = units.get("compression")
    if compression is not None:
        roles[compression] = "cooling"
        target = plant.target_of(f"{compression}.sink_out")
        if target:
            roles[target.rpartition(".")[0]] = "cooler"
    return roles


def setpoint_issues(plant, case):
    """Return ``(issues, roles)``: a ``missing`` issue for each setpoint the schedule lacks.

    The setpoints are read as the schedule reads them, on the plant with the case's values set:
    a case may give the supply temperature a unit follows.
    """
    from gemini.engine.apply import apply_case
    from gemini.errors import ValidationError

    try:
        plant = apply_case(plant, case)
        roles = setpoint_paths(plant)
    except ValidationError:
        return [], {}
    issues, lacking = [], {}
    for path, role in roles.items():
        name = f"{path}.temperature_setpoint"
        if plant.input_value(name) is not None:
            continue
        lacking[path] = role
        issues.append(
            {
                "path": f"params.{name}",
                "code": "missing_value",
                "kind": "missing",
                "message": (
                    f"no value: the {role} supply setpoint the schedule reads; give it, or a "
                    "supply_margin on a unit of the supply line"
                ),
                "units": "degC|K",
            }
        )
    return issues, lacking


def probe_plant(plant, lacking):
    """Return a copy of ``plant`` with a stand-in setpoint at each unit of ``lacking``."""
    import gemini as gm

    data = copy.deepcopy(plant.to_dict(structure=True))
    for path, role in lacking.items():
        node = data["params"]
        for part in path.split("."):
            node = node.setdefault(part, {})
        node["temperature_setpoint"] = {"value": PROBE_SETPOINTS[role], "unit": "K"}
    return gm.Plant.from_dict(data)


def lacking_values(issues):
    """Return the issues of a probe run that name a value the plant lacks, not a stand-in."""
    return [
        issue
        for issue in issues
        if issue["code"] in RUN_CODES or "first guess" in issue["message"]
    ]


def later_issues(plant, found, case=None):
    """Return ``(issues, probe)``: what gemini asks at later stages, and a plant to run on.

    ``found`` are the issues of gemini's check; the setpoints are named only against a ``case``.
    ``probe`` is a copy of the plant with a stand-in for each missing setpoint, so a run reaches
    its own checks; ``None`` when none is missing. A gemini without the schedule helpers read here
    gives no later issues.
    """
    try:
        doublets = doublet_issues(plant, found)
        setpoints, lacking = setpoint_issues(plant, case) if case is not None else ([], {})
    except (ImportError, AttributeError):
        return [], None
    known = {issue.get("path") for issue in found}
    issues = [issue for issue in doublets + setpoints if issue["path"] not in known]
    return issues, (probe_plant(plant, lacking) if lacking else None)

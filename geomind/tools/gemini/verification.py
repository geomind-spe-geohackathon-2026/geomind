"""Verification of a design: gemini's verdict decides, geomind routes each reason to an agent.

The pass or fail, the reasons, the requirements and the numbers are gemini's (``gm.evaluate``).
What geomind adds is the domain of a reason, the agent that should fix it: ``subsurface``,
``sizing``, ``surface`` or ``coupled``.
"""

SUBSURFACE_ROLE = "doublet"
SIZING_ROLES = ("heating_supply", "cooling_supply")
COUPLED = "coupled"
METRIC_EXCLUDED = ("requirements", "passed", "verdict", "failures", "services")


def role_domain(role):
    """Return the domain that fixes a failed ``role`` of ``gm.plants.roles()``.

    The doublets are subsurface. A supply that does not meet its temperature or its demand is
    sizing (the topology works, the sizes do not). Every other role is surface.
    """
    if role == SUBSURFACE_ROLE:
        return "subsurface"
    return "sizing" if role in SIZING_ROLES else "surface"


def unit_roles(requirements):
    """Return ``{unit path: role}`` of the units that the requirement checks of a report name."""
    return {item["unit_path"]: item["role"] for item in requirements if item.get("unit_path")}


def requirement_roles(case):
    """Return ``{name: role}`` of the requirements of a case: the ``on`` of each."""
    return {requirement.name: requirement.on for requirement in case.requirements}


def domain_of(item, roles, named=None):
    """Return the domain of one reason of gemini's verdict, or of one of its failure groups.

    A requirement reason names its ``role`` (the ``on`` of the requirement, also read in ``named``,
    ``{requirement name: role}``). Any other reason, and a failure group, names the ``path`` of the
    unit it lies in, routed by that unit's role in ``roles``; a numerical reason, or a path in no
    unit of a known role, is ``coupled``.
    """
    if item.get("kind") == "numerical":
        return COUPLED
    role = item.get("role") or (named or {}).get(item.get("name"))
    if role is not None:
        return role_domain(role)
    role = roles.get(str(item.get("path", "")).split(".")[0])
    return COUPLED if role is None else role_domain(role)


def displayed(report, values):
    """Return ``values`` (``{name: Value}``) as plain JSON in the display units of ``report``.

    Only a gemini ``Report`` knows its display table (MWh, MW, MEUR, EUR/MWh, kt), also for the
    parts of a value, so the values are shown by a report of the same type.
    """
    return type(report)(values).to_dict()


def assess(plant, case, results):
    """Return gemini's verdict on a run: ``{feasible, reasons, requirements, failures, metrics}``.

    ``feasible`` and ``reasons`` are ``gm.evaluate.verdict`` (each reason has a ``kind``:
    ``requirement``, ``failed_step``, ``numerical`` or ``bound``),
    ``requirements`` the checks of the
    report with the unit and role of each, ``failures`` the failed and skipped rows by module and
    code, and ``metrics`` the rest of the report. All is in display units.
    """
    import gemini as gm

    report = gm.evaluate.report(plant, case, results)
    verdict = gm.evaluate.verdict(plant, case, results)
    shown = displayed(report, {**report, "verdict": verdict})
    return {
        "feasible": verdict["feasible"],
        "reasons": shown["verdict"]["reasons"],
        "requirements": shown["requirements"],
        "failures": shown["failures"],
        "metrics": {name: item for name, item in shown.items() if name not in METRIC_EXCLUDED},
    }

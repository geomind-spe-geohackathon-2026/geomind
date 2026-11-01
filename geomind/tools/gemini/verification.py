"""Verification of a design: gemini's report decides, geomind routes each failure to an agent.

Every check, balance and number is gemini's (``gm.evaluate``). What geomind adds is the domain of
a failure, the agent that should fix it: ``subsurface``, ``sizing``, ``surface`` or ``coupled``.
"""

SUBSURFACE_ROLE = "doublet"
SIZING_ROLES = ("heating_supply", "cooling_supply")
COUPLED = "coupled"
METRIC_EXCLUDED = ("constraints", "passed", "failures")


def role_domain(role):
    """Return the domain that fixes a failed ``role`` of ``gm.case.roles()``.

    The doublets are subsurface. A supply that does not meet its temperature or its demand is
    sizing (the topology works, the sizes do not). Every other role is surface.
    """
    if role == SUBSURFACE_ROLE:
        return "subsurface"
    return "sizing" if role in SIZING_ROLES else "surface"


def unit_roles(constraints):
    """Return ``{unit path: role}`` of the units that the constraint checks of a report name."""
    return {item["unit_path"]: item["role"] for item in constraints if item.get("unit_path")}


def domain_of(item, roles):
    """Return the domain of a failed constraint check, balance or failure group of gemini.

    A constraint check names its ``role``. A failure group names a module
    ``path``, routed by the role of the unit it lies in; a balance, or a path in no unit of a
    constrained role, is ``coupled``.
    """
    if "role" in item:
        return role_domain(item["role"])
    role = roles.get(str(item.get("path", "")).split(".")[0])
    return COUPLED if role is None else role_domain(role)


def plain(check):
    """Return a gemini check with its values as ``{value, unit}`` JSON."""
    return {
        key: item.to_dict() if hasattr(item, "to_dict") else item for key, item in check.items()
    }


def displayed(report, values):
    """Return ``values`` (``{name: Value}``) as plain JSON in the display units of ``report``.

    Only a gemini ``Report`` knows its display table (MWh, MW, MEUR, EUR/MWh, kt), also for the
    parts of a value, so the values are shown by a report of the same type.
    """
    return type(report)(values).to_dict()


def balances(plant, case, results):
    """Return gemini's ledger checks and the plant balance as plain checks.

    The plant balance holds one check per module and equation; only the failed ones are listed.
    """
    import gemini as gm

    evaluate = gm.evaluate
    ledgers = [
        plain(check)
        for check in (
            evaluate.energy_balance(plant, case, results),
            evaluate.mass_balance(plant, case, results),
            evaluate.bounds(plant, case, results),
        )
    ]
    modules = [plain(check) for check in evaluate.plant_balance(plant, case, results)]
    return [*ledgers, *(check for check in modules if check["passed"] is False)]


def assess(plant, case, results):
    """Return gemini's verdict on a run: ``{passed, constraints, failures, balances, metrics}``.

    ``constraints`` are the checks of the case's constraints and of the services' supply
    temperatures, ``failures`` the failed and skipped rows of the run by module and code,
    ``balances`` the ledgers and the plant balance, and ``metrics`` the rest of the report in
    display units. ``passed`` is true when no constraint, balance or step failed and gemini could
    judge at least one constraint.
    """
    import gemini as gm

    shown = gm.evaluate.report(plant, case, results).to_dict()
    constraints, failures, judged = shown["constraints"], shown["failures"], shown["passed"]
    metrics = {name: item for name, item in shown.items() if name not in METRIC_EXCLUDED}
    checks = balances(plant, case, results)
    sound = metrics["failed_steps"] == 0 and all(check["passed"] is not False for check in checks)
    return {
        "passed": judged is True and sound,
        "constraints": constraints,
        "failures": failures,
        "balances": checks,
        "metrics": metrics,
    }


def failed_checks(found):
    """Return the failed items of ``assess``: constraint checks, balances and failure groups."""
    constraints = [item for item in found["constraints"] if item["passed"] is False]
    balances_failed = [item for item in found["balances"] if item["passed"] is False]
    return constraints, balances_failed, found["failures"]["groups"]

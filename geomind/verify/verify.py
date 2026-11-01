"""Verify a run of a design on its case: gemini's report decides, the failures get a domain."""

from geomind.tools.gemini.verification import assess, domain_of, failed_checks, unit_roles


def amount(item):
    """Return a gemini ``{value, unit}`` as text."""
    return f"{item.get('value')} {item.get('unit', '')}".strip()


def check_detail(check):
    """Return what a failed check measured against its limit, as text."""
    return f"{amount(check['value'])} against {amount(check['limit'])}"


def group_detail(group):
    """Return a failure group of gemini's rows as text."""
    return f"{group['count']} {group['kind']} steps, {group['code']}: {group['message']}"


def failure_items(found):
    """Return ``[{name, domain, detail}]`` of everything that failed in an ``assess`` result."""
    roles = unit_roles(found["constraints"])
    constraints, balances, groups = failed_checks(found)
    items = [
        {"name": item["name"], "domain": domain_of(item, roles), "detail": check_detail(item)}
        for item in [*constraints, *balances]
    ]
    items += [
        {
            "name": f"{group['path']} {group['code']}",
            "domain": domain_of(group, roles),
            "detail": group_detail(group),
        }
        for group in groups
    ]
    return items


def verify(plant, results, case):
    """Return ``{passed, checks, failures, metrics}`` of a plant's run on its case.

    ``passed`` and ``checks`` are gemini's (``gm.evaluate``): the case's constraints, the ledgers
    and the plant balance. ``failures`` lists each failed check or group of failed steps with the
    ``domain`` that should fix it (``subsurface``, ``sizing``, ``surface`` or ``coupled``).
    """
    found = assess(plant, case, results)
    return {
        "passed": found["passed"],
        "checks": [*found["constraints"], *found["balances"]],
        "failures": failure_items(found),
        "metrics": found["metrics"],
    }

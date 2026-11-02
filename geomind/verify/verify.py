"""Verify a run of a design on its case: gemini's verdict decides, the reasons get a domain."""

from geomind.tools.gemini.verification import assess, domain_of, requirement_roles, unit_roles


def amount(item):
    """Return a gemini ``{value, unit}`` as text."""
    return f"{item.get('value')} {item.get('unit', '')}".strip()


def reason_detail(reason):
    """Return what a reason measured against its limit in display units, else gemini's message."""
    if "value" in reason and "limit" in reason:
        return f"{reason['name']}: {amount(reason['value'])} against {amount(reason['limit'])}"
    return reason["message"]


def group_detail(group):
    """Return a failure group of gemini's rows as text."""
    return f"{group['count']} {group['kind']} steps, {group['code']}: {group['message']}"


def group_items(groups, roles):
    """Return one failure item per group of failed rows, routed by the unit it lies in."""
    return [
        {
            "name": f"{group['path']} {group['code']}".strip(),
            "kind": "failed_step",
            "domain": domain_of(group, roles),
            "detail": group_detail(group),
        }
        for group in groups
    ]


def failure_items(found, case):
    """Return ``[{name, kind, domain, detail}]`` of every reason in an ``assess`` result.

    A ``failed_step`` reason is listed as the groups of failed rows by module and code, each routed
    by the unit it lies in; the other reasons are listed as gemini gave them.
    """
    roles = unit_roles(found["requirements"])
    named = requirement_roles(case)
    items = []
    for reason in found["reasons"]:
        if reason["kind"] == "failed_step" and found["failures"]["groups"]:
            items += group_items(found["failures"]["groups"], roles)
            continue
        items.append(
            {
                "name": reason["name"],
                "kind": reason["kind"],
                "domain": domain_of(reason, roles, named),
                "detail": reason_detail(reason),
            }
        )
    return items


def verify(plant, results, case):
    """Return ``{passed, checks, failures, metrics}`` of a plant's run on its case.

    ``passed`` is gemini's ``gm.evaluate.verdict`` (``feasible``), ``checks`` the requirement checks
    of its report. ``failures`` lists each reason of the verdict (``kind``: ``requirement``,
    ``failed_step``, ``numerical`` or ``bound``) with the ``domain`` that should fix it
    (``subsurface``, ``sizing``, ``surface`` or ``coupled``).
    """
    found = assess(plant, case, results)
    return {
        "passed": found["feasible"],
        "checks": found["requirements"],
        "failures": failure_items(found, case),
        "metrics": found["metrics"],
    }

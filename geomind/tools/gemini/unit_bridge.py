"""Units gemini 0.6.1 refuses that the models write as the sources give them, mapped by set_case.

A stopgap, reversible: gemini request 31 (``°C/km`` as a temperature gradient) and request 15
(``mol%`` and ``%`` on a gas fraction) make it unneeded, and this module goes when they land.
Unit names as sources spell them (``kg/m³``, ``mPa·s``, ``MWth``) become gemini's name of the same
unit, ``kg/m3``, ``mPa.s``, ``MW``, only where the key's units hold that name: a name, no factor
(#118).
``set_case`` lists each mapping in its result (``converted``) so the case lead puts it in the
confirmation question.
"""

import copy

GRADIENT = ("site", "ground", "gradient")
GRADIENT_UNITS = {
    "degC/km": "K/km",
    "°C/km": "K/km",
    "C/km": "K/km",
    "degC/m": "K/m",
    "°C/m": "K/m",
    "C/m": "K/m",
}
"""A temperature difference per length: the same number in kelvin, a unit name and no factor."""
FRACTIONS = (("site", "fluid", "dissolved_gas"), ("utilities", "gas", "composition"))
PERCENT_UNITS = ("%", "mol%", "mol %")
GRADIENT_REASON = "a temperature gradient: °C/km is K/km, the same number (until gemini request 31)"
PERCENT_REASON = "a gas fraction given in percent: value / 100 (until gemini request 15)"
SPELLINGS = {"³": "3", "²": "2", "·": "."}
"""Characters of a unit name as sources print it, and gemini's spelling of them."""
UNIT_NAMES = {"MWth": "MW", "MWcool": "MW"}
"""Unit names that say what the power is for, and the unit they are in."""
NAME_REASON = "unit name"


def percent_fraction(value):
    """Return the fraction of a percentage, ``value / 100``.

    The one unit conversion geomind does: gemini 0.6.1 does not know ``%`` or ``mol%`` on a
    fraction (gemini request 15). Remove it, and its line in ``test_no_unit_math``'s allowlist,
    when that request lands.
    """
    return value / 100


def bridged_units(changes):
    """Return ``(changes, converted)``: the changes with the units above mapped, and the list.

    ``converted`` holds ``{path, from: {value, unit}, to: {value, unit}, reason}`` per value; the
    changes are copied, never edited in place.
    """
    changes = copy.deepcopy(changes)
    converted = []
    gradient = _node(changes, GRADIENT)
    unit = _unit(gradient)
    if unit in GRADIENT_UNITS:
        gradient["unit"] = GRADIENT_UNITS[unit]
        value = gradient.get("value")
        converted.append(_entry(GRADIENT, value, unit, value, gradient["unit"], GRADIENT_REASON))
    for section in FRACTIONS:
        gases = _node(changes, section)
        for gas, item in (gases or {}).items():
            unit = _unit(item)
            if unit in PERCENT_UNITS and _is_number(item.get("value")):
                converted.append(_fraction(item, (*section, gas), unit))
    converted.extend(_renamed_units(changes, _case_schema(), ()))
    return changes, converted


def gemini_unit_name(unit, accepted):
    """Return gemini's name of ``unit`` when ``accepted`` holds it and not ``unit``, else ``None``.

    ``m³/h`` is ``m3/h``, ``mPa·s`` is ``mPa.s``, ``MWth`` and ``MWcool`` are ``MW``: the same unit.
    """
    if not isinstance(unit, str) or unit in accepted:
        return None
    name = "".join(SPELLINGS.get(char, char) for char in unit.strip())
    name = UNIT_NAMES.get(name, name)
    return name if name in accepted else None


def _case_schema():
    """Return gemini's JSON Schema of a case."""
    import gemini as gm

    return gm.Case.schema()


def _accepted_units(schema):
    """Return the units a field's schema accepts: its ``x-units`` or the ``unit`` enums."""
    if not isinstance(schema, dict):
        return set()
    units = set(schema.get("x-units") or ())
    unit = (schema.get("properties") or {}).get("unit")
    units |= set((unit or {}).get("enum") or ())
    for branch in schema.get("anyOf") or ():
        units |= _accepted_units(branch)
    return units


def _child_schema(schema, key):
    """Return the schema of ``key`` under an object schema, or ``None``."""
    if not isinstance(schema, dict):
        return None
    child = (schema.get("properties") or {}).get(key)
    extra = schema.get("additionalProperties")
    return child if child is not None else extra if isinstance(extra, dict) else None


def _renamed_units(changes, schema, path):
    """Give each ``unit`` under ``changes`` gemini's name where its key takes it; return entries."""
    if not isinstance(changes, dict) or schema is None:
        return []
    name = gemini_unit_name(changes.get("unit"), _accepted_units(schema))
    if name is not None:
        given, changes["unit"] = changes["unit"], name
        value = changes.get("value")
        return [_entry(path, value, given, value, name, NAME_REASON)]
    entries = []
    for key, item in changes.items():
        entries.extend(_renamed_units(item, _child_schema(schema, key), (*path, key)))
    return entries


def _fraction(item, path, unit):
    """Turn a gas given in percent into its fraction in place; return its ``converted`` entry."""
    given = item["value"]
    del item["unit"]
    item["value"] = percent_fraction(given)
    for key in ("range", "uncertainty"):
        _scale_bounds(item.get(key))
    return _entry(path, given, unit, item["value"], None, PERCENT_REASON)


def _scale_bounds(bounds):
    """Turn the ``min``, ``max`` and ``std`` of a range or an uncertainty into fractions."""
    if not isinstance(bounds, dict):
        return
    for name in ("min", "max", "std"):
        if _is_number(bounds.get(name)):
            bounds[name] = percent_fraction(bounds[name])


def _node(changes, path):
    """Return the dict at ``path`` of a merge patch, or ``None``."""
    node = changes
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else None


def _unit(item):
    """Return the stripped unit of a value object, or ``None``."""
    unit = item.get("unit") if isinstance(item, dict) else None
    return unit.strip() if isinstance(unit, str) else None


def _is_number(value):
    """Tell whether a value is a number, not a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _entry(path, value, unit, new_value, new_unit, reason):
    """Return one ``converted`` entry."""
    return {
        "path": ".".join(path),
        "from": {"value": value, "unit": unit},
        "to": {"value": new_value, "unit": new_unit},
        "reason": reason,
    }


def bridged_requirements(requirements):
    """Return ``(requirements, converted)``: each requirement's unit under gemini's name of it.

    A requirement's ``unit`` may be any unit gemini knows, so ``m³/h`` becomes ``m3/h``; the
    requirements are copied, never edited in place.
    """
    import gemini as gm

    requirements = copy.deepcopy(requirements)
    known = set(gm.units.names())
    converted = []
    for name, item in requirements.items():
        unit = item.get("unit") if isinstance(item, dict) else None
        renamed = gemini_unit_name(unit, known)
        if renamed is not None:
            item["unit"] = renamed
            converted.append(_entry(("requirements", name), None, unit, None, renamed, NAME_REASON))
    return requirements, converted

"""The outside air pressure of a site from its elevation, by the standard atmosphere.

gemini gives no data, defaults or derived inputs for other packages (docs/rules.md), and a case
without ``site.air.pressure`` is ``missing_value``. When no file and no knowledge gives the
pressure, the case lead asks the user for it or for the site's elevation. With an elevation,
``set_case`` takes ``site.air.pressure`` as ``{"elevation": {"value", "unit"}}`` and sets the
pressure of the International Standard Atmosphere at that elevation, so the model computes
nothing; ``converted`` names the value and its source for the user's confirmation. No elevation
and no pressure leave the key unset.
"""

from geomind.errors import ToolError

AIR = ("site", "air")
CITATION = "ISA (ISO 2533:1975)"
FORMULA = "p = 101325*(1-2.25577e-5*h)^5.25588 Pa, h the elevation in m"
FORM = '{"elevation": {"value": <number>, "unit": "m"}}'


def isa_pressure(elevation):
    """Return the ISA air pressure in Pa at ``elevation`` m above sea level (ISO 2533:1975)."""
    return 101325 * (1 - 2.25577e-5 * elevation) ** 5.25588


def pressure_from_elevation(changes):
    """Return ``(changes, converted)``: an elevation under ``site.air.pressure`` as ISA pressure.

    The pressure is set in Pa with its source in ``site.air.about``; ``converted`` holds its entry.
    The changes are edited in place; ``set_case`` passes its own copy.
    """
    site = changes.get(AIR[0]) if isinstance(changes, dict) else None
    air = site.get(AIR[1]) if isinstance(site, dict) else None
    pressure = air.get("pressure") if isinstance(air, dict) else None
    if not isinstance(pressure, dict) or "elevation" not in pressure:
        return changes, []
    pascal = isa_pressure(elevation_in_metres(pressure))
    value, unit = pressure["elevation"]["value"], pressure["elevation"]["unit"]
    air["pressure"] = {"value": pascal, "unit": "Pa"}
    source = f"{CITATION} at the site's elevation {value} {unit}: {FORMULA}"
    about = air.get("about") if isinstance(air.get("about"), dict) else {}
    air["about"] = {**about, "pressure": source}
    entry = {
        "path": "site.air.pressure",
        "from": {"elevation": {"value": value, "unit": unit}},
        "to": {"value": pascal, "unit": "Pa"},
        "reason": f"{CITATION}: {FORMULA}; confirm it with the user",
    }
    return changes, [entry]


def elevation_in_metres(pressure):
    """Return the elevation of ``{"elevation": {value, unit}}`` in m, converted by gemini.

    Raises ``invalid_input`` for another form and ``invalid_unit`` for a unit of no length.
    """
    import gemini as gm

    elevation = pressure["elevation"]
    given = isinstance(elevation, dict) and isinstance(elevation.get("unit"), str)
    value = elevation.get("value") if given else None
    if set(pressure) != {"elevation"} or not isinstance(value, (int, float)):
        raise ToolError(
            f"set_case: site.air.pressure = {pressure!r}; expected a pressure {{value, unit}} or "
            f"the site's elevation alone, {FORM}",
            path="site.air.pressure.elevation",
            suggestions=[FORM],
        )
    try:
        metres = gm.units.convert(value, elevation["unit"], "m", quantity="length")
    except gm.errors.ValidationError as error:
        raise ToolError(
            f"set_case: site.air.pressure.elevation.unit = {elevation['unit']!r}; expected a unit "
            "of length, such as m or ft",
            code="invalid_unit",
            path="site.air.pressure.elevation.unit",
            suggestions=[FORM],
        ) from error
    if not 1 - 2.25577e-5 * metres > 0:
        raise ToolError(
            f"set_case: site.air.pressure.elevation = {value} {elevation['unit']}; expected an "
            "elevation within the atmosphere (below 44 km)",
            path="site.air.pressure.elevation",
        )
    return metres

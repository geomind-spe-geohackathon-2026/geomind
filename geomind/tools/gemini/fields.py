"""Where each case value comes from, what each option says, and gemini's meaning of each field.

gemini 0.6.3's ``Case.schema()`` and ``Economics.schema()`` describe every key (request 22), so a
field's meaning is gemini's description, read when a tree renders, never copied here. geomind
keeps only what gemini's schema does not say: where a case value comes from and a few notes for
the case lead (``CASE_NOTES``), and the meaning of each option of a requirement (``OPTIONS``).
Where a value comes from: ``brief`` (the organiser's or client's brief), ``data`` (a data file),
``report`` (a geological or well report, read by the geoscientist), ``user`` (ask), ``economics``
(an economics file or the knowledge base with its source). ``derived`` means gemini computes it:
leave it unset.
"""

CASE_NOTES = {
    "site.ground.surface_temperature": "brief/report",
    "site.ground.gradient": "brief/report",
    "site.reservoir.reference_depth": "true vertical depth; brief/report",
    "site.reservoir.thickness": "gross thickness (net-to-gross if given); report",
    "site.reservoir.permeability": "report",
    "site.reservoir.pressure": "static pressure; brief/report",
    "site.reservoir.temperature": "set it only when a report measured it; derived",
    "site.fluid.density": "brief/report",
    "site.fluid.viscosity": "brief/report",
    "site.fluid.gas_liquid_ratio": "report",
    "site.fluid.dissolved_gas": "the produced gas; report",
    "site.fluid.sand_concentration": "report",
    "site.air": "for coolers and the flare",
    "site.air.temperature": "brief/data",
    "site.air.relative_humidity": "brief/data",
    "site.air.pressure": (
        "with only the site's elevation, give {elevation: {value, unit}}: set_case sets the ISA "
        "pressure; brief/report/user"
    ),
    "demand.heating.power": "a series on the case's steps; data",
    "demand.heating.supply_temperature": "brief",
    "demand.heating.return_temperature": "colder than the supply; brief/user",
    "demand.heating.return_pressure": "brief/user",
    "demand.cooling.power": "a series on the case's steps; data",
    "demand.cooling.supply_temperature": "brief",
    "demand.cooling.return_temperature": "warmer than the supply; brief/user",
    "demand.cooling.return_pressure": "brief/user",
    "demand.cooling.indoor_temperature": "brief/user",
    "demand.cooling.indoor_relative_humidity": "brief/user",
    "demand.cooling.dew_point_margin": "user",
    "utilities.electricity.co2_intensity": "brief/economics",
    "utilities.electricity.import_limit": "brief/user",
    "utilities.electricity.export_limit": "brief/user",
    "utilities.gas.composition": "never the brine's gas; utility/user",
    "utilities.gas.heating_value": "utility/user",
    "time.step": "the data's interval",
    "requirements": "brief",
    "requirements.min": "min = max is an exact rule",
}
"""geomind's note on a case field, after gemini's meaning: its source last, after a semicolon."""

OPTIONS = {
    "requirements.over": {
        "each": "every step on its own (a cap or a floor per day)",
        "sum": "the sum over the run",
        "mean": "the mean over the run",
        "max": "the largest step",
        "min": "the smallest step",
        "duration": "the total time of the steps where `when` holds; bounds in d or h",
    },
    "requirements.when": {
        "always": "every step",
        "running": "only the steps the unit carries flow",
    },
    "requirements.on": {
        "doublet": "each geothermal doublet",
        "heat_pump": "each heat pump",
        "boiler": "each boiler",
        "chp": "each combined heat and power unit",
        "chiller": "each chiller",
        "heat_exchanger": "each heat exchanger",
        "heating_supply": "the heat delivered to the consumers",
        "cooling_supply": "the cold delivered to the consumers",
        "plant": "the whole plant",
    },
    "requirements.quantity": {
        "count": "how many units of the role there are: a number of units, never days",
        "production_flow": "brine flow of a doublet",
        "brine_cooling": "brine temperature drop from producer to injector",
        "production_temperature": "brine temperature at the producer",
        "injection_temperature": "brine temperature at the injector",
        "pump_power": "electric power of a doublet's pumps",
        "pump_efficiency": "hydraulic efficiency of a doublet's pumps",
        "intake_pressure": "pressure at the pump intake",
        "intake_gas_fraction": "free gas share at the pump intake",
        "reinjection_ratio": "injected over produced brine volume",
        "wellhead_pressure": "pressure at the wellhead",
        "cop": "coefficient of performance",
        "lift": "temperature lift of a heat pump",
        "heat_output": "heat a unit gives",
        "cold_output": "cold a unit gives",
        "duty": "heat a heat exchanger transfers",
        "approach": "smallest temperature difference of a heat exchanger",
        "fuel_input": "fuel a unit burns",
        "power_output": "electric power a unit gives",
        "unmet": "demand not covered",
        "unmet_share": "share of the demand not covered, 0-1",
        "temperature": "temperature delivered",
        "co2": "CO2 emitted",
        "electricity_bought": "electricity bought",
        "gas_bought": "gas bought",
        "gas_burned": "gas burned",
        "heat_surplus": "heat made beyond the demand",
    },
}
"""What each option of a case field means and when to choose it."""

EXAMPLES = (
    "Operating days are a time, never a count: `{name: running_time_limit, on: doublet, "
    "quantity: production_flow, over: duration, when: running, max: <days>, unit: d}`; "
    "a number of doublets is `{on: doublet, quantity: count, min, max}`."
)
"""How a rule of a brief is written, for the two that are mixed up."""


MAP_ENTRY = "The entry of this map for "
"""The start of gemini's description of a map's entry, which names only the entry's key."""


def schema_descriptions(schema, path=""):
    """Return gemini's own ``description`` of each field and section of a schema, by dotted path.

    A list's fields are ``list.field``, as in ``CASE_NOTES``. gemini 0.6.3 describes each entry of
    a map as ``The entry of this map for <key>.``, which says nothing: it is left out, so the map's
    own description covers its entries (``opex.fixed.boiler`` reads ``opex.fixed``'s).
    """
    found = {}
    for key, sub in (schema.get("properties") or {}).items():
        dotted = f"{path}{key}"
        if sub.get("description") and sub["description"] != f"{MAP_ENTRY}{key}.":
            found[dotted] = sub["description"]
        items = sub.get("items") if sub.get("type") == "array" else None
        found.update(schema_descriptions(items if isinstance(items, dict) else sub, f"{dotted}."))
    return found


def case_fields():
    """Return the meaning of each case field: gemini's description, then geomind's note."""
    import gemini as gm

    given = schema_descriptions(gm.Case.schema())
    return {
        path: "; ".join(text for text in (given.get(path), CASE_NOTES.get(path)) if text)
        for path in {**given, **CASE_NOTES}
    }


def economics_fields():
    """Return the meaning of each economics field: gemini's description.

    A section's description covers every field below it that has none of its own.
    """
    import gemini as gm

    return schema_descriptions(gm.case.Economics.schema())


def meaning(path, fields):
    """Return the meaning of a dotted path, by its own entry or the nearest prefix entry."""
    found = fields.get(path)
    if found is not None:
        return found
    for key in sorted(fields, key=len, reverse=True):
        if key.endswith(".") and path.startswith(key):
            return fields[key]
        if path.startswith(f"{key}."):
            return fields[key]
    return None


def options_text():
    """Return the meaning of every option of the requirement fields, one line per field."""
    lines = []
    for field, options in OPTIONS.items():
        shown = "; ".join(f"{value}: {text}" for value, text in options.items())
        lines.append(f"{field} options: {shown}")
    return "\n".join([*lines, EXAMPLES])


def undescribed():
    """Return the case and economics fields gemini's schemas describe nowhere: the list for Sahand.

    A field reads with its own description or its nearest section's; gemini 0.6.3 gives one for
    every key (request 22), so the list is empty.
    """
    import gemini as gm

    from geomind.tools.gemini.skeleton import key_tree

    found = []
    for prefix, schema in (("", gm.Case.schema()), ("economics.", gm.case.Economics.schema())):
        given = schema_descriptions(schema)
        parent = ""
        for line in key_tree(schema):
            path = line.split(":", 1)[0].replace("*", "").strip()
            if not line.startswith("  "):
                parent = path.removesuffix("[]") if path.endswith("[]") else ""
            elif parent:
                path = f"{parent}.{path}"
            if meaning(path.removesuffix("[]"), given) is None:
                found.append(f"{prefix}{path.removesuffix('[]')}")
    return found

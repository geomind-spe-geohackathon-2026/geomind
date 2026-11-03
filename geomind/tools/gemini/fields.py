"""What each field of a case means, where its value comes from, and what each option says.

gemini's ``Case.schema()`` and ``Economics.schema()`` give the keys, forms and units but no
meaning; these texts are geomind's, taken from gemini's class docstrings where they say it
(``gemini.case.site``, ``demand``, ``time``, ``utilities``, ``requirement``, ``economics``). A
field shown here with ``(gemini: none)`` has no description in gemini at all: it is on the list
for Sahand. Where a value comes from: ``brief`` (the organiser's or client's brief), ``data``
(a data file), ``report`` (a geological or well report, read by the geoscientist), ``user`` (ask),
``economics`` (an economics file or the knowledge base with its source). ``derived`` means gemini
computes it: leave it unset.
"""

CASE_FIELDS = {
    "format": "always 1",
    "kind": 'always "case"',
    "name": "a short name of the case",
    "about": "free notes: where the case comes from, what it is for (gemini: none)",
    "site.ground.surface_temperature": (
        "undisturbed ground temperature at the surface; brief/report"
    ),
    "site.ground.gradient": "rise of rock temperature with depth; brief/report",
    "site.reservoir.reference_depth": "depth the reservoir values are given at (TVD); brief/report",
    "site.reservoir.thickness": "gross thickness of the aquifer; report (net-to-gross if given)",
    "site.reservoir.permeability": "permeability of the aquifer rock; report",
    "site.reservoir.pressure": "static pressure at the reference depth; brief/report",
    "site.reservoir.temperature": (
        "measured temperature at the reference depth only; derived from the ground when unset, "
        "so leave it unset unless a report measured it"
    ),
    "site.fluid.density": "brine density; brief/report",
    "site.fluid.viscosity": "brine dynamic viscosity; brief/report",
    "site.fluid.gas_liquid_ratio": (
        "gas liberated per volume of brine at standard conditions (GLR); report"
    ),
    "site.fluid.dissolved_gas": (
        "mole fraction of each species of the produced gas, adding up to 1; report"
    ),
    "site.fluid.sand_concentration": "solids carried by the brine; report",
    "site.air": "outside air at the site, for coolers and the flare",
    "site.air.temperature": "outside air temperature, a constant or a series; brief/data",
    "site.air.relative_humidity": "outside air relative humidity 0-1; brief/data",
    "site.air.pressure": "outside air pressure; brief/user (from the site's elevation)",
    "demand.heating.power": "heat the consumers ask for, a series on the case's steps; data",
    "demand.heating.supply_temperature": "temperature the heat is delivered at; brief",
    "demand.heating.return_temperature": (
        "temperature the heating water comes back at, colder than the supply; brief/user"
    ),
    "demand.heating.minimum_return_temperature": "lowest return the consumers allow (gemini: none)",
    "demand.heating.maximum_return_temperature": (
        "highest return the consumers allow (gemini: none)"
    ),
    "demand.heating.return_pressure": "pressure the heating water comes back at; brief/user",
    "demand.cooling.power": "cold the consumers ask for, a series on the case's steps; data",
    "demand.cooling.supply_temperature": "temperature the chilled water is delivered at; brief",
    "demand.cooling.return_temperature": (
        "temperature the chilled water comes back at, warmer than the supply; brief/user"
    ),
    "demand.cooling.minimum_return_temperature": "lowest return the consumers allow (gemini: none)",
    "demand.cooling.maximum_return_temperature": (
        "highest return the consumers allow (gemini: none)"
    ),
    "demand.cooling.return_pressure": "pressure the chilled water comes back at; brief/user",
    "demand.cooling.indoor_temperature": "room temperature of the cooled building; brief/user",
    "demand.cooling.indoor_relative_humidity": "room relative humidity 0-1; brief/user",
    "demand.cooling.dew_point_margin": (
        "how far the chilled water stays above the room's dew point; user"
    ),
    "utilities.electricity.co2_intensity": "CO2 per unit of grid electricity; brief/economics",
    "utilities.electricity.import_limit": "most power the grid connection takes in; brief/user",
    "utilities.electricity.export_limit": "most power the plant may sell to the grid; brief/user",
    "utilities.gas.composition": (
        "mole fractions of the bought grid gas, adding up to 1; utility/user, never the brine's gas"
    ),
    "utilities.gas.heating_value": "energy per mass of the grid gas; utility/user",
    "time.start": "first instant, ISO 8601; text without an offset is UTC",
    "time.end": (
        "end of the period, excluded: a year of daily values ends on the next year's first day"
    ),
    "time.step": "length of one step: the data's interval, such as 1 d",
    "initial_state": "stored state of modules at the start, by module (gemini: none)",
    "economics": "the economics file's name or its object",
    "requirements": "the rules the outcome must meet, each on one role of the plant; brief",
    "requirements.name": "unique snake_case name of the rule",
    "requirements.on": "the role the rule applies to, each unit of it on its own",
    "requirements.quantity": "the quantity of that role the rule bounds",
    "requirements.unit": "the bounds' unit, present only when they have a dimension",
    "requirements.over": "how a per-step quantity is read over the run",
    "requirements.when": "which steps count: every step, or only those the unit runs",
    "requirements.min": "lower bound, in unit; min = max is an exact rule",
    "requirements.max": "upper bound, in unit",
}
"""One meaning per case field, by its dotted path; a list's fields by ``list.field``."""

ECONOMICS_FIELDS = {
    "format": "always 1",
    "kind": 'always "economics"',
    "name": "a short name of the economics",
    "currency": "the label of every amount; nothing converts between currencies",
    "price_year": "the year the prices are in",
    "discount_rate": "real discount rate per year, 0-1",
    "analysis_period": "years of the analysis",
    "capex.": "cost of building one kind of equipment, per W, per metre, per W/K, per m3 or fixed",
    "opex.fixed.": "yearly share of that kind's capex spent on operation and maintenance",
    "opex.variable.": "price of a consumable per mass",
    "energy.": "price of bought electricity or gas per energy, constant or series",
    "carbon.price": "price of a mass of CO2-equivalent",
    "revenue.heat": "what a unit of delivered heat earns",
    "revenue.cold": "what a unit of delivered cold earns",
    "revenue.subsidy.amount": "subsidy paid per year",
    "revenue.subsidy.duration": "how long the subsidy is paid",
    "accounting.allocation.heat_cost_share": "share of a joint plant's cost put on heat, 0-1",
    "accounting.gwp.standard": "name of the global warming potential set",
    "accounting.gwp.CH4": "global warming potential of methane",
    "about": "free notes (gemini: none)",
}
"""One meaning per economics field; a key ending in ``.`` covers every field below it."""

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
    """Return the fields whose meaning gemini gives nowhere: the list for Sahand."""
    found = [path for path, text in CASE_FIELDS.items() if "(gemini: none)" in text]
    return found + [
        f"economics.{path}" for path, text in ECONOMICS_FIELDS.items() if "(gemini: none)" in text
    ]

"""The brief as data: what a design must meet, as a brief states it, and the named presets.

Every field is optional and ``None`` means "not given": a limit the brief does not give is not
checked. Amounts are what gemini takes, a text such as ``"50 m3/h"`` or a Value
``{"value": 50, "unit": "m3/h"}``; geomind converts nothing here, the tools use ``gm.units``.
"""

from typing import Any

from geomind.errors import StateError
from geomind.types import Record
from geomind.utils.strings import did_you_mean, join_names

Amount = str | dict[str, Any]
"""A text ``"<number> <unit>"`` or a Value ``{"value", "unit"}``, as gemini takes them."""


class Demand(Record):
    """The demand profiles: a gemini profile name or a stored ``profile/<name>``."""

    heating: str | None = None
    cooling: str | None = None


class Count(Record):
    """A range of whole numbers; a missing end is not limited."""

    min: int | None = None
    max: int | None = None


class Span(Record):
    """A range of amounts; a missing end is not limited."""

    min: Amount | None = None
    max: Amount | None = None


class Network(Record):
    """The supply and return temperatures of a heating or cooling network."""

    supply: Amount | None = None
    return_temperature: Amount | None = None


class Reservoir(Record):
    """The reservoir and brine values a brief gives; ``gas_composition`` is mole fractions."""

    depth: Amount | None = None
    thickness: Amount | None = None
    gradient: Amount | None = None
    surface_temperature: Amount | None = None
    pressure: Amount | None = None
    permeability: Amount | None = None
    density: Amount | None = None
    viscosity: Amount | None = None
    gas_liquid_ratio: Amount | None = None
    gas_composition: dict[str, float] | None = None


class Brief(Record):
    """What a design must meet, as a brief states it; ``None`` is "not given".

    ``source`` is a preset name, ``user`` (values the user gave) or ``agent`` (values an agent
    read from the user's message). ``volume_balance`` is true when the produced and injected
    liquid volumes must be equal.
    """

    source: str | None = None
    demand: Demand | None = None
    doublets: Count | None = None
    doublet_flow: Span | None = None
    max_brine_cooling: Amount | None = None
    operating_days: int | None = None
    pump_efficiency: Amount | None = None
    volume_balance: bool | None = None
    heating: Network | None = None
    cooling: Network | None = None
    reservoir: Reservoir | None = None


HACKATHON_2027 = Brief(
    source="hackathon_2027",
    demand=Demand(heating="heating_demand", cooling="cooling_demand"),
    doublets=Count(min=1, max=3),
    doublet_flow=Span(min="50 m3/h", max="300 m3/h"),
    max_brine_cooling="40 K",
    operating_days=330,
    pump_efficiency="0.7 -",
    volume_balance=True,
    heating=Network(supply="100 degC"),
    cooling=Network(supply="20 degC"),
    reservoir=Reservoir(
        depth="2500 m",
        thickness="100 m",
        gradient="30 K/km",
        surface_temperature="12 degC",
        pressure="250 bar(g)",
        permeability="200 mD",
        density="1030 kg/m3",
        viscosity="0.4 mPa.s",
        gas_liquid_ratio="0.8 Nm3/m3",
        gas_composition={"CH4": 0.8, "CO2": 0.2},
    ),
)
"""The GEMINI hackathon challenge requirements of 28 October 2026, sections 2 and 3.

Demand: gemini's ``heating_demand`` and ``cooling_demand`` profiles of 2027. Reservoir at a
2500 m midpoint, 100 m thick, 30 K/km from 12 degC, 250 bar(g), 200 mD; brine 1030 kg/m3 and
0.40 mPa.s, 0.8 Nm3 gas per m3 liquid, 80 mol% methane and 20 mol% CO2. Limits: 1 to 3 doublets,
50 to 300 m3/h per doublet while active, brine cooled by at most 40 K from producer to injector,
70 % pump efficiency, equal produced and injected volumes, 330 daily steps of operation, heating
supply 100 degC and cooling supply 20 degC. The brief gives no return temperatures: 60 degC and
25 degC are assumptions of a design, never of the brief.
"""

PRESETS = {"hackathon_2027": HACKATHON_2027}
"""The named briefs; the only place their numbers live."""


def preset(name):
    """Return the preset brief ``name``; an unknown name raises ``StateError``."""
    if name not in PRESETS:
        raise StateError(
            f"brief: preset = {name!r}; expected one of {join_names(sorted(PRESETS))}"
            f"{did_you_mean(name, sorted(PRESETS))}"
        )
    return PRESETS[name]


def with_changes(brief, changes):
    """Return ``brief`` with the fields of ``changes`` replaced, nested records merged.

    ``changes`` is the JSON of a partial ``Brief``; a field set to ``None`` is removed. The result
    is validated as a whole, so a wrong name or type raises ``pydantic.ValidationError``.
    """
    document = brief.model_dump(mode="json") if brief is not None else {}
    return Brief.model_validate(_merged(document, changes))


def _merged(document, changes):
    """Return ``document`` with ``changes`` merged in, one level of records deep at a time."""
    merged = dict(document)
    for name, value in changes.items():
        current = merged.get(name)
        is_record = isinstance(value, dict) and isinstance(current, dict)
        is_record = is_record and name != "gas_composition"
        merged[name] = _merged(current, value) if is_record else value
    return merged

"""gemini's hackathon example as a stored design: its spec with the inputs kept in ``boundary``."""

INPUTS = {
    "heat_pump": {"temperature_setpoint": "100 degC"},
    "boiler": {"temperature_setpoint": "100 degC"},
    "chiller": {"temperature_setpoint": "20 degC"},
    "cool_users": {"indoor_temperature": "26 degC", "indoor_relative_humidity": 0.5},
    "chiller_cooler": {"temperature_setpoint": "15 degC", "flow": "800 kg/s"},
    "air": {"temperature": "10 degC"},
    "desander": {"sand_concentration": "20 mg/l"},
    "dosing": {"dose": "10 ppm"},
}
"""The inputs of gemini's ``examples/cases/hackathon.py``, as a design stores them."""


def hackathon_spec(gm):
    """Return the spec of gemini's hackathon plant with its inputs kept in ``boundary``."""
    spec = gm.plants.example("HackathonPlant").to_dict()
    return {**spec, "boundary": {"": {"inputs": INPUTS}}}


def flat_inputs():
    """Return the inputs as ``set_inputs`` takes them."""
    return {
        f"{path}.{name}": value for path, values in INPUTS.items() for name, value in values.items()
    }


def hackathon_run(gm, start="2027-01-01", end="2027-01-31"):
    """Return gemini's own hackathon plant and its run on both demand profiles, in a window."""
    import pandas as pd

    from geomind.tools.gemini.brief import SCHEDULE_RULES

    plant = gm.plants.example("HackathonPlant")
    plant.set_inputs(flat_inputs())
    demand = pd.concat([gm.profiles.get(name) for name in gm.profiles.names()], axis=1)
    plan = gm.schedule(plant, demand.loc[start:end], SCHEDULE_RULES)
    return plant, gm.simulate(plant, plan, on_error="record")


MWH = 3.6e9
PRICES = {
    "discount_rate": 0.05,
    "lifetime_years": 25,
    "electricity_price": 100.0 / MWH,
    "gas_price": 40.0,
    "heat_price": 60.0 / MWH,
    "cold_price": 60.0 / MWH,
    "electricity_emission_factor": 0.3 / 3.6e6,
    "pump_cost": 0.5,
    "chiller_cost": 0.3,
    "exchanger_cost": 0.5,
    "flare_cost": 1e5,
    "makeup_cost": 5e4,
    "waste_disposal_price": 0.2,
    "chemical_price": 3.0,
}
"""The placeholder prices of gemini's ``examples/cases/hackathon.py``: not data, for tests only."""


SERIES = [
    {"source": "heat_pump.sink_out", "target": "chiller.generator_in"},
    {"source": "chiller.generator_out", "target": "boiler.fluid_in"},
    {"source": "boiler.fluid_out", "target": "heat_users.supply_in"},
    {"source": "degasser.gas_out", "target": "flare.gas_in"},
    {"source": "gas_grid.gas_out", "target": "boiler.fuel_in"},
]
"""The wiring that replaces the example's splitter, mixer and gas makeup."""


def base_spec(gm):
    """Return a design that meets every check of the brief, built from gemini's example.

    The chiller's generator sits between the heat pump and the boiler, so the heating users get
    100 degC and no water loop is needed; the co-produced gas goes to the flare and the boiler
    burns grid gas only.
    """
    spec = hackathon_spec(gm)
    removed = {"loads", "heat_return", "makeup"}
    replaced = {"heat_pump.sink_out", "boiler.fluid_out", "degasser.gas_out", "gas_grid.gas_out"}
    connections = [
        item
        for item in spec["connections"]
        if item["source"] not in replaced
        and not {item["source"].split(".")[0], item["target"].split(".")[0]} & removed
    ]
    modules = {name: entry for name, entry in spec["modules"].items() if name not in removed}
    return {**spec, "name": "BaseSeries", "modules": modules, "connections": connections + SERIES}


def base_run(gm, start="2027-01-01", end="2027-01-31"):
    """Return the base design and its run on both demand profiles, in a window."""
    import pandas as pd

    from geomind.tools.gemini.brief import SCHEDULE_RULES
    from geomind.tools.gemini.plants import apply_inputs

    spec = base_spec(gm)
    plant = apply_inputs(gm.plants.from_dict(spec), spec)
    demand = pd.concat([gm.profiles.get(name) for name in gm.profiles.names()], axis=1)
    plan = gm.schedule(plant, demand.loc[start:end], SCHEDULE_RULES)
    return plant, gm.simulate(plant, plan, on_error="record")

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

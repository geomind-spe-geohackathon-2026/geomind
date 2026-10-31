"""The numbers of the official brief that geomind hands to gemini, held in one place.

The GEMINI hackathon challenge requirements of 28 October 2026, section 3: 1 to 3 doublets,
50 to 300 m3/h per doublet while active, brine cooled by at most 40 K from producer to injector.
NOTE: ``operating_days`` stays ``None``: ``gm.schedule`` raises ``NotImplementedYet`` for the
"330 daily steps" until gemini decides what they mean, so every doublet runs every day.
"""

SCHEDULE_RULES = {
    "order": ["geothermal", "heat_pump", "boiler"],
    "doublet_flow": {"min": "50 m3/h", "max": "300 m3/h"},
    "max_brine_cooling": "40 K",
    "operating_days": None,
}

DOUBLETS = (1, 3)
"""The number of doublets the brief allows."""

DOUBLET_FLOW = ((50, "m3/h"), (300, "m3/h"))
"""The flow of each doublet while it runs."""

MAX_BRINE_COOLING = (40, "K")
"""The cooling of the brine from producer to injector."""

HEATING_SUPPLY = (100, "degC")
"""The fixed supply temperature of the heating network."""

COOLING_SUPPLY = (20, "degC")
"""The fixed supply temperature of the cooling network."""

PUMP_EFFICIENCY = 0.7
"""The pump efficiency the brief fixes."""

TOLERANCE = {"temperature": 1e-3, "power": 1e-3, "volume_flow": 1e-9}
"""The one numerical tolerance of verification, in SI (K, W, m3/s), by quantity.

NOTE: it only absorbs floating-point noise, such as an unmet demand of 3e-8 W on a day that is fully
met; it never relaxes a limit of the brief.
"""

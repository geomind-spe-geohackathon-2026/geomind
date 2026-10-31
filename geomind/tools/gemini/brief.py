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

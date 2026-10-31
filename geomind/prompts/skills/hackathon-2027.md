The GEMINI hackathon challenge of 28 October 2026 in numbers: its demand, reservoir, brine and hard limits, the preset hackathon_2027.

`set_brief(preset="hackathon_2027")` puts all of this into the problem state; verification checks
it from there.

- Demand: `heating_demand` and `cooling_demand`, gemini's 365 daily values of 2027; heating peaks at
  30 MW on 28 January (111.7 GWh a year), cooling at 10 MW on 19 July (23.7 GWh a year).
- Reservoir: midpoint 2500 m TVD, 100 m thick, 30 K/km from 12 degC at the surface, 250 bar(g),
  200 mD. Another depth may be chosen, with hydrostatic pressure and the same gradient.
- Brine: 1030 kg/m3, 0.4 mPa.s, 0.8 Nm3 of gas per m3 of liquid, the gas 80 mol% methane and
  20 mol% CO2.
- Hard limits: 1 to 3 doublets; 50 to 300 m3/h per doublet while it runs; the brine cooled by at
  most 40 K from producer to injector; pump efficiency 0.7; produced volume equal to injected
  volume; 330 daily steps of operation; heating supply fixed at 100 degC and cooling supply at
  20 degC; demand met on every day.
- Not given: the return temperatures of both networks. A design assumes them (for example 60 degC
  and 25 degC) as unconfirmed assumptions.
- `example/HackathonPlant` has this brief's reservoir and brine values. It is a starting point, not
  an answer: it mixes the chiller's return into the heating supply and burns the co-produced gas,
  and both fail verification.

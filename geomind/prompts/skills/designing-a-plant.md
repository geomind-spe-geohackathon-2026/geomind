How to design the brief's plant in gemini: the numbers, the plant file and what gemini can run.

The brief (GEMINI hackathon, 28 October 2026):

- Demand: `heating_demand` and `cooling_demand`, 365 daily values of 2027; heating peaks at 30 MW
  (111.7 GWh a year), cooling at 10 MW (23.7 GWh a year).
- Reservoir: mid depth 2500 m TVD, 100 m thick, 30 K/km from 12 degC at the surface, 250 barg,
  200 mD; another depth may be chosen, with hydrostatic pressure and the same gradient.
- Brine: 1030 kg/m3, 0.4 mPa*s, 0.8 Nm3 of gas per m3 of liquid, the gas 80 % methane and 20 % CO2.
- Hard limits: 1 to 3 doublets; 50 to 300 m3/h per doublet while it runs; the brine cooled by at
  most 40 K from producer to injector; pump efficiency 0.7; produced volume equal to injected volume;
  heating supply fixed at 100 degC, cooling supply fixed at 20 degC; demand met on every day.
- gemini cannot schedule the 330 operating days yet; every doublet runs every day.

The plant file (`spec`) is what `read_plant` returns under `spec` and what `build_plant` takes:
`modules` (`{id: {type, params}}`), `connections` (`[{source, target}]`, ends `"module.port"`),
`fluids`, `bindings`, `inlets`, `outlets`, `boundary`. Every port is connected or named as a plant
port. A `Doublet` is designed from its `depth`, `gradient`, `surface_temperature`, `permeability`,
`thickness`, `nominal_flow` and `pump_efficiency`. Setpoints and other inputs (a heat pump's,
boiler's or chiller's `temperature_setpoint`, the air temperature, indoor conditions) go in
`boundary[""]["inputs"]` as `{module: {name: value}}`.

What gemini runs:

- A run plans each day with the brief's rules: the doublets first, then at most one `HeatPump`, then
  at most one `Boiler`; one `AbsorptionUnit` is the only chiller the plan dispatches. A compression
  chiller or a second heat pump cannot be planned yet.
- A water circuit that returns to itself needs a `state` connection, which gemini cannot run yet.
  So an absorption chiller's drive water cannot flow back into the heating supply without lowering
  it; placing the chiller's generator between the heat pump and the boiler, which reheats to
  100 degC, keeps the supply at 100 degC.
- At 2500 m the reservoir is about 87 degC, below the 100 degC supply: a heat pump, a boiler or
  deeper wells (about 3000 m for 102 degC) close the gap. One doublet gives at most about 14 MW at
  40 K, so the 30 MW peak needs two or three doublets or top-up heat.
- Templates have no values; `example/HackathonPlant` has the brief's reservoir and brine, but it
  mixes the chiller's return into the heating supply and burns the co-produced gas.

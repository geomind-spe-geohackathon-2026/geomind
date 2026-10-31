How to design a geothermal heating and cooling plant in gemini for any brief: reading the brief, choosing families, sizing, and what gemini can run.

Reading the brief:

- Set the brief of the problem state first with `set_brief`: a preset when the request names one
  (`hackathon_2027` for the GEMINI hackathon challenge; read the `hackathon-2027` skill then),
  otherwise the values the request gives. Never take a preset's numbers for another brief.
- A design needs a demand. When the request gives none, ask the user; a profile they give as daily
  values goes in with `save_profile`, and its `profile/<name>` into the brief's demand.
- A limit the brief does not give is not checked: `check_results` lists it under `not_given`. Do
  not invent one. A value the design needs and the brief lacks (a return temperature, a price) is
  an assumption: record it with its value, `source: "default"` and `confirmed: false`.
- Read the demand with `read_profile` before you size: the peak day, the annual energy, and when
  heating and cooling overlap.

Choosing families:

- Propose 4 to 6 materially different families, each `{id, summary, status}`: vary the number and
  depth of the doublets, how the supply temperature is reached (direct geothermal heat, a heat
  pump, a boiler, deeper wells), how cold is made (absorption chiller, compression chiller, heat
  pump) and storage or backup. Mark a family gemini cannot run `blocked`, with the reason.
- Start the one most likely to pass within gemini's limits below; keep the others for later rounds.

Sizing:

- A doublet's heat is its flow times its brine cooling times the brine's heat capacity, so the
  brief's flow cap and brine-cooling cap bound what one doublet gives. Get the numbers from gemini
  (`evaluate_module` on a doublet, or `simulate` on a short window around the peak day), never by
  hand.
- Size the doublets against the peak demand within those caps; when they cannot reach it, add
  doublets (within the brief's count), deeper wells, or top-up heat from a heat pump or boiler.
- The reservoir temperature follows the gradient and depth. When it is below the brief's heating
  supply, a heat pump, a boiler or deeper wells must close the gap: `evaluate_module` on the
  doublet gives the production temperature.
- A chiller's cold depends on its drive heat or electricity: size it against the cooling peak, and
  check where its drive water or reject heat goes.

What gemini can run today (facts about gemini, not a design):

- A run plans each day by rule: the doublets first, then at most one `HeatPump`, then at most one
  `Boiler`. One `AbsorptionUnit` is the only chiller the plan dispatches; a compression chiller or
  a second heat pump cannot be planned yet.
- No water circuit may return to itself: a loop needs a `state` connection, which gemini cannot
  run yet. Water that leaves a unit colder (a chiller's drive water, a user's return) cannot be
  mixed back into a fixed-temperature supply without lowering it; plan where each stream goes.
- The 330 operating days of a brief cannot be planned yet: every doublet runs every day, and
  verification lists `operating_days` as blocked.
- The base design meets the demand without co-produced methane: a degasser's gas goes to a flare,
  never to a boiler, a CHP or a gas makeup. Burning it is a separate scenario only.
- Templates (`template/<name>`) have no values; examples (`example/<Name>`) have values, but none is
  a solution to any brief.

The plant file (`spec`) is what `read_plant` returns under `spec` and what `build_plant` takes:
`modules` (`{id: {type, params}}`), `connections` (`[{source, target}]`, ends `"module.port"`),
`fluids`, `bindings`, `inlets`, `outlets`, `boundary`. Every port is connected or named as a plant
port. A `Doublet` is designed from its `depth`, `gradient`, `surface_temperature`, `permeability`,
`thickness`, `nominal_flow` and `pump_efficiency`. Setpoints and other inputs (a heat pump's,
boiler's or chiller's `temperature_setpoint`, the air temperature, indoor conditions) go in
`boundary[""]["inputs"]` as `{module: {name: value}}`.

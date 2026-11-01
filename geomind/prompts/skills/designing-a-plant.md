How to design a geothermal heating and cooling plant in gemini for any case: reading the case, choosing families, sizing, optimising, and what gemini can run.

Reading the case:

- Read the case first with `read_case`: the time axis, the demand with its supply and return
  temperatures, the environment, the choices to search and the constraints gemini judges. When the
  state has none, `set_case` from the project or from the values the request gives. Never take the
  numbers of one case for another.
- A design needs a demand. When the request and the project give none, ask the user; a profile
  they give as daily values goes in with `save_profile`, and then into the case's demand.
- A limit the case does not state is not checked; do not invent one. A value the design needs and
  the case lacks (a return temperature, a price) is an assumption: ask the user, or record it with
  its value, `source: "default"` and `confirmed: false`.
- Read the demand with `read_profile` before you size: the peak, the annual energy, and when
  heating and cooling overlap.

Choosing families:

- Propose 4 to 6 materially different families, each `{id, summary, status}`: vary the number and
  depth of the doublets, how the supply temperature is reached (direct geothermal heat, a heat
  pump, a boiler, deeper wells), how cold is made (absorption chiller, compression chiller, heat
  pump) and storage or backup. Mark a family gemini cannot run `blocked`, with the reason.
- Start the one most likely to pass; keep the others for later rounds.

From a family to a design:

- `list_plants` shows what gemini can build; `read_plant` of a plant class or a stored design
  returns the plant and its `missing_parameters`: the values a run still needs, each of which you
  give with its unit or take from the case.
- `build_plant` stores the plant under a new name. `size_plant` sizes it for the case under a
  backup policy and stores the sized plant as another design; its notes say what was sized, what
  stayed, and what is broken. Then `simulate` the whole year and `check_results`.
- `optimize` searches the sized design for the values that minimise a metric, with its variables
  and the number of evaluations the case or the request gives. Its trials count as feasible only
  when they pass every constraint of the case. When it returns `feasible: false`, change the
  topology or the variables and search again.
- Get the numbers from gemini (`evaluate_module` on a doublet, `simulate` on a short window around
  the peak), never by hand. After any change, every earlier result of that design is stale.

What gemini can run (facts about gemini, not a design):

- A run plans the demand by rule from the case: sources load from the cheapest to the dearest and
  the limits are the case's constraints. `check_results` reports what the plan cannot enforce.
- No water circuit may return to itself unless gemini closes it; plan where each stream goes.
  Water that leaves a unit colder (a chiller's drive water, a user's return) cannot be mixed back
  into a fixed-temperature supply without lowering it.
- Gas the reservoir co-produces is a stream like any other: where it goes is a design decision,
  judged by the case's constraints, not by this skill.

The plant record (`plant`) is what `read_plant` returns and `build_plant` takes: modules, their
connections, and the parameters of each. Every port is connected or named as a plant port. Values
that the case owns (ground, reservoir, brine, air, temperatures of the grids) are the case's: a
plant record that states one is refused. Give every dimensional value as `{value, unit}`.

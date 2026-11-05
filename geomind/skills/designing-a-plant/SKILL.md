---
name: designing-a-plant
description: How to design a geothermal heating and cooling plant in gemini for any case: reading the case, choosing families, sizing, optimising, and what gemini can run.
tools: read_case, build_plant, patch_plant, read_plant
roles: all
---

Reading the case:

- Read the case first with `read_case`: the time axis, the demand with its supply and return
  temperatures, the site, the utilities, the requirements gemini judges by name, and the
  uncertainty. `read_case(section="economics")` gives the prices (`economics.json`). The case is set
  before design, from the user's files and answers, by the case's owner (`set_case`, with
  `save_profile` for a profile given as daily values); a design lead only reads it. Never take the
  numbers of one case for another.
- A requirement is a named limit of the case (`name`, `on`, `quantity`, `min`/`max`). A limit the
  case does not state is not checked; do not invent one. A case value the design needs and the
  case lacks (a price) is a change of the case: name it, with why, for the case's owner, who
  records it as an assumption or asks the user. A network return temperature is a design choice
  of the team within the case's limits: propose a value with its reason for the case's owner to
  record; never stop the design to wait for one.
- Tools worth knowing: `list_modules`, `describe_module` and `evaluate_module` (skill
  `evaluating-a-module`); `list_profiles`,
  `read_profile`; `read_result`; `read_study`. A model gemini lacks makes its family
  `blocked`; no code is written.
- Read the demand with `read_profile` before you size: the peak, the annual energy, and when
  heating and cooling overlap.

Choosing families:

- Design one family unless a comparison is asked for; for a comparison propose 2 to 6 materially
  different families, each `{id, summary, status}`: vary the number and
  depth of the doublets, how the supply temperature is reached (direct geothermal heat, a heat
  pump, a boiler, deeper wells), how cold is made (absorption chiller, compression chiller, heat
  pump) and storage or backup. Mark a family gemini cannot run `blocked`, with the reason.
- `list_plants` shows the project's plant files (`project_plants`) and the plant classes gemini
  can build. When the project has plants, start from one: `read_plant(project_plant=...)`, then
  `build_plant` it. Take a class or write a plant only when no project plant fits, and say why in
  an assumption. Build the other families to compare them.

From a family to a design:

- `read_plant(plant_class=...)` (or `project_plant=...` for a plant file of the project, which
  `list_plants` names, or `design=...`) returns `plant`, the plant file; `ranges`, the
  leaves that can be searched with their bounds; `options`; and `issues`, each with a path and what
  is missing or wrong. `checked_against` is `case` when the state has a case, else `plant`.
- Complete the plant file and pass it to `build_plant(plant=..., name=...)`. Every value with a
  dimension is `{"value", "unit"}`. Every source of a stream (a grid, a user, an air module)
  needs its fluid under `fluids` of the file, keyed by module name. The backup policy is
  `params.backup`: `{"value": "peak"}` covers the whole heating peak with the doublets off,
  `{"value": "none"}` only what the doublets cannot reach; there is no default, so state it and
  record it as an assumption. Values the case owns (ground, reservoir, brine, air, temperatures of
  the grids) are the case's: a plant file that states one is refused. gemini reports a file it
  cannot read as problems with a path, a message and suggestions; a file that builds is stored with
  its `issues`.
- `set_ranges(design, ranges, name)` puts the search on the leaves: `ranges` is `{leaf: {"min":
  {"value", "unit"}, "max": {"value", "unit"}}}`, and a count such as `size.doublets` takes plain
  numbers. A leaf is the path in the plant file without `params.`: `size.doublets`, `depth`,
  `heat_pump.capacity`, `d0.nominal_flow`. `options={leaf: [values]}` offers a list instead of a
  range. An unknown leaf is an error that lists the valid ones. Without ranges nothing is searched.
- Ranges and options come only from the user or the case (the ranges a plant file states). Never
  fill a missing one with a typical value. When `size_plant` or `optimize` reports one missing,
  record the question in the state's `questions`, call `ask_user` with the values you propose and
  a one-line reason, and set them with `set_ranges` only after the user confirms. In a run with no
  user to ask, the question stays open in the state and the run stops with it.
- `size_plant` sizes the built design for the case under its `params.backup` and stores the sized
  plant as another design; its notes say what was sized, what stayed and what is broken. Then
  `simulate` the whole year and `check_results`.
- Every study tool takes a `name` of its own, never reused (a taken name is refused), and returns
  the study as `study/<name>`, which is stored whole and never changes. Cite that key in an answer
  that relies on the study. `list_studies` lists the chat's studies and whether each is `current`
  (its case is still the state's), `read_study` reads one.
- `optimize(design, objective, evaluations, seed, name)` searches the ranges for the objective
  (`lcts`, `lcoh`, `lcoc`, `annualised_cost`, `co2`; a leading `-` maximises). gemini needs
  at least five evaluations per searched continuous leaf, so search few leaves with few
  evaluations. It returns the `best`, `feasible`, the `trials` and the stored design. A trial is
  feasible only when gemini's verdict says so. When it returns `feasible: false`, read the `reason`
  and change the ranges, the options or the topology.
- `run_study(designs, method, name, ...)` runs one study over several designs and ranks them:
  `method="minimize"` with `objective`, `evaluations` and `seed`, and `prepare=["size"]` to size
  each first. It returns one run per design (`feasible`, `metrics`, `ranks`, `pareto`, the stored
  `design`, named `design/<name>_<plant>`) and `best`. This is how families are compared.
- Get the numbers from gemini (`evaluate_module` on one module, `simulate` on a short window around
  the peak), never by hand. After any change, every earlier result of that design is stale.

What `check_results` returns:

- `feasible` is gemini's verdict, true when nothing is wrong. `reasons` lists what is, each with a
  `kind` (`requirement`, `failed_step`, `numerical` or `bound`), a `name` and a `message`.
  `requirements` is one check per unit of each requirement, and `failures` the failed steps by
  module and code. A failed step is a simulation problem to fix in the plant; a requirement is a
  limit of the case, never loosened.

What gemini can run (facts about gemini, not a design):

- A run plans the demand by rule from the case: sources load from the cheapest to the dearest.
- No water circuit may return to itself unless gemini closes it; plan where each stream goes.
  Water that leaves a unit colder (a chiller's drive water, a user's return) cannot be mixed back
  into a fixed-temperature supply without lowering it.
- Gas the reservoir co-produces is a stream like any other: where it goes is a design decision,
  judged by the case's requirements, not by this skill.

The plant file is what `read_plant` returns and `build_plant` takes: modules, their connections,
the parameters of each under `params`, and `fluids`. Every port is connected or named as a plant
port.

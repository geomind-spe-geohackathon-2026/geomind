---
name: designing-a-plant
description: How to design a geothermal heating and cooling plant in gemini for any case: reading the case, choosing families, sizing, optimising, and what gemini can run.
tools: build_plant, patch_plant, read_plant, merge_designs, list_plants, set_ranges
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
  `list_plants` names, `plant_version=N` for a saved version of the project, which
  `list_plants` lists in `project_versions` with name, note and who saved it, or `design=...`)
  returns `plant`, the plant file; `ranges`, the
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
- The doublet count is searched with `size.doublets` (1 to 3). A plant class takes it; a plant
  built from modules and connections takes it when it has exactly one doublet, `d0` (no `d1`):
  the search then copies `d0` and joins the copies in parallel. So build a free plant with one
  doublet `d0` when the number of doublets is to be searched; `d0`'s values hold for every copy.
- A question over sizes (the fewest doublets, the lowest flow, the smallest unit that still
  meets the case) is ONE search, never plants built one by one: `set_ranges` once on the
  design with every range the question names (e.g. `size.doublets` 1 to 3, `d0.nominal_flow`
  50 to 300 m3/h), then one `optimize` with the objective it asks for (or `size_plant`), and
  answer from that study. Each hand-built variant is another approval for the user.
- A range the user approved that `set_ranges` refuses is never dropped in silence: fix the path
  from the error's list and call again; if it still cannot be set, tell the user in your answer
  which range was not searched and why, and ask before you optimise without it.
- How to design, size and optimise for any case: the handbook `knowledge/handbook-design.md`
  in the Knowledge base, read by section with `read_rag(name, section=...)` (`outline=true`
  lists them): "10 Sizing and optimisation" (10.1 what to fix and what to search, 10.2 search
  ranges, 10.6 staying out of infeasible regions) and "11 Designing in gemini" (11.6 the good
  path, 11.8 common failures and their fixes).
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

## The tools

### `build_plant`

Build a plant from a plant file and store it as design/<name>; return its issues.

`plant` is the plant file (`read_plant` shows one). Every value with a dimension is
`{"value", "unit"}`. A file gemini cannot read is an error with gemini's problems
(`path`, `message`, `suggestions` such as the name probably meant) and nothing is
stored. A file without its header is `old_format`, the smallest plant file of gemini's
schema last in `suggestions`. A file that builds is stored even with `issues` (the values
still missing, checked as in `read_plant`): fill them in a new file or with `simulate`
`changes`. A plant with `type` takes only the modules of its class. To add a module to a
class (`thermal_storage`), name the class in `from_class` and give `plant` without
`type`, holding only what differs: the added `modules`, their `connections`,
`optional` or `choices`; the class gives every other module and connection, its size,
params and fluids. A connection you give at a port that takes one connection replaces the
class's connection there; connect each port of an added module (`describe_module` lists
them).

### `list_plants`

List the plant classes and the project's plant files; one class in full on request.

Without arguments: `project_plants`, the names of the project's plant files (`read_plant`
`project_plant` reads one; empty without a project or plants), and `plants`, each class
with its summary. With `plant_class`: its `capabilities` (`roles`, whether it is
`schedulable` and `ranges`, the leaves of the plant file that may state a search range,
which `set_ranges` sets) and `roles`, the quantities a module of each of its roles reports.
With `with_schema` true: `schema`, gemini's schema of the plant file `build_plant` takes.

### `merge_designs`

Join the designs the engineers patched side by side from `base`, stored as design/<name>.

Each of `designs` started from `base`; what each changed is applied to `base` in order.
Two designs that set one value differently are a conflict: nothing is stored and the error
names the path and both designs. gemini builds the result, and the answer lists what is
still missing, as `patch_plant` does.

### `patch_plant`

Change a stored design by a small patch, stored as design/<name>, and list what is missing.

`changes` is a JSON merge patch (RFC 7386) on the plant file of `design`, such as
`{"params": {"d0": {"drainage_radius": {"value": 500, "unit": "m"}}}}`: every value you
change, of one module or several, in one patch, never the whole file. `changes` may also be
the design engineers' list `[{path, value, source, reason}]`, `path` dotted
(`params.d0.depth`): put all engineers' changes into one call. gemini builds the result: a
patch it refuses is its error, and nothing is stored. A patch that changes nothing (`{}`, the
values already stored) is refused `no_change` and stores nothing. Returns the new design, its
`issues` (what is still missing, checked as in `read_plant`) and their count, `missing`. A
module's parameters written at the top or inside `modules` are taken as under `params`.

### `read_plant`

Read a project plant file, a stored design or a plant class: file, ranges, issues.

Give one of `project_plant` (a name from `list_plants` `project_plants`),
`design` as `design/<name>` or `plant_class` (a name from `list_plants`); with none,
the project's plant is read when it has exactly one file. Returns `plant` (the plant file
`build_plant` takes), `ranges` (each searchable leaf as `{min, max}` in display units),
`options` and `issues` (what is wrong or missing, with path, kind, quantity and accepted
units). With a case in the state the issues come from `gm.check(plant, case)` and
`checked_against` is `case`; without one they come from the plant alone (`plant`),
which lists as missing what the case would fill. A class is read without values: every
parameter it needs is missing until you fill it in a plant file.

### `set_ranges`

Set search ranges on a design: they come from the user or the case, so ask_user first.

Propose values with ask_user and set them only after the user confirms. The result is stored
as design/<name>.

`ranges` is `{path: {"min": {"value", "unit"}, "max": {"value", "unit"}}}`; a count such
as `size.doublets` takes plain numbers; a side left out is open and a leaf with neither
loses its range. `options` is `{path: [value, ...]}` for a leaf that takes one of a
list. A path is the leaf of the plant file without `params.`: `size.doublets`,
`depth`, `heat_pump.capacity`, `d0.nominal_flow`; `list_plants` `capabilities` and
`read_plant` `ranges` name them. An unknown path, or a bound gemini refuses, is gemini's
error with its path (for an unknown path, the valid ones). A study (`optimize`) searches
the leaves that state a range; the design read is not changed.

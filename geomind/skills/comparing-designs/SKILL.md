---
name: comparing-designs
description: How to compare designs: a superstructure (union_designs, evolve_structure) and its front, or several families in one run_study; how to pick the design and cite the study.
tools: union_designs, evolve_structure, run_study, read_study, list_studies, compare
roles: all
---

Superstructure (more than one sensible way to meet a service, in one design):

- Read the union's `structures` and `notes` before `evolve_structure`: a note is a value the
  alternatives state differently, where gemini kept the first and widened its range.
- After your review, call `evolve_structure` on the merged design with the objectives the case or
  your brief names, never ones you choose.
- Read the front and `rejected` (a structure gemini refused, with its reasons, such as a port left
  open). Take the best feasible design on the first objective, or the trade-off the brief asks
  for, and say why, quoting `stopped` and `why`; for more, `read_study`'s `explanation` and
  `table`, as gemini gives them, never computed.

Several families:

- Size each and compare them in one `run_study`: `designs`, `method="minimize"`, `objective`,
  `evaluations`, `seed`, `prepare=["size"]`.
- Keep the feasible design it ranks first (`best`), `simulate` it for the whole year, take it as
  final.
- Record the study in `design.study` as returned, and cite its `study/<name>` in
  `design.study.key` and in your answer. Every study has a new name.

## The tools

### `compare`

Compare stored runs on metrics such as `lcts` or `co2`; return one entry per run.

Each entry has the run's `reference`, its metric `values` in display units, `ranks` (1
is best, the feasible first), `pareto` and `feasible`, and the `reasons` of an
infeasible run.

### `evolve_structure`

Search a superstructure's structures and values by gemini's genetic algorithm.

`design` holds optional modules (`optional`) and choice groups (`choices`) with their
ranges; `objectives` are the metrics the case or the brief names to minimise (a leading
`-` maximises), never ones you choose. The evaluations, population, seed, polish and when
to stop early are settings, not yours. Each design of the front (none beats it on every
objective) is stored as `design/<name>_<n>`; the answer lists each with its `structure`,
`metrics`, `feasible` and `reason`, then `best` (on the first objective), the
`evaluations` run, the `invalid` candidates refused, each structure gemini refused before
any simulation with its reasons (`rejected`: a port a bypass leaves open, say), `stopped`
(gemini's `budget`, `stalled`, `converged` or `seconds`) with `why` in words, and
the `study` key. `read_study` of it gives gemini's `explanation` of the search and its
`table` of the front: quote them, never compute from them. Take the chosen design on as any
other: size, simulate, check.

### `list_studies`

List the studies stored in this chat: what ran, over which designs, and whether current.

Each item is `{study, tool, method, designs, best, current}`: the `study/<name>` key, the
study tool and the gemini method it ran, the names of the plants it ran over, the reference of
the design it recommends (`null` when it has none) and `current`, whether the state's case
is still the case it ran on. A study that is not current ran on an older case: run it again
under a new name before relying on it.

### `read_study`

Read a stored study: what ran, what came back, the designs it read and wrote, and its case.

`study` is a key such as `study/<name>` that a study tool returned or `list_studies`
listed. Returns `study` (gemini's study file as it ran), `result` (gemini's plain form of
what came back), `designs` (`{read, wrote}` references), `case` (the id of the case it
ran on), `tool` and `versions`.

### `run_study`

Run one study over several stored designs on the state's case and rank them.

This is how alternatives are compared: one study over several topologies. `method` is
`run` (simulate as it is), `minimize` (search each design's ranges), `sample` or
`sensitivity`; `prepare=["size"]` sizes each design first, from its ranges and its own
`params.backup`.
The settings a method needs are gemini's: `minimize` needs `objective`, `evaluations`
and `seed`; `sample` needs `metrics`, `samples` and `seed`; `sensitivity` needs
`metrics`. A missing or unread setting is gemini's error; none has a default. `name`
names the study `study/<name>` that records the call, and each design it ends with is
stored as `design/<name>_<plant name>`; a taken name is refused. Returns the `study` key
and `runs`, one per design in order: `plant_name`, `feasible`, `verdict`, `metrics`
in display units, `ranks` and `pareto` (rank 1 is best, over the objective then the
metrics), `note`, what the method `found` and the stored `design` the run ended with
(the sized or the best plant). `best` names the feasible design ranked first by the
objective, if any.

### `union_designs`

Join alternative designs into one superstructure by gemini, stored as design/<name>.

Each of `designs` is a whole alternative (a heating plant, the same with a heat pump and
cooling). gemini's `gm.plants.union` keeps a module of every design fixed and makes one of
some designs `optional` or a group of `choices`; a value the designs state differently
keeps the first design's, its range widened to cover every design's. Designs it cannot join
(one module name with two types, a module with no bypass) are gemini's `invalid_design`,
and nothing is stored. Returns the `design`, `structures` (`{design: structure}`, the
structure that gives back each design), `notes` (each value stated differently, `{path,
kept, values}` with `values` by design) and what is still missing, as `patch_plant`
does. `evolve_structure` then searches it. This is not `merge_designs`, which joins the
patches engineers made side by side on one design.

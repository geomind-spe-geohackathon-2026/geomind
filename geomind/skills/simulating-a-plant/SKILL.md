---
name: simulating-a-plant
description: How to simulate, size and optimise a stored design: simulate, size_plant and optimize; arguments, windows, changes, names, common mistakes.
tools: simulate, size_plant, optimize
roles: all
---

## The tools

### `optimize`

Search a stored design for the values that minimise a metric; store the best as `name`.

`objective` is a metric such as `lcts`, `lcoh`, `lcoc`, `annualised_cost` or `co2`;
a leading `-` maximises it. The variables are the ranges and options of the design (set them
with `set_ranges`); a design with none is gemini's error. The constraints are the case's
requirements, which the user owns. `evaluations` and `seed` have no default. `name`
names the stored best design and the study `study/<name>` that records the call; a taken
name is refused. Returns the `best` (its value, parameters and plant, in display units),
`feasible`, the `trials` run, the stored `design` and the `study` key. When no trial
is feasible the best is the least violating one and its `reason` says why. A search that
takes longer than 15 minutes comes back as a `timeout` error: ask for fewer evaluations.

### `simulate`

Simulate a plant on the state's case and store the results; return a reference and summary.

`design` is a stored design (`design/<name>`); `plant_version` is a saved plant version of the
project (`list_plants` project_versions), never with `design`. With neither, it runs the
project's LATEST plant version, and the summary's `plant` names that version: to report on an
older version, pass its `plant_version`.
`changes` holds parameters by module path for this run only, each a `{"value", "unit"}`
(a dimensionless parameter may be a number); the plant's own options go under `control`
(`{"control": {"dispatch": {"value": "least_cost"}}}`) or as `backup`. `start` and `end` are ISO 8601 times that cut
the case's time to a window, both inclusive: the run, its summary and its stored case are those
of the window (the case's `time` cut to it); to change the case's time itself use set_case.

The plan comes from gemini's schedule over the case. A step that fails is a failed row in the
summary and the run goes on. What `gm.check` finds wrong with the plant on this case (a
parameter without a value, equipment without a cost in the economics, a role a requirement
names) is a gemini error with each issue's path and message, and nothing runs.

The summary gives the steps, the failed steps with their first groups, the report's totals in
display units (MWh, MEUR, EUR/MWh, kt), gemini's `verdict`, the requirements that are not met
(`unmet`), the coverage of the demand, the plant and the case's time span.

### `size_plant`

Size a stored design for the state's case; store the sized plant as design `name`.

Sizing reads the plant's ranges (`size.doublets` min and max, when its class takes doublets)
and its `params.backup`; set what is missing with `set_ranges` first. The boiler's backup
policy is the plant's own `params.backup`: `peak` covers the whole heating peak with
the doublets off, `none` covers only what the doublets cannot reach. The policy has no
default: set it in the plant first, as an assumption when the user gave none. `name` names
the sized design and the study `study/<name>` that records the call; a taken name is
refused. Returns the new design reference, the `study` key,
gemini's notes (what was `sized` with its reason, what stayed `unchanged`, what is
`broken` and the `simulation` that judged it) and, as `patch_plant` gives them, the
sized plant's `issues` with their count `missing`: every value `simulate` still needs.

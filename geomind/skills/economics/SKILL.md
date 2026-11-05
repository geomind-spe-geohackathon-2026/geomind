---
name: economics
description: How to run the uncertainty, the sensitivity and the studies of a costed design, and cite them: calls, samples and seed, failed draws, study names and keys.
tools: sample_uncertainty, sensitivity, compute_kpis, estimate_costs
roles: all
---

Uncertainty and sensitivity run only when the task asks for an uncertainty, a range or a
sensitivity.

- Call `sample_uncertainty(design, metrics, samples, seed)` and `sensitivity(design, metrics)` on
  the verified design, with the metrics the task gives, else the costs you reported.
- Use the `samples` and `seed` the task gives. Where it gives none, choose them yourself and record
  each as an assumption `{id, text, value, source: "agent", confirmed: false}` with a one-line
  reason.
- A metric with `failed` draws is reported with that count.
- A case without declared uncertainty is an error: report it, never invent a range.

Studies:

- Every study you run gets a name of its own (`name`, never reused: a taken name is refused) and is
  stored as `study/<name>`.
- Cite the study key that a ranking, a range or a sensitivity relies on, in the state and in your
  answer.
- Use `list_studies` and `read_study` for the design lead's study; report a study that is not
  `current` as made on an older case.
- `run_study` with `method="run"` ranks stored designs; `compare` ranks stored results.

## The tools

### `compute_kpis`

Compute KPIs of stored results in display units, all of them without `names`.

The KPIs are the totals of `gm.evaluate.totals` (what crossed the plant's edge, coverage,
COP, peaks) and the metrics of `gm.evaluate.report`. `errors` maps each cost gemini gives
no value for to its error, `case_incomplete` with the path in the case when a value is
missing; it is left out when there is none.

### `estimate_costs`

Estimate capex, opex, LCOH, LCOC, LCTS, NPV, payback, CO2 and the annualised cost.

Every value is gemini's (`gm.evaluate`) on the run's case, in display units with its parts;
prices, discount rate, analysis period and cost factors are the case's `economics.json`.
Nothing the file lacks is filled: a cost that needs it is `{"error": {path, code, message}}`
with gemini's error (its code and the path in the case; a missing value is `case_incomplete`
with every value the costs need in `suggestions`), and when no cost can be computed the call
fails with that error. Set the values in the case's economics or ask the user.

### `sample_uncertainty`

Sample a design over the case's uncertainty (from the user or the case, never made up).

Returns a summary per metric.

The distributions are only those of the case's `uncertainty` (set them with `set_case`);
a case without any is an error. `samples` draws are simulated, one run each, from `seed`.
`name` names the study `study/<name>` that records the call; a taken name is refused.
Returns the `study` key and, in `summary`, each metric's `mean`, `p5`, `p50` and
`p95` in display units and `failed`, the number of draws left out because their run had
failed steps.

### `sensitivity`

Rank the case's uncertain values (from the user or the case, never made up) by effect.

The metrics are those of a stored design.

Each value the case declares an `uncertainty` for is set at its low and high bound. `name`
names the study `study/<name>` that records the call; a taken name is refused. Returns the
`study` key and `rows`, sorted by effect, each `{parameter, metric, low, high, at_low,
at_high, effect}`.

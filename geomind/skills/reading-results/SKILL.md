---
name: reading-results
description: How to read large results: summaries, references and `read_result`.
tools: read_result, read_stored, check_results
roles: all
---

A large result does not come back whole. You get a summary and a `reference` to the stored data.

- A summary gives the minimum, maximum and mean and the unit of each field. It is enough for most
  answers, so start there.
- When you need the values themselves, call `read_result(reference, path, field, start, end)`. `path`
  is the module path, `field` the field name, and `start` and `end` are ISO times of the case. Leave
  them out for the whole series, and prefer a short window.
- A question about a stored result is one `read_result` call, never code:
  - the peak or the lowest value and its day, the days or steps a value is not zero: the series
    of that field, `read_result(reference, path, field)`; its `summary` gives `max` and `min`
    with their `time`, `mean`, `active_steps`, `active_days`, `first_active` and `last_active`.
    Example: the peak heat delivered and its day is the summary's `max` of the heat field.
  - how many days a module ran (a doublet's pump, a boiler) and the energy it used:
    `read_result(reference, path)`; its `operation` gives `operating_days` and
    `operating_steps` (days with flow) of `steps`, and `energy_whole_run` per energy output in
    MWh. A module without an energy output (a heat exchanger) has no `energy_whole_run`: that
    does not mean it was unused; its `operating_days` and its duty series say how it ran.
  - energies of the whole plant: `check_results` `metrics` (`heat_delivered`, `cold_delivered`,
    `boiler_heat`, `electricity_bought`, `gas_bought`); the heat not from the boiler is
    `heat_delivered` minus `boiler_heat`, one `calculate` call.
  - whether each requirement passes, with its number: `check_results` `requirements`; each entry
    has `name`, `passed`, `value` (the worst value of the run: brine cooling in K, running days
    in d, reinjection ratio, flow), `limit`, `unit_path` (which doublet or module) and
    `worst_step` (its day). Quote `value` against `limit` for every requirement; never write that
    a requirement "rests on the verdict" when its entry has a value.
  - Whether the plant is feasible is `check_results` `feasible` (gemini's verdict) alone; a
    requirement's `passed`, or a count of passed checks, is never the plant's verdict: a plant that
    gives no cooling can pass every requirement and still be infeasible. Write "feasible" or
    "infeasible" from `feasible`, with its reasons (QA-162).
  - a doublet's production flow against its range: the series `<doublet>.reservoir.liquid_flow`
    (the liquid at brine density, what the requirement judges). The pump's
    `fluid_in.volume_flow` also counts the free gas at the intake pressure, so it reads higher
    (341 m3/h for 300 m3/h of liquid) and is no flow limit.
  Use `run_python` only for what none of these gives, and never to sum a power series into an
  energy: the energies come from gemini in MWh.
- A wrong `path` or `field` is an error result that lists what exists, so read it and try again.
- Keep the reference of a result you record with `update_state`, so that it can be read again later.
- `check_results` of a result returns `feasible` (gemini's verdict), `reasons` (each with a `kind`
  of `requirement`, `failed_step`, `numerical` or `bound`, a `name` and a `message`), the
  `requirements` it judged and the `failures`. Report the reasons as they are; a result with a
  failed step is not feasible, whatever its totals say.
- Values come in display units (MW, MWh, degC, Pa, EUR/MWh); report each with its unit.

## The tools

### `check_results`

Check stored results against the case they ran on: gemini's verdict and report.

Returns `{feasible, reasons, requirements, failures, metrics}`, gemini's, in display units.
`feasible` is `gm.evaluate.verdict`, the one rule: true when nothing is wrong. `reasons`
says what is, each with a `kind` (`requirement`, `failed_step`, `numerical` or
`bound`), a `name` and a `message`. `requirements` is one check per unit of each
requirement of the case and per service supply temperature, `failures` the failed and skipped
steps by module and code, and `metrics` the energies, capacities, costs and CO2. A limit is a
requirement of the case: set it with `set_case`.

### `read_result`

Return one series of a stored run, or a summary of the run or of one module path.

`reference` is what simulate returned. With `path` and `field` it returns the series
`{time, value, unit, summary}`, `summary` being `{steps, unit, max: {value, unit, time}, min:
{value, unit, time}, mean, active_steps, active_days, first_active, last_active}` (active: not
zero; days are UTC calendar days); `start` and `end` are ISO 8601 times, both inclusive. With
only `path` it returns `{<path>: {field: {min, max, mean}}, operation: {steps, operating_steps,
operating_days, energy_whole_run}}`, and with neither min, max and mean of every module of the
whole run. Power is in MW, temperature in degC, pressure in bar, flows in m3/h or kg/s.

### `read_stored`

Return a result that was stored by reference, whole or one part of it.

`reference` is the `result-...` (or `output-...`) key of a result that came back as a
reference and an outline. `path` is dotted keys and list indexes into it, such as
`capabilities.HeatingPlant` (`/` reads as `.`). A part too long to show whole comes
back as its keys (or its length) and an outline, with the path to read deeper.

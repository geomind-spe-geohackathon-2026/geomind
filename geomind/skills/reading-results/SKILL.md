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
`{time, value, unit}`; `start` and `end` are ISO 8601 times, both inclusive. With only
`path` it returns min, max and mean of each field of that module, and with neither of the
whole run. Power is in MW, temperature in degC, pressure in bar, flows in m3/h or kg/s.

### `read_stored`

Return a result that was stored by reference, whole or one part of it.

`reference` is the `result-...` (or `output-...`) key of a result that came back as a
reference and an outline. `path` is dotted keys and list indexes into it, such as
`capabilities.HeatingPlant` (`/` reads as `.`). A part too long to show whole comes
back as its keys (or its length) and an outline, with the path to read deeper.

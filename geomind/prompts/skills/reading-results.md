How to read large results: summaries, references and `read_result`.

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

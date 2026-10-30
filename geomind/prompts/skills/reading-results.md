How to read large results: summaries, references and `read_result`.

A large result does not come back whole. You get a summary and a `reference` to the stored data.

- A summary gives the minimum, maximum and mean and the unit of each field. It is enough for most
  answers, so start there.
- When you need the values themselves, call `read_result(reference, path, field, start, end)`. `path`
  is the module path, `field` the field name, and `start` and `end` are sample positions, the first
  sample being 0. Leave them out for the whole series, and prefer a short slice.
- A wrong `path` or `field` is an error result that lists what exists, so read it and try again.
- Keep the reference of a result you record with `update_state`, so that it can be read again later.

---
name: python
description: How to run Python with `run_python` in the sandbox: inputs only as references to sourced values, no data in the code, numbers kept as calculations through result.json.
tools: run_python
roles: all
---

Use `run_python` for work one `calculate` call cannot do: a loop over a profile, a fit, a table,
a search over options. For one operation on a few values, use `calculate` (`calculator`).

The sandbox: Python 3.11 with gemini (`import gemini as gm`) and numpy, no network, a time and
memory limit, a small working folder that is gone after the call. Every call starts fresh.

Inputs:

- `inputs` maps a variable name to a reference to a sourced value, the same references as
  `calculate`'s operands: `{"case": "<path>"}`, `{"assumption": "<id>"}` (confirmed),
  `{"catalogue": "<row id>"}`, `{"stored": "<result-...>", "path": "<dotted>"}`,
  `{"calculation": "<id>"}`, and plain `{"number": 24, "unit": "h"}` or `{"constant": "pi"}`.
  At least one input has a source, or the code reads a project file. The code gets each as a
  plain number in its unit; `UNITS["name"]` gives the unit.
- `files` names project files; the code reads them as `files/<name>` (copies: the project's own
  files never change).
- The code holds no data: no number above 10 as a literal (indices, counts and small exponents
  are fine). A price, a depth, 24, 1000 or 3600 typed into the code is refused: pass the value as
  an input, and convert units with `gm.units.Quantity(value, UNITS["x"]).to("MWh")` or
  `gm.units.convert`.

Outputs:

- To keep a number, write `result.json`:
  `{"annual_heat": {"value": 6.0, "unit": "GWh", "label": "annual heat delivered"}}`. Each entry
  becomes a calculation (C1, C2 ...) that cites the code and its inputs; cite its id from then on,
  and pass it to `calculate` or another `run_python` as `{"calculation": "C3"}`.
- The unit of each result is one gemini knows, `-` for none.
- Files written under `out/` come back as text (cut when long). `stdout` and `stderr` are cut too:
  print short summaries, not whole series.
- `status` is `ok`, `failed` (read `stderr`, fix the code, call again) or `timed_out` (make the
  work smaller).

When the run has no sandbox, `run_python` is not offered; do the work with `calculate`.

## The tools

### `run_python`

Run Python in a sandbox (no network, gemini installed) on sourced inputs.

`inputs` maps a variable name to a reference to a sourced value, the same references as
calculate's operands (plain numbers too, but one input at least has a source, or a file is
read); the code gets each as a number in its unit, and `UNITS` gives the unit
of each. Never type data into the code: no number above 10 as a literal. `files` names project
files the code reads as `files/<name>`. To keep a number, write `result.json` as
`{"name": {"value": ..., "unit": "...", "label": "..."}}`: each becomes a calculation with an
id. Files written under `out/` come back. `purpose` says what the code is for. Read the
skill python for the rules.

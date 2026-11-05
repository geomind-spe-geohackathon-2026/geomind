---
name: calculator
description: How to derive a number with `calculate`: operands are references to sourced values, gemini converts the units, the result is a calculation with an id you cite.
tools: calculate
roles: all
---

Never type a number you made up or worked out in your head. When a value has to be derived (a
sum, a ratio, an energy from a power and a time, a cost from a price and a size), call `calculate`
and cite the calculation's id from then on.

Operands: each is a reference to a value that already has a source, never a bare number.

- `{"case": "<path>"}`: a field of the case, dotted, such as `site.depth` or
  `demand.heating.peak`. It must hold one number or `{"value", "unit"}`.
- `{"assumption": "<id>"}`: an assumption of the problem state the user has confirmed, with its
  value. An unconfirmed assumption is refused: ask the user first, with its source.
- `{"catalogue": "<row id>"}`: a row of the cost catalogue `knowledge/cost-sources.csv`; its 2015
  value and unit are used, and its citation goes with the result.
- `{"stored": "<result-... reference>", "path": "<dotted path>"}`: one value of a result stored by
  reference (`read_stored` shows its parts).
- `{"calculation": "<id>"}`: an earlier calculation, such as `C2`.

A value from the web, a connector or the user's words enters only after the user approves it as
an assumption with its source; then reference the assumption.

Operations: `add`, `subtract`, `multiply`, `divide` (two operands), `power` (one operand and an
integer `exponent`, the only plain number allowed), `min`, `max`, `sum`, `mean`.

Units:

- `unit` is the unit you want the result in, one gemini knows (see `gemini-units`); `-` for a
  dimensionless result. gemini converts every operand; never convert by hand, never put 24, 1000
  or 3600 anywhere.
- add, subtract, min, max, sum and mean need operands of one dimension. A wrong `unit` is an
  error that lists the units of the result's dimension.
- subtract of two temperatures is a difference: give it in `K`. Never add absolute temperatures;
  a mean of temperatures is fine.

The result has `id`, `label`, `value`, `unit`, `expression` and `operands`, each operand with its
value and `source`. It is kept in the problem state (`Calculation C1: ...`); `update_state`
cannot write calculations. When you report or record a derived number, give its calculation id.
A chain of steps is one call per step, each citing the one before.

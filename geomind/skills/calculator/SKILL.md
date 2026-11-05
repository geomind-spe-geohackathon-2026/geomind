---
name: calculator
description: How to derive a number with `calculate`: operands are sourced values (plus plain numbers and pi or e), gemini converts the units, the result is a calculation with an id you cite.
tools: calculate
roles: all
---

Never work a number out in your head. When a value has to be derived (a sum, a ratio, an energy
from a power and a time, a cost from a price and a size), call `calculate` and cite the
calculation's id from then on.

Operands: each is an object. Every calculation needs at least one operand with a source:

- `{"case": "<path>"}`: a field of the case, dotted, such as `site.depth` or
  `demand.heating.peak`. It must hold one number or `{"value", "unit"}`.
- `{"assumption": "<id>"}`: an assumption of the problem state the user has confirmed, with its
  value. An unconfirmed assumption is refused: ask the user first, with its source.
- `{"catalogue": "<row id>"}`: a row of the cost catalogue `knowledge/cost-sources.csv`; its 2015
  value and unit are used, and its citation goes with the result.
- `{"stored": "<result-... reference>", "path": "<dotted path>"}`: one value of a result stored by
  reference (`read_stored` shows its parts).
- `{"calculation": "<id>"}`: an earlier calculation, such as `C2`.

Beside them, and never alone:

- `{"number": 24, "unit": "h"}`: a plain number you give, shown to the user as `24 h (plain)`.
  Only for a fact that needs no source (hours in a day, a count you were told, a factor of a
  formula); never for a price, a property or a site value: those need a source. Leave out `unit`
  for a dimensionless number.
- `{"constant": "pi"}`, `{"constant": "e"}` or `{"constant": "g"}`, the standard gravity
  9.80665 m/s2 (a hydrostatic pressure is density × g × depth).

A calculation whose operands are all plain numbers or constants is refused.

A value from the web, a connector or the user's words enters only after the user approves it as
an assumption with its source; then reference the assumption.

Operations: `add`, `subtract`, `multiply`, `divide` (two operands), `power` (one operand and an
integer `exponent`), `min`, `max`, `sum`, `mean`. The exponent is a plain integer in the
call itself, not an operand: it is structure (a square, a cube), never data, so it needs no
source and no sourced operand beside it.

Units:

- `unit` is the unit you want the result in, one gemini knows (see `gemini-units`); `-` for a
  dimensionless result. gemini converts every operand: give each number in its own unit and
  never a conversion factor (no 1000 for kW to MW, no 3600 for h to s).
- add, subtract, min, max, sum and mean need operands of one dimension. A wrong `unit` is an
  error that lists the units of the result's dimension.
- subtract of two temperatures is a difference: give it in `K`. Never add absolute temperatures;
  a mean of temperatures is fine.

The result has `id`, `label`, `value`, `unit`, `expression` and `operands`, each operand with its
value and `source`. It is kept in the problem state (`Calculation C1: ...`); `update_state`
cannot write calculations. When you report or record a derived number, give its calculation id.
A chain of steps is one call per step, each citing the one before.

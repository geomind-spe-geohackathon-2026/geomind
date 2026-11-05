---
name: evaluating-a-module
description: How to run one gemini module at one operating point with `evaluate_module`, and read a module's inputs with `describe_module` and `list_modules`: arguments, forms, filling from a design or a result, common mistakes.
tools: evaluate_module, describe_module, list_modules
roles: all
---

## Find the module

- `list_modules(category=None)`: every module type with its category and summary.
- `describe_module(name)`: one type (`HeatPump`, `ESP`): its parameters and controls one per line
  (type, quantity, units, bounds, options; `*` = no default, you give it), its inlets and outlets
  and outputs. A parameter and a control are different sections: the line says which.

## evaluate_module

`evaluate_module(name, parameters, inlets, controls, state, dt, design, result, time)` runs one
module at one point and answers in gemini's display units (MW, degC, bar, m3/h; a quantity with
no display unit stays in SI).

- `name`: the module type (`HeatPump`), or, with `design` or `result`, the module's id in that
  plant (`heat_pump`, `d0.esp`): then its type and values come from the plant.
- `parameters`: `{name: value}`. A value with a dimension is `{"value": 150, "unit": "m3/h"}`,
  never text such as `"150 m3/h"`; a choice or a fraction is bare (`"heating"`, `0.5`).
- `controls`: `{name: value}` in the same form, for the names `describe_module` lists as
  controls (`temperature_setpoint`, `production_rate`, `frequency`). The unit must be one of the
  control's: `production_rate` is a mass flow (`kg/s`, `t/h`); a volume flow needs the brine
  density first (`calculate`).
- `inlets`: `{port: {"fluid": {...}, "T": {...}, "p": {...}, "m_dot": {...}}}`, one entry per
  required stream inlet (`describe_module` lists them), `flow` in place of `m_dot` for a volume
  flow. `fluid` holds gemini's fluid fields: `kind` (`brine`, `water`, `glycol_water`, `steam`,
  `gas`), `salinity`, `gas_liquid_ratio`, `gas_composition` and `density`, `viscosity`,
  `specific_heat` as `{value, unit}`; `kind` alone uses gemini's properties.
  One inlet in full: `{"fluid_in": {"fluid": {"kind": "brine", "density": {"value": 1000,
  "unit": "kg/m3"}}, "T": {"value": 80, "unit": "degC"}, "p": {"value": 10, "unit": "bar"},
  "flow": {"value": 100, "unit": "m3/h"}}}`.
- `design` (`design/<name>`): with `name` a module id (or a class the design holds once, such as
  `Doublet`), the design's values of that module are used for every parameter and control the
  call does not give. A design holds no stream's state: a module with stream inlets (a doublet's
  `return_in`, a heat pump's `source_in`) needs them in `inlets` with `design`, or a `result`
  instead. Example, a doublet of a design not yet simulated: `evaluate_module(name="d0",
  design="design/x", inlets={"return_in": {"fluid": {"kind": "brine"}, "T": {"value": 40,
  "unit": "degC"}, "p": {"value": 10, "unit": "bar"}, "flow": {"value": 300, "unit":
  "m3/h"}}})`, with the temperature, pressure and flow of your design.
- A refused call is never sent again unchanged: an identical call that already failed is not
  run (`failed_before`) until something else succeeded in between.
- `result` (`result/<id>`, a simulated run) and `time` (ISO 8601, a step of the run): with `name`
  a module id, the plant's values as with `design`, and `T`, `p` and `m_dot` of every required
  inlet are read from that step; give each inlet's `fluid` only (a result keeps no fluid). Without
  `time` the step of the largest inflow is used, and the answer says which.
- `state` and `dt`: only a module with state (a storage): its state at the start as
  `{name: {value, unit}}` and the step as `{value, unit}`; the answer's `state` is the state after.
- The answer's `notes` say what the tool fixed in the call (a type name, a control moved out of
  `parameters`, a range dropped) or took from the design or result: write the next call so.

Example: the heat pump of a simulated design at its peak step:

```json
{"name": "heat_pump", "result": "result/3fc37eb6fdb9a22b",
 "inlets": {"source_in": {"fluid": {"kind": "brine"}}, "sink_in": {"fluid": {"kind": "water"}}},
 "controls": {"temperature_setpoint": {"value": 100, "unit": "degC"}}}
```

Common mistakes:

- `inlets: []` or no inlets on a module that has required stream inlets: refused; give them, or
  `result` to read them.
- A whole `Doublet` (or a plant) to learn its flow: it needs every inner value; read the plant's
  `issues` and gemini's check instead. `evaluate_module` is for one module at one point.
- A machine the plant file gives and the case does not change needs no evaluation.
- A value the reservoir needs from the case (`productivity_index` of a reservoir run alone) is
  required here: read it from the case or the plant, never a number of yours.

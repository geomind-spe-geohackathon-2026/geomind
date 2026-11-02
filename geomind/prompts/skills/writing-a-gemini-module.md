How to write a gemini module that the library lacks, in general: the contract, categories, ports, units, parameters and the check.

Write a module only when `list_modules` has no class for the equipment and no plant can be built from existing ones. Reuse the shipped classes (`describe_module`) as references.

The contract:

- A module is a class that subclasses `gm.modules.Module`. It declares in `__init__` (call `super().__init__()` first, no arguments) and computes in two pure methods:
  `forward(self, inputs, inlets, state)` returns `(outputs, outlets)`, and, only if it has states,
  `update(self, inputs, inlets, outlets, state, dt)` returns the state at the end of the step.
  The parameter names of `forward` are exactly those.
- Pure means: never write to `self` inside a call. `self` holds the parameters, set before a run. Controls and boundaries are read from `inputs["name"]`, an inlet from `inlets.name`, the state from `state["name"]`. A value that changes in time is an argument or a local variable.
- `outputs` has a key for every declared `Output`; `outlets` has a key for every declared `Outlet` and for every inlet the module draws (a single `Power` inlet is drawn: return it under its own name). A missing or an extra key is an error.
- Declarations come from `gemini.modules`: `Parameter`, `Control`, `Boundary`, `Inlet`, `Outlet`, `Output`, `State`. Quantity types come from `gemini.units.quantities` (`Power`, `Temperature`, `VolumeFlow`, `Efficiency`, `Fraction`, `Pressure`, ...). Streams are `gemini.streams.Stream`.
- Use `gemini.ops` (`ops.minimum`, `ops.where`, ...) and the functions of `gemini.physics` instead of writing a formula again; do not use `if` on a value that varies, use `ops.where`.
- No file, network or global state. The module is one file with the imports it needs.

Category: a class from outside states `category = "..."` in its body, one of `gm.modules.categories()` (subsurface, wells, pumps, treatment, exchangers, heating, cooling, power, storage, piping, grids, environment, control). Choose the one of what the equipment does. A class with a category registers itself under its class name when the file is imported, and a plant dict can then name it by `type`. A name already registered by another class is refused.

Ports: a port carries a `Stream` (`Inlet(Stream, kind="hot_water")`) or a `Power` (`Inlet(Power, kind="electricity")`). `kind` is a label only (brine, hot_water, chilled_water, gas, electricity, fuel, heat, air, waste, chemical); connections check that the kinds match. A single `Power` inlet is drawn: no value is given for it, `forward` computes it.

Units and values:

- Every scalar number is declared with a quantity type that has a unit, never a bare `float`. Arrays of coefficients are exempt.
- Inside `forward` and `update` everything is SI (W, K, Pa, m3/s, kg/s). Never convert units in the module.
- A value given to or read from a module is `{"value": 2, "unit": "MW"}`: gemini converts (display units for people, SI inside). Never give a bare number with a unit.
- A parameter that the equipment has no honest default for has no `default`. Do not invent a default; the plant or the case gives the value. A parameter with a default says so in its description.

A minimal example of the pattern:

```python
from gemini import ops
from gemini.modules import Control, Inlet, Module, Outlet, Output, Parameter
from gemini.physics import energy
from gemini.units.quantities import Efficiency, Power


class ResistanceHeater(Module):
    """Electric resistance heater that delivers the heat asked, up to its capacity."""

    category = "heating"

    def __init__(self):
        super().__init__()
        self.capacity = Parameter(Power)
        self.efficiency = Parameter(Efficiency)
        self.requested = Control(Power)
        self.power_in = Inlet(Power, kind="electricity")
        self.heat_out = Outlet(Power, kind="heat")
        self.duty = Output(Power)

    def forward(self, inputs, inlets, state):
        duty = ops.minimum(inputs["requested"], self.capacity)
        power_in = energy.input_power(duty, self.efficiency)
        return dict(duty=duty), dict(heat_out=duty, power_in=power_in)
```

The check:

1. `write_module(name, code)` stores the file as `module/<name>.py` (`name` is a Python identifier; writing again replaces it).
2. `test_module(name, example=None)` runs `gm.modules.check` on each module class of the file inside the sandbox, never in this process, and returns `{name, passed, modules, problems, undecided}`. A problem is `{path, message}` with the path `<Class>.<check>`; `import` means the file failed to import. The checks are `is_module`, `instantiate`, `category`, `forward_signature`, `units`, `describe` and `call`.
3. A module with a parameter, control or inlet that has no default is `undecided` on `call` until you give `example`, the arguments of `gm.call`: `{"parameters": {"capacity": {"value": 2, "unit": "MW"}}, "inlets": {...}, "controls": {...}}`. Give an example with values you can justify, never with invented design numbers in the module itself.
4. Read each problem, fix the code, write it again and test again until `passed` is true and nothing important is undecided.

A module that passes the check is not yet part of a plant run: this harness cannot load the file into `build_plant`. Say so; do not claim a design uses it.

Write one module per file. Keep a module small: declare, call physics, return. A fitting or a calibration is not a module.

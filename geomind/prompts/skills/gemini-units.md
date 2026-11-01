Units gemini accepts and returns, and how to state them.

gemini works in SI internally, and geomind speaks display units: a value you read comes with its
unit (MW, degC, bar, m3/h, kg/s), and a value you give is a quantity.

- A parameter, control, change or bound takes `{"value": 150, "unit": "m3/h"}`. Never a bare
  number where the parameter has a unit, and never a text such as `"150 m3/h"`. gemini converts the
  quantity; never convert a value yourself.
- gemini knows a fixed list of units. These work: `m3/h`, `m3/s`, `l/s`, `t/h`, `kg/s`, `bar`,
  `barg`, `bar(g)`, `Pa`, `kPa`, `MPa`, `degC`, `C`, `K`, `K/km`, `W`, `kW`, `MW`, `GW`, `J`, `kWh`, `MWh`, `GWh`, `m`,
  `km`, `mm`, `ft`, `in`, `Hz`, `rpm`, `mD`, `mPa*s`, `kg/m3`, `Nm3/m3`, `mg/l`, `ppm`, `d`, `h`,
  `min`, `s`. These do not: `L/s`, `psi`, `degF`.
- `degC` (or `C`) is a temperature, `K` a temperature or a temperature difference: a brine cooling
  of 40 degrees is `{"value": 40, "unit": "K"}`.
- An unknown or wrong unit is an error result that names the nearest unit. Read it and give the value
  in a unit it knows.
- A result is read in display units: power in MW, temperature in degC, pressure in bar, volume
  flow in m3/h, mass flow in kg/s, each next to its value. Read the unit from the result; do not
  assume one, and report it with every number.
- Always state the unit of every number you report.

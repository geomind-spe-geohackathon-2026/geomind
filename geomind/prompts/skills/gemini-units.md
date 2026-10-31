Units gemini accepts and returns, and how to state them.

gemini works in SI: metres, kilograms, seconds, kelvin, pascal, watt, joule, cubic metres per second.

- A parameter, control or input takes a number in its declared SI unit, or a text with a unit, such
  as `"150 m3/h"`, `"16 bar"`, `"80 degC"` or `"2 MW"`. gemini converts the text; never convert a
  value yourself.
- gemini knows a fixed list of units. These work: `m3/h`, `m3/s`, `l/s`, `t/h`, `kg/s`, `bar`,
  `barg`, `bar(g)`, `Pa`, `kPa`, `MPa`, `degC`, `C`, `K`, `K/km`, `W`, `kW`, `MW`, `J`, `kWh`, `m`,
  `km`, `mm`, `ft`, `in`, `Hz`, `rpm`, `mD`, `mPa*s`, `kg/m3`, `Nm3/m3`, `mg/l`, `ppm`, `d`, `h`,
  `min`, `s`. These do not: `MWh`, `GWh`, `GW`, `L/s`, `psi`.
- `degC` (or `C`) is a temperature, `K` a temperature or a temperature difference: a brine cooling
  of 40 degrees is `"40 K"`.
- An unknown or wrong unit is an error result that names the nearest unit. Read it and give the value
  in a unit it knows.
- Results are in the declared SI unit of each field, and a summary names it. Read the unit from the
  result; do not assume one.
- A temperature in a result is in kelvin, a pressure in pascal, a power in watt and an energy in
  joule. Report them in the units the user asked for, and say which conversion you made: 353.15 K is
  80 °C, 3.6e12 J is 1 GWh.
- Always state the unit of every number you report.

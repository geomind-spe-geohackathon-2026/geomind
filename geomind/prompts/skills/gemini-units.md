Units gemini accepts and returns, and how to state them.

gemini works in SI: metres, kilograms, seconds, kelvin, pascal, watt, cubic metres per second.

- A parameter or control takes a number in its declared unit, or a text with a unit, such as
  `"150 m3/h"`, `"16 bar"`, `"80 C"` or `"2 MW"`. gemini converts the text; never convert a value
  yourself.
- gemini knows a fixed list of units, and not every prefix. `m3/h`, `m3/s`, `l/s`, `t/h`, `kg/s`,
  `bar`, `Pa`, `C`, `K`, `W`, `kW`, `MW`, `kWh`, `J`, `m` and `ft` work. `km`, `mm`, `in`, `kPa`,
  `MPa` and `rpm` do not.
- An unknown or wrong unit is an error result that names the nearest unit. Read it and give the value
  in a unit it knows.
- Results are in the declared unit of each field, and a summary names it. Read the unit from the
  result; do not assume one.
- A temperature in a result is in kelvin and a pressure in pascal. Report them in the units the user
  asked for, and say which conversion you made: 353.15 K is 80 °C.
- Always state the unit of every number you report.

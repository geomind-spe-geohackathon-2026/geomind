# data-equipment.csv

A catalogue of general equipment parameters for a geothermal heating and cooling plant: the model
values gemini asks a plant to state (well and pipe roughness, reservoir skin, ESP limits, heat
pump and chiller efficiencies, treatment pressure drops, cooler settings). It is reference data
for any plant, not a code default and not the values of one case: each row keeps its source and
its status. Sizes (capacities, conductances, lengths) are not in it; they belong to a design.

## Columns

| Column | Meaning |
|---|---|
| `id` | The row's id, unique. |
| `group` | The kind of equipment (wells, pumps, heat pumps, chillers, coolers, ...). |
| `item` | What the value is, in words. |
| `path` | The gemini module class and its parameter (`HeatPump.carnot_fraction`); a doublet's own parameter is `Doublet.<name>`, its wells' `ProductionWell.<name>` (the riser and the injector take the same value). |
| `value` | The value, a number or a model choice. |
| `unit` | The unit of `value`; empty for a model choice, `-` for a ratio. |
| `status` | `secondary`: from the source named, read second-hand and not re-verified; `placeholder`: an assumption with no verified source. |
| `source`, `publisher`, `year`, `url` | Where a `secondary` value comes from; empty for a `placeholder`. |
| `note` | Why the value, or how it is meant. |

## Use

- A value proposed from this catalogue is shown to the user with its row id and source and
  recorded as an assumption; a `placeholder` row is an assumption to confirm
  (`confirmed: false`), never a fact.
- A parameter that no row gives is asked of the user, or searched in the handbooks, never made up.

## Origin (2026-11-05)

51 rows (10 secondary, 41 placeholder): the general equipment values that gemini's sample plants
state, moved out of a case's assumptions document so that they serve any plant (QA-340). Values
that only fit one case (its pump efficiency, sizes, search ranges and derived temperatures) were
left with that case.

## Additions (2026-11-05, QA-351)

11 rows (1 secondary, 10 placeholder), the equipment values gemini's check still asked for after
the first 51 rows, found by running `gm.check` on every plant class of gemini 0.6.34 with no
parameters and comparing with this catalogue: the calibration factors of wells and ESP (none),
the ESP alarm and operating window used when no pump model is chosen, the injection pump's model
and motor frequency, the supply margins of boilers and absorption chillers, and the heat
exchanger's pressure drop. Rows: 62 (11 secondary, 51 placeholder).

## Values that are not in this catalogue, and where they come from

Each is a size or an operating choice of one design, so no catalogue can give it. Never search
the web for them:

| Path | Where it comes from |
|---|---|
| `capacity` of a heat pump, chiller or boiler; `nominal_flow` of a doublet; `depth` | `size_plant` and the search over the ranges the user approves |
| `injection_pump.nominal_flow`, `nominal_head`, `pressure_setpoint` | `size_plant` (from the doublets it serves) |
| `injection_pump.efficiency` | the production pump's efficiency (`dN.pump_efficiency`), which the case's files or the user give |
| `nominal_mass_flow` of a filter, desander or heat exchanger side | the design flow of the stream it carries: brine, the doublets' flow times the density; network, duty / (c_p (T_supply - T_return)) |
| `heat_exchanger.thermal_conductance` | the design duty and the chosen approach, Q = UA dT_lm |
| `heat_pump.minimum_source_outlet_temperature` | the production temperature less the case's brine cooling limit, or a chemistry limit |
| `<cooler>.capacity` | the heat rejected: cold plus drive heat (compression: cold x (1 + 1/COP)) |
| `<cooler>.flow` (first guess of a closed loop) | capacity / (c_p dT) with c_p = 4186 J/kg/K of water and the loop's rise, about 10 K |
| `<cooler>.temperature_setpoint` | below the chiller's condensing (or absorber) limit; a case's assumptions document may give it |
| pipe `length`, `elevation_change` | the site: the case, its files or its assumptions document; never invented |
| pipe `inner_diameter` | 1 to 3 m/s at the design flow |
| `params.control.dispatch`, `params.control.outages`, `params.backup` | the one value gemini's check suggests (`least_cost`, `lowest_demand`; `peak` or `none`) |

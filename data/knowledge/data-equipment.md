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

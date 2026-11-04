# Prompt: find cited values for the missing geothermal cost and economics data

Paste everything below the line into a new Claude session that has web search. Attach
`cost-sources.csv` (from the geomind repo, `data/knowledge/cost-sources.csv`) to the session.

---

You are a research assistant for a geothermal district heating and cooling design study (SPE Europe
Energy GeoHackathon 2026). The design tool takes every price and factor from a cited cost
catalogue, `cost-sources.csv` (attached). Some keys have no row, and 16 rows are `placeholder`
with no source. Your job is to find **real, cited values** for them on the web and give them back
as new CSV rows that can be appended to the catalogue unchanged.

## Hard rules

1. **Never invent or estimate a value.** Every number must be found in a public source you
   opened: a report, a paper, an official statistic or a vendor datasheet. No values from memory.
2. Every row has a working `url`, a `page` (page, table, sheet or slide), and a `quote` with the
   exact source text that holds the number.
3. If you cannot find a source for a key, still write the row with `status` `placeholder`, an empty
   `value`, and a `note` that says what you searched and why it failed. Do not fill the gap with a
   guess.
4. Prefer this order: the Netherlands, then NW Europe (DK, DE, BE, FR), then EU-wide, then
   international. Prefer official or peer-reviewed sources (DEA Technology Data, PBL/SDE++, TNO,
   ECN, IEA, IRENA, Eurostat, CBS, IPCC, EU ETS) over blogs or vendor marketing.
5. Prefer sources from 2015 or later. Take older ones only if nothing newer exists, and say so in
   `note`.
6. Use `status` `verified` when the source states the number directly for this kind of item.
   Use `secondary` when it is a proxy (a similar item, a range midpoint, a derived figure), and
   explain the proxy in `note`.
7. Give two or more rows for one key when sources disagree (for example a low and a high value).
   Give each row its own `id`.

## Price conversion to 2015 EUR

- `value` and `unit` are what the source says, in its own currency and price year.
- `value_2015` and `unit_2015` are in **EUR at 2015 prices**:
  - Convert another currency to EUR at the ECB annual average exchange rate of the price year.
  - Then deflate with the **Eurostat HICP, euro area, annual average index (prc_hicp_aind,
    2015 = 100)**: `value_2015 = value_EUR × 100 / HICP(price_year)`.
  - Check against the existing catalogue's factors (value_2015 / value): 2012 1.0199,
    2013 1.0062, 2017 0.9825, 2019 0.9542, 2023 0.8120, 2025 0.7767. Use the same index, so
    your factors for these years must match.
- Write the arithmetic in `conversion`, for example `5.7 MEUR / (2 × 2300 m) = 1239.1 EUR/m;
  × 1.0062 (HICP 2013→2015)`.
- Shares, factors and years (discount rate, GWP, years of analysis) are not converted:
  `value_2015 = value` and `price_year` is empty.
- Keep full precision in `value_2015`. Do not round.

## CSV columns (same order as the attached file)

```
id,group,item,value,unit,price_year,value_2015,unit_2015,status,source,publisher,year,page,url,quote,conversion,path,in_case,note
```

- `id`: unique kebab-case, `<item>-<publisher>-<year>[-detail]`, for example
  `electric-boiler-dea-2025-10mw`. Do not reuse an id in the attached file.
- `group`: reuse a group from the file where one fits (`drilling and wells`, `pumps`,
  `heat pumps`, `chillers`, `heat exchangers and coolers`, `pipes and network`,
  `gas treatment`, `operating costs`). New groups: `boilers and chp`, `storage`,
  `energy prices`, `carbon and emissions`, `finance`.
- `path`: the case key that the value fills (list below).
- `in_case`: leave empty.
- `source`: full title. `publisher`: organisation. `year`: publication year.
- Quote every field that contains a comma.

## Keys to fill

### A. Keys with no row yet

| path | meaning | unit to give |
|---|---|---|
| assumptions.finance.analysis_period | economic lifetime used for geothermal heat projects | years |
| assumptions.finance.carbon.price | price of a tonne of CO2-equivalent (EU ETS, or NL CO2 levy) | EUR/t CO2e |
| assumptions.finance.energy.electricity | price of bought electricity for a large industrial or utility user, NL, excluding VAT | EUR/MWh |
| assumptions.finance.energy.gas | price of bought natural gas for a large user, NL, excluding VAT | EUR/MWh (GCV or NCV: say which) |
| assumptions.finance.revenue.subsidy.amount | SDE++ subsidy for deep geothermal heat, per year or per unit of heat | EUR/yr or EUR/MWh (say which) |
| assumptions.finance.revenue.subsidy.duration | how long SDE++ pays for geothermal | years |
| assumptions.finance.accounting.allocation.heat_cost_share | share of a combined heat and cold (or CHP) plant's cost put on heat, by a named method | 0-1 |
| assumptions.finance.accounting.gwp.standard | the name of the GWP set (for example IPCC AR6 GWP100) | text in `value`, empty unit |
| assumptions.finance.accounting.gwp.CH4 | GWP100 of methane in that set (fossil and non-fossil if both are given) | kg CO2e/kg CH4 |
| assumptions.finance.capex.boiler | gas boiler for district heating, installed | EUR/W heat |
| assumptions.finance.capex.electric_boiler | electric boiler for district heating, installed | EUR/W heat |
| assumptions.finance.capex.chp | gas engine CHP for district heating, installed | EUR/W electric (say the basis) |
| assumptions.finance.capex.circulation_pump | district heating circulation pump, installed | EUR/W shaft or EUR per unit with size |
| assumptions.finance.capex.thermal_storage | hot water tank storage for district heating | EUR/m3 (and EUR/MWh if given) |
| assumptions.finance.capex.ice_storage | ice storage for district cooling | EUR/m3 or EUR/MWh cold |
| assumptions.finance.opex.fixed.boiler, .electric_boiler, .chp, .circulation_pump, .thermal_storage, .ice_storage | yearly fixed O&M as a share of that item's capex | %/yr (or EUR/MW/yr, then also the share with its arithmetic) |
| assumptions.finance.opex.variable.chp | variable O&M of a gas engine CHP | EUR/MWh electric |

### B. Placeholder rows to replace (ids in the attached file)

Find a source for each and write a new row with a new id and the same `path`. If none exists,
say so in your report.

- `heat-pump-lift-range` (largest temperature lift of industrial heat pumps, K)
- `flare-capex` (`capex.flare`), `gas-makeup-capex` (`capex.gas_makeup`)
- `opex-fixed-drilling`, `-degasser`, `-absorption-chiller`, `-adsorption-chiller`,
  `-injection-pump`, `-heat-exchanger`, `-dry-cooler`, `-cooling-tower`, `-flare`, `-gas-makeup`
  (yearly O&M as a share of the item's capex, %/yr)
- `chemical-scale-inhibitor`, `chemical-corrosion-inhibitor` (EUR/kg). Write their `path` as
  `assumptions.finance.opex.variable.scale_inhibitor` and `...variable.corrosion_inhibitor`.
- `waste-disposal` (geothermal scale, sludge or NORM disposal, EUR/kg). Write its `path` as
  `assumptions.finance.opex.variable.waste_disposal`.

## Deliverables

Give three files to download:

1. `cost-sources-additions.csv`: only the new rows, with the exact header above. It must append
   to the attached file without changes.
2. `cost-sources-additions.json`: the same rows as a JSON list of objects with the same keys.
3. `cost-sources-report.md`, at most one page:
   - a table with one line per key: found or not found, the chosen value_2015 and unit, status,
     and the source;
   - the keys still without a source, and what you searched;
   - any source that disagrees with an existing row in the attached file.

Before you hand the files over, check them: the header matches the attached file, the ids are
unique and new, every non-placeholder row has url, page and quote, every `value_2015` follows
from `value` by the stated conversion, and the CSV parses with a standard CSV reader.

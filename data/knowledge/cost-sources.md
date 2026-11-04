# cost-sources.csv

A copy of gemini's cited cost catalogue, kept by geomind as a knowledge source of its memory.
It is reference data with its sources, not a code default: each row keeps its source columns
(title, publisher, year, price year, page, link) and its status (`verified`, `secondary` or
`placeholder`). Load it into a memory with `geomind memory seed data/knowledge/cost-sources.csv`.

- From: gemini, tag `v0.5.13` (commit `0177b1f46e9c821f84cd65a0228778f2c3fad18d`)
- Path: `docs/cost-sources/sources.csv`
- sha256: `d95516f2152fa866efb025114af74d53888861ba7a9fc315b26f9aa19b17dea0`
- Rows from gemini: 74 (33 verified, 25 secondary, 16 placeholder)

## Additions (2026-11-03)

59 rows appended after gemini's 74 (rows 75-133, 28 verified, 28 secondary, 3 placeholder), found by a
web research session and checked against the same rules: a source, page, quote and link on every
sourced row, EUR at 2015 prices by Eurostat HICP (euro area, 2015 = 100), the arithmetic in
`conversion`. They cover the economics keys gemini's catalogue had no row for (analysis period,
carbon price, electricity and gas prices, SDE++ subsidy, heat cost share, GWP set and CH4, capex and
fixed O&M of boiler, electric boiler, CHP, circulation pump, thermal and ice storage, CHP variable
O&M) and new sources for most of gemini's `placeholder` rows. A key can now have several rows; a
sourced row wins over a `placeholder` row of the same `path`.

- Four O&M rows (`opex-boiler-gas-dea-2018`, `opex-boiler-electric-dea-2017`,
  `opex-chp-gas-engine-dea-2018`, `opex-thermal-storage-tank-dea-2025`) give the source amount in
  `value` and the share of capex per year in `value_2015` (`%/yr`), as `opex.fixed` takes a share.
- Still without a source: `opex.fixed.circulation_pump`, `opex.fixed.ice_storage`,
  `opex.variable.corrosion_inhibitor`.
- Second-hand: the electricity and gas prices were read on CEIC, not on Eurostat (nrg_pc_205,
  nrg_pc_203); the DEA sheets were read in DEA's xlsx files mirrored by PyPSA technology-data.
- The waste disposal row (COVRA drum tariff) is an upper bound for NORM waste; bulk scale below the
  exemption limits costs far less.
- The NL CO2 levy is reduced by the ETS price; it is not added on top of it.
- Rows: 133 (61 verified, 53 secondary, 19 placeholder).

## Paths on gemini 0.6.2's keys (2026-11-04)

gemini 0.6.2 prices every chemical product, a scale or a corrosion inhibitor alike, under
`opex.variable.chemical`, the waste under `opex.variable.waste_disposal`, and a variable O&M per
energy produced under `opex.per_energy.<kind>` (gemini requests 17 and 18). Seven `path` cells
changed to those keys, nothing else:

- `chemical-scale-inhibitor`, `chemical-corrosion-inhibitor`: `opex.chemical` to `opex.variable.chemical`;
- `scale-inhibitor-proxy-watertap-2020`, `corrosion-inhibitor-placeholder`:
  `opex.variable.scale_inhibitor`, `opex.variable.corrosion_inhibitor` to `opex.variable.chemical`;
- `waste-disposal`, `waste-disposal-proxy-sewage-sludge`: `opex.waste_disposal` to
  `opex.variable.waste_disposal`;
- `opex-variable-chp-gas-engine-dea-2018`: `opex.variable.chp` to `opex.per_energy.chp` (EUR/MWh
  of electricity).

The units gemini 0.6.2 takes now: `capex.ice_storage` and `capex.thermal_storage` per MWh,
`capex.heat_exchanger` per W, `capex.production_pump` per unit, `opex.fixed.<kind>` per MW and
year for a kind sized by a power, `revenue.subsidy.amount` per MWh. Still refused (listed for
Sahand): `capex.pipe` in EUR/MW/m (`pipe-dea-2025-transmission-0-50mw`) and `opex.fixed.pipe` in
EUR/MW/yr or EUR/MW/km/yr (`opex-pipe-dea-2025-distribution`, `opex-pipe-dea-2025-transmission`);
`emissions.CO2.electricity` is the case's `utilities.electricity.co2_intensity`, no economics key.

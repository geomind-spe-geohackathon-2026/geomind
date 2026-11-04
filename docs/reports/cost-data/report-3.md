# Cost catalogue additions, batch 3: report

19 new rows (`cost-sources-additions-3.csv` / `.json`). The header matches the catalogue, all ids are unique and new against the current 151 data rows, and the rows append and parse cleanly (171 lines, 19 columns each). Conversions use the same HICP index as before; a 2026 price year uses the 2025 index.

## Keys

| Key | Found | value_2015 | Status | Source |
|---|---|---|---|---|
| opex.per_energy.boiler | yes | 1.1 EUR/MWh | verified | DEA sheet 44, row 31, 2020 column |
| opex.per_energy.electric_boiler | yes | 0.9 EUR/MWh | verified | DEA sheet 41, row 34, 2020 column |
| opex.per_energy.heat_pump | yes | 1.69 (waste heat, 10 MW); 1.19 (seawater, 20 MW) EUR/MWh | verified | DEA sheet 40, row 33, 2025 column |
| capex.production_pump | yes | 0.60 to 0.72 EUR/W electric (250 to 500 kWel) | secondary | Kennisagenda Aardwarmte ESP report 2016 |
| | | 1.55 EUR/W electric (332 kWel) | verified | Schlagermann and Reinicke 2023, Table 7 |
| discount_rate | **yes, 2025** | 5.1 % real / 7.2 % nominal, after tax | verified | PBL Eindadvies SDE++ 2025, Tabel 3.2 |
| | 2026 | 5.2 % real / 7.3 % nominal | secondary, unconfirmed | PBL 2026 erratum, Tabel 6.3 row 4 |
| opex.variable.waste_disposal | yes, derived | 3.87 EUR/kg (filter waste) | secondary | French TFA 1200 EUR/m3 ÷ NRG/EBN density 0.266 t/m3 |
| opex.variable.chemical, corrosion inhibitor | proxy | 1.94 to 3.11 EUR/kg | secondary | IndexBox 2026, EU amine inhibitors |
| opex.fixed.ice_storage | ice-specific | 0.51 (district cooling, 50 MWh) to 0.88 %/yr | secondary | sp.ICE manufacturer table 2024 |
| | proxy | 2 %/yr (whole cooling plant) | secondary | Hao, Kim and Braun 2022 |

## Notes and caveats

- **Danish Energy Agency workbook.** The copy read (PyPSA mirror) is an older edition than the version 0019 your catalogue cites. Its heat-pump capex is 0.67 MEUR/MW against 0.95 in `heat-pump-dea-2025-10mw`, so re-check the heat-pump variable O&M against v0019. The workbook's Index says all costs are 2015 EUR unless stated otherwise; the heat-pump sheet states no price year, so 2015 is assumed.
- **ESP.** Both sources give electric (motor) power, not shaft power. Shaft power is about 0.85 to 0.9 of it, so EUR per W shaft is roughly 10 to 15 % higher. The Dutch report gives the cost range and the power range without pairing them, which is why those rows are secondary. The German value is about twice the Dutch one per W; it comes from a cost correlation with no stated price year.
- **Discount rate (recommendation).** Replace the 2022 rows with the 2025 ones: the real 5.1 % with this catalogue's real prices, the nominal 7.2 % with nominal cash flows.
  - 2025 inputs: 70 % debt at 5.5 %, 30 % equity at 14.5 %, tax 25.8 %, inflation 2.0 %. Recomputed WACC 7.21 %.
  - 2026 round: the Eindadvies tables (ch. 6, pp.58 and 66) are beyond what the fetch tool can read. A PBL erratum changes "Tabel 6.3, 4e rij" from 8.4 / 6.2 % to 7.3 / 5.2 %, but does not say whether that row is geothermal. Read the PDF before using it.
- **2022 re-check.** Re-read against the PDF text through the fetch tool's extraction; the PDF itself could not be downloaded.
  - "Geothermie 5,6% / 4,0%" (Tabel 3-2, p.22) is confirmed verbatim.
  - The footnote reads "Er geldt dat reële WACC = [1 + nominale WACC] / [1 + inflatie] -1."
  - The 2.5 % debt rate and 15.0 % equity return are confirmed. A further -0.5 % green-finance discount brings the effective debt rate to 2.0 %, and only that reproduces 5.6 %.
  - The 70/30 split is listed under "Overige categorieën", not under geothermal by name.
  - Tax is 25.0 % and inflation 1.5 %.
  - Tabel 3-1 is titled "...voor de SDE++ 2021" inside the 2022 report.
- **Waste disposal.** The density applies to packed spent filters (big bags) only. Solid scale is far denser, so its per-kg cost would be much lower. The French figure is a nuclear-sector cost, not a Dutch NORM tariff. A per-kg disposal price for geothermal or oil-and-gas NORM in NL or the EU is still not published anywhere I searched: Mineralz, ANVS, COVRA inventory 2022, RIVM 2018-0138, BfS, ENA-NORM 2024.
- **Corrosion inhibitor.** A market-research page, not peer-reviewed. Formulated geothermal inhibitors are probably dearer (the same page gives specialty grades at more than 10 EUR/kg). No geothermal-specific price from 2015 or later was found.
- **Ice storage.** The ice-specific values come from a manufacturer's marketing table with no price year; the share is a ratio, so the year doesn't affect it. The table's 25-year lifecycle totals cross-check exactly.

## Disagreements with existing rows

- **ESP:** the 2016 Dutch per-unit cost (180 to 300 kEUR) is well below `esp-unit-2019` (800 kEUR). That row may include replacement and workover.
- **Discount rate:** the 2025 real WACC (5.1 %) is above the 2022 real WACC (4.0 %) and the EU 4 % financial rate.
- **Ice storage:** 0.5 to 0.9 %/yr is below the batch-2 PCM proxy (1.7 to 4.2 %/yr).

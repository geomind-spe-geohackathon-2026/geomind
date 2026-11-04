# Cost catalogue additions, batch 2: report

There are 18 new rows (`cost-sources-additions-2.csv` / `.json`). The header matches the catalogue. All ids are unique and new against the current 133 data rows. The rows append and parse cleanly (152 lines, 19 columns each).

Prices are in EUR at 2015 prices, deflated with the euro-area HICP (2015 = 100), the same index as batch 1. USD is converted at the ECB annual average (2023: 1.0813, 2024: 1.0824, from the Bank of Finland's ECB reference averages). Paths use the new `economics.` prefix.

## Keys

| Key | Found | value_2015 | Status | Source |
|---|---|---|---|---|
| opex.fixed.pipe | **yes** | 1.0 %/yr (transport and distribution) | verified | PBL Vesta MAIS model parameters |
| | | 0.5 to 1.0 %/yr | secondary | VDI 2067 via VICUS |
| | | 0.158 %/yr (range 0.07 to 0.39) | secondary, derived | DEA transport v8: 100 EUR/MW/km/yr ÷ 63,195 EUR/MW/km |
| opex.fixed.circulation_pump | proxy | 2.0 to 3.0 %/yr (pumps in general) | secondary | VDI 2067 via VICUS |
| opex.fixed.ice_storage | weak proxy | 1.67 to 4.17 %/yr (latent heat storage in general) | secondary | IRENA/ETSAP E17 (2013), Table 8 |
| opex.variable.chemical, corrosion inhibitor | weak | about 2.09 EUR/kg in 1989 money; no 2015 value | secondary | Ouzounian et al. 1989, Paris basin |
| opex.variable.chemical, scale inhibitor | proxy | 0.77 EUR/kg (raw ATMP); 2.15 and 2.68 EUR/kg (formulated antiscalant) | secondary | ChemAnalyst 2024 (Hamburg); Spitsov et al. 2023 (reverse osmosis) |
| opex.variable.waste_disposal | proxy, **not in EUR/kg** | 1027 EUR/m3 | secondary | French government, very-low-level radioactive waste (TFA) |
| discount_rate (optional) | yes | 4.0 % real / 5.6 % nominal WACC | verified | PBL SDE++ 2022 financing parameters |
| | | 8.7 % | secondary | EBN / Geothermie NL 2026 report on PBL's model |
| | | 2.25 % real | verified | Dutch social CBA rate (2020) |

## Still weak or open

- **Waste disposal in EUR/kg:** no geothermal-specific Dutch or EU price exists in any open source found. Sources that give quantities but no price: RIVM 2025 (about 40 t of geothermal filters landfilled at Maasvlakte in 2024), SodM/IAEA slides, the BVG NORM paper, and the EBN whitepaper, which leaves waste costs out. Converting the French per-m3 figure needs a density, which no source gives. The batch 1 COVRA drum tariff stays the only per-kg value.
- **Corrosion inhibitor:** the only per-kg figure comes from 1989. It is in French francs and has no 2015 value, because the euro-area HICP starts in 1996. Searched without a price: TNO 2015, Vogelaer TKI, PERFORM, Ungemach, EIKE and Otten (DGK 2024, PDF blocked).
- **Scale inhibitor:** no geothermal inhibitor product price was found. The two proxies differ by a factor of about 3: raw phosphonate against a formulated antiscalant.
- **Circulation pump and pipe (VDI 2067):** these come from a vendor's summary of the standard. Nobody has openly quoted the standard's pump row.
- **Ice storage:** no ice-specific O&M exists in any source opened. The proxy is pre-2015, mixes fixed and variable O&M, and is not ice-specific.

## Notes on discount_rate

- **Which rate for which use:** PBL's geothermal WACC fits a private financial appraisal under SDE++. Use the real 4.0 % with this catalogue's real prices. The 2.25 % rate is for social CBA only.
- **Inputs behind the PBL rate:** the 2022 parameters are 70 % debt at 2.5 % and 30 % equity at 15 %, with 25 % tax.
- **Not the latest round:** the SDE++ 2026 values are in Chapter 6 of the Eindadvies (p.57). Our tools can't read that far into the PDF, so 2022 is the latest round read. The EBN/GN report suggests PBL's later model uses 5.5 % debt and 14.5 % equity (8.7 % combined), so the 2026 rate is likely well above 5.6 %.
- **Quotes to check:** the PBL quotes came through a summarising fetch. Check them against the PDF.

## Disagreements with existing rows

- **Pipe O&M:** in the catalogue's DEA rows, the transmission O&M works out to only 0.16 %/yr of capex. That is about a sixth of the Dutch Vesta MAIS 1 %/yr. The tool's in_case default of 0.5 %/yr sits between the two.
- **Chemicals:** the in_case default for `opex.chemical` (3 EUR/kg) is at or above the formulated-antiscalant proxies (2.1 to 2.7 EUR/kg) and well above the raw phosphonate price (0.77 EUR/kg).
- **Discount rate:** the in_case default of 0.05 sits between PBL's real 4.0 % and nominal 5.6 %.

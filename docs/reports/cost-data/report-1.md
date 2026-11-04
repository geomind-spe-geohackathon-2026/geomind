# Cost catalogue additions: report

59 new rows (`cost-sources-additions.csv` / `.json`). The header matches the catalogue, all ids are new and unique, and the rows append and parse cleanly (134 rows, 19 columns). Every value is converted to EUR at 2015 prices with Eurostat HICP, euro area, 2015 = 100. The factors for 2017, 2019, 2023 and 2025 match the catalogue's. 2026 uses the 2025 index, as the catalogue already does. USD is converted at the ECB annual average rate (2017: 1.1297, 2020: 1.1422).

## Keys

| Key (path, short) | Found | value_2015 | Status | Source |
|---|---|---|---|---|
| analysis_period | yes | 25 yr; 15 yr | verified; secondary | DEA geothermal DH 2019; SDE++ period (Stcrt 2025) |
| carbon.price | yes | 57.5 (2025 ETS), 51.6 (2024 ETS), 61.1 (NL levy 2026) EUR/t | verified | ESMA 2026/2025; Rijksoverheid |
| energy.electricity | yes | 115.0 (ID), 138.0 (IE) EUR/MWh | secondary | Eurostat nrg_pc_205 via CEIC, 2024 S2 |
| energy.gas | yes | 37.5 (I4), 44.4 (I3) EUR/MWh GCV | secondary | Eurostat nrg_pc_203 via CEIC, 2024 S2 |
| revenue.subsidy.amount | yes | basisbedrag 48.7 (≥20 MW), 62.1 (<12 MW); net 27.5 EUR/MWh | verified; net secondary | PBL SDE++ 2026, Tabel 3.9/3.10 |
| revenue.subsidy.duration | yes | 15 yr | verified | Stcrt 2025, 23407, art. 54 |
| allocation.heat_cost_share | proxy | 0.87 (energy), 0.71 to 0.76 (PES) | secondary | Fiaschi et al. 2021 (geothermal CHP) |
| gwp.standard | yes | IPCC AR6 GWP100; EU reporting uses AR5 | verified | GHG Protocol 2024; EU 2020/1044 |
| gwp.CH4 | yes | 29.8 fossil, 27.0 non-fossil, 27.9 (SM) | secondary; SM verified | GHG Protocol 2024; IPCC AR6 7.SM.7 |
| capex.boiler | yes | 0.06 EUR/W | verified | DEA el & DH, sheet 44 |
| capex.electric_boiler | yes | 0.07 (>10 MW), 0.15 (1-5 MW) EUR/W | verified | DEA sheet 41 |
| capex.chp | yes | 0.95 EUR/W electric | verified | DEA sheet 06 |
| capex.circulation_pump | proxy | 0.09 to 0.24 EUR/W heat | secondary | DEA transport, pumping station |
| capex.thermal_storage | yes | 168.6 EUR/m3 tank; 64.9 EUR/m3 pit | verified | DEA storage sheets 141, 140 |
| capex.ice_storage | proxy | 23,250 to 31,704 EUR/MWh (ice bank); 10,062 to 50,310 (PCM) | secondary | CLIMA 2022 case; IRENA 2013 |
| opex.fixed boiler / e-boiler / chp | yes | 3.25 / 1.53 / 1.03 %/yr | verified | DEA 44, 41, 06 |
| opex.fixed.thermal_storage | yes | 0.28 %/yr | verified | DEA 141 note E |
| opex.fixed circulation_pump, ice_storage | **no** | – | placeholder | – |
| opex.variable.chp | yes | 5.4 EUR/MWh electric | verified | DEA 06 |
| heat-pump lift (no path) | yes | 130 K | verified | Arpagaus et al., Purdue 2018 |
| capex.flare | proxy | 57,700 EUR | secondary | US EPA flare cost manual (sizing assumed) |
| capex.gas_makeup | proxy | 636,893 EUR (1 MWe CHP on separated gas) | secondary, low confidence | nPro cost curve |
| opex.fixed.drilling | yes | 1 %/yr; 0.5 %/yr | verified | GEOPHIRES-X; Schlagermann 2023 |
| opex.fixed degasser / injection_pump / flare | proxy | 3 %/yr (all surface facilities) | secondary | Schlagermann 2023 |
| opex.fixed.gas_makeup | proxy | 8 %/yr (CHP, VDI 2067) | secondary | nPro |
| opex.fixed absorption / adsorption chiller | yes | 3 %/yr (HRE4: 4 %/yr) | verified (HRE4 secondary) | IEA SHC Task 65 D-C2 |
| opex.fixed.cooler | yes | dry 2, wet tower 4 %/yr | verified | IEA SHC Task 65 D-C2 |
| opex.fixed.heat_exchanger | proxy | 1.5 to 2.5 %/yr (DH transfer station) | secondary | VDI 2067 via VICUS |
| opex.variable.scale_inhibitor | weak proxy | 2.91 EUR/kg | secondary | WaterTAP (entry comment names hydrazine) |
| opex.variable.corrosion_inhibitor | **no** | – | placeholder | – |
| opex.variable.waste_disposal | proxy | 45.9 EUR/kg (upper bound) | secondary | COVRA 2026 drum tariff |

## Still without a source

- **opex.fixed.circulation_pump:** the DEA transport sheets give pumping-station fixed O&M as N/A, and no public quote of the VDI 2067 pump factors was found.
- **opex.fixed.ice_storage:** searched IRENA TES 2020, ETSAP E17, CLIMA 2022, MDPI and NREL/OSTI; none gives an ice-specific O&M figure.
- **corrosion_inhibitor:** searched Dutch and German terms, TNO 2015, EIKE 2024 (dosages only), IECM and oilfield sources. Fallback: Schlagermann 2023 puts inhibitors, disposal and other supplies at 1 % of the capex of the relevant items.

## Caveats and disagreements with existing rows

- **Waste disposal:** COVRA's radioactive-waste drum tariff (45.9 EUR/kg, 2015 EUR) is about 900 times the sewage-sludge proxy row (0.050) and far above in_case 0.2. Bulk NORM below the exemption limits goes to landfill and costs much less, so treat COVRA as an upper bound.
- **Heat-pump lift:** the open paper confirms the existing Arpagaus-slides row (130 to 40 K, conclusions 130 to 25 K), not the old 10-80 K claim.
- **Circulation pump proxy:** 0.09 EUR/W (DEA 2017, 2015 EUR) agrees with `injection-pump-proxy-dh-station` (0.099, DEA 2025).
- **Item O&M vs plant O&M:** item-level shares of 0.5 to 3 %/yr sit below the plant-level 5 % in `opex-plant-share-of-capex`.
- **in_case defaults that differ from sources:** chillers 2 vs 3 %/yr; wet cooling tower 2 vs 4; heat exchanger 1 vs 1.5 to 2.5; degasser and injection pump 2 vs 3; flare capex 100,000 vs about 57,700 EUR.
- **Second-hand data:**
  - Eurostat could not be reached. The electricity and gas prices were read from CEIC, which mislabels the electricity unit as EUR/MWh, and the IE band comes out dearer than ID. Check both against nrg_pc_205 and nrg_pc_203.
  - The DEA data sheets were read in DEA's own xlsx files mirrored on GitHub (PyPSA technology-data), because ens.dk blocked downloads. DEA's 2026 storage catalogue v0011 rewrote the tank chapter and was not read.
- **NL CO2 levy:** the levy is reduced by the ETS price, so do not add it on top of the ETS price.

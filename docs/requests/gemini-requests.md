# geomind -> gemini requests (for Sahand), 2026-11-04 00:30 UTC

Sent by Sahand already: 13, 14, 15 (and earlier 1-12 were listed before). The 16-21 list posted in GEOMIND II at ~23:55 UTC overlaps the items below.

## If you already sent 16-21: send only these new ones

```
geomind requests (new, found in agent tests on gemini 0.6.1):
23. gemini's own cost catalogue (docs/cost-sources/sources.csv) names paths that are not keys of gm.case.Economics: the prefix assumptions.finance.*; emissions.CO2.electricity (the case's utilities.electricity.co2_intensity); opex.chemical; opex.waste_disposal (the schema's opex.variable.waste_disposal). Asked: catalogue paths that match the schema.
24. capex.pipe: accept a cost per capacity and length (EUR/MW/m), as DEA gives it (the key takes EUR/m).
25. Case schema descriptions are missing for: about, initial_state, economics.about, demand.heating.minimum_return_temperature, demand.heating.maximum_return_temperature, demand.cooling.minimum_return_temperature, demand.cooling.maximum_return_temperature. Asked: describe them in Case.schema().
```

## If you have not sent 16-21 yet: send this one block instead

```
geomind requests (economics and schema, found in agent tests on gemini 0.6.1):
16. Economics units that cited cost data needs but the keys don't accept: revenue.subsidy.amount per MWh of delivered heat (SDE++; key takes EUR/yr); opex.fixed.* as an amount per W per year (DEA EUR/MW/yr; key takes %/yr); capex.heat_exchanger per W of duty (key takes EUR/(W/K)); capex.ice_storage and capex.thermal_storage per stored energy (key takes EUR/m3); capex.pipe per MW and metre (key takes EUR/m); capex.production_pump per unit (key takes EUR/W).
17. gemini's own cost catalogue (docs/cost-sources/sources.csv) names paths that are not keys of gm.case.Economics: the prefix assumptions.finance.*; emissions.CO2.electricity (the case's utilities.electricity.co2_intensity); opex.chemical; opex.waste_disposal (the schema's opex.variable.waste_disposal). Asked: catalogue paths that match the schema.
18. Variable O&M per energy produced (EUR/MWh, e.g. CHP electricity, boilers), and opex.variable consumable keys for scale_inhibitor and corrosion_inhibitor (EUR/kg); list the allowed consumable names in the schema.
19. Descriptions (meaning, accepted units) for every field of the Economics schema and of the Case schema, including about, initial_state, economics.about and demand.heating/cooling.minimum/maximum_return_temperature, which have none today.
```

Older open items 1-12 are in geomind's plan.md; priority suggested by geomind: 13, 14, 15, 16, 6 (evaluate speed).

## New (2026-11-05, QA-287 follow-up, for Sahand)

```
geomind request (private names, found by test_geomind_uses_no_private_gemini_name):
- A public name for a doublet's design groups. geomind needs the design values of a doublet
  (gemini.plants._utils.doublet_design COLUMN, FLOW_PATH, PUMP) and the ESP values its design
  derives (PUMP_VALUES esp.*), to name all missing values at once and to leave derived ones out
  of `missing`. Today geomind keeps a copy in tools/gemini/stages.py and a test compares it with
  gemini's private module. Asked: e.g. gm.plants.Doublet.design_groups() or the lists in
  Doublet.describe().
```

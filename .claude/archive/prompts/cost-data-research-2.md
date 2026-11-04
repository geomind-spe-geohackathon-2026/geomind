# Prompt: cited values for the last open cost keys (follow-up)

Paste everything below the line into the same Claude session that made `cost-sources-additions.csv`
earlier. If it's a new session, attach `cost-sources.csv` (geomind `data/knowledge/cost-sources.csv`,
134 rows) and the first prompt, `cost-data-research.md`.

---

Thanks for the first batch: it's in the catalogue now. A few keys are still open. Please find
**real, cited values** for them, with **the same hard rules, price conversion (EUR at 2015 prices,
euro-area HICP prc_hicp_aind, 2015 = 100), CSV columns and deliverables as last time**:

- never invent or estimate a value;
- every row needs `url`, `page` and an exact `quote`;
- a key you can't source still gets a `placeholder` row with a `note` saying what you searched;
- the order of preference is NL, NW Europe, EU, then international, and official or peer-reviewed sources first;
- use new ids only.

## Keys to fill

| path | meaning | unit to give | why it's open |
|---|---|---|---|
| economics.opex.fixed.circulation_pump | yearly fixed O&M of a district heating circulation pump | %/yr of its capex | only a placeholder row |
| economics.opex.fixed.ice_storage | yearly fixed O&M of an ice storage for district cooling | %/yr of its capex | only a placeholder row |
| economics.opex.fixed.pipe | yearly fixed O&M of district heating pipes | **%/yr of the pipe capex** (the design tool can't take EUR/MW/yr); if a source gives EUR/MW/yr or EUR/m/yr together with a capex, give the share and its arithmetic | the DEA rows are EUR/MW/yr, which the tool refuses |
| economics.opex.variable.chemical (corrosion inhibitor) | price of a corrosion inhibitor used in geothermal brine | EUR/kg | only a placeholder row |
| economics.opex.variable.chemical (scale inhibitor) | price of a scale inhibitor (phosphonate, polyphosphate) for geothermal brine | EUR/kg | only a US proxy (`secondary`); a European or geothermal-specific source is wanted |
| economics.opex.variable.waste_disposal | cost of disposing geothermal scale, sludge or NORM waste below exemption limits (bulk, e.g. landfill), not a radioactive-waste drum tariff | EUR/kg | only proxies (sewage sludge, COVRA drum); a geothermal-specific NL/EU source is wanted |
| economics.opex.per_energy.boiler, .electric_boiler, .heat_pump | variable O&M per MWh of heat (e.g. DEA technology data: gas boiler, electric boiler, large heat pump; give the sheet and column) | EUR/MWh heat | no row yet |
| economics.capex.production_pump | electric submersible pump (ESP) for a geothermal well, with the power it was quoted for | EUR/W of shaft or hydraulic power | no usable row |

## discount_rate: a choice, not a gap

The catalogue already has two verified rows: 4% real (financial, EU Reg. 480/2014 Art. 19(3))
and 3% (social, EU Better Regulation Tool #64). Also look for the Dutch rate for a deep geothermal heat project: PBL's SDE++
financial assumptions (WACC, return on equity, interest, debt/equity share, inflation) in the
geothermal chapter or the general financial section of Eindadvies basisbedragen SDE++ 2025/2026,
or the Dutch discount rate for social cost-benefit analysis (Werkgroep discontovoet). Give the
REAL rate per year (0-1). If the source gives a nominal WACC and inflation, put both in `note` and
give the real rate only if the source states it. A rate has value_2015 = value and unit_2015 = unit.

## Deliverables

The same three files, with new names:

- `cost-sources-additions-2.csv`
- `cost-sources-additions-2.json`
- `cost-sources-report-2.md`

Check them as before:

- the header matches;
- the ids are unique and new;
- every row except a placeholder has url, page and quote;
- every value_2015 follows from its stated arithmetic;
- the CSV parses.

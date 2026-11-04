# Prompt: cited site, utility and remaining cost data

Paste everything in the code block into a new Claude session that has web search. Fill the SITE line first (the brief names no site).

```
You collect cited reference data for a geothermal heating-and-cooling design case (a doublet, a 2027 daily demand, Dutch/EU context). Every value must come from a real, checkable public source. Never estimate, never use a "typical" value, never compute a value except the price-year conversion described below. If you cannot find a source for an item, write a row with status "placeholder", leave value empty, and say in note what you searched.

SITE: <fill in: country/city, or "Netherlands, generic">

Deliver two files:

1) site-sources.csv with these columns:
id,item,path,value,unit,status,source,publisher,year,page,url,quote,note
- status: verified (official or peer-reviewed primary source), secondary (a report quoting one), or placeholder (none found).
- quote: the exact sentence or table cell the value comes from.
- path: the case key, exactly as written below.
Items:
- site.air.temperature: yearly mean outside air temperature at SITE, in degC. If a daily 2027-like series exists (e.g. KNMI daily means), give its download URL in note.
- site.air.relative_humidity: yearly mean outside relative humidity at SITE, as a 0-1 fraction or %.
- site.air.pressure: mean station or sea-level air pressure at SITE, in hPa or kPa.
- utilities.gas.composition: mole fractions of the national grid natural gas (CH4, C2H6, C3H8, CO2, N2, O2). One row per species, path utilities.gas.composition.<species>.
- utilities.gas.heating_value: gross calorific value of that grid gas, in MJ/kg or MJ/m3(n). Say in note which.
- utilities.electricity.co2_intensity: grid CO2 intensity for the latest year, in g/kWh.
- demand.cooling.indoor_temperature and demand.cooling.indoor_relative_humidity: design indoor conditions for comfort cooling (e.g. EN 16798-1 category II).
- demand.cooling.dew_point_margin: the margin chilled-water supply keeps above the room dew point, in K, from a design guide.
- demand.heating.return_pressure and demand.cooling.return_pressure: typical design return pressures of a district heating network and a chilled-water network, in bar(g), from a design guide.
- site.fluid.sand_concentration: produced-sand or solids content of Dutch geothermal brine, in mg/l, from field reports.
- site.fluid.dissolved_gas.N2 and site.fluid.dissolved_gas.H2S: mole fractions in the produced gas of Dutch geothermal wells.

2) cost-additions.csv with exactly these columns, the same as our catalogue:
id,group,item,value,unit,price_year,value_2015,unit_2015,status,source,publisher,year,page,url,quote,conversion,path,in_case,note
- value and unit: as the source gives them. price_year: the year the source's prices are in.
- value_2015: the value in EUR of 2015, converted with the euro-area HICP (Eurostat prc_hicp_aind, all items). In conversion, write the formula and both index values. Don't convert units: if the source unit is not the unit asked below, keep it and say so in note.
- path: exactly as below. in_case: leave empty.
Items, each with the unit the case needs:
- assumptions.finance.capex.ice_storage, in EUR/m3 of storage volume
- assumptions.finance.capex.heat_exchanger, in EUR/(W/K), i.e. cost per UA value
- assumptions.finance.capex.production_pump, in EUR/W of hydraulic or shaft power (an ESP for geothermal)
- assumptions.finance.capex.injection_pump, in EUR/W
- assumptions.finance.opex.fixed.heat_pump and assumptions.finance.opex.fixed.pipe, in %/yr of capex
- assumptions.finance.revenue.subsidy.amount, in EUR/yr, or the SDE++ base amount per MWh with its basis in note
- assumptions.finance.opex.variable.scale_inhibitor and assumptions.finance.opex.variable.corrosion_inhibitor, in EUR/kg
- assumptions.finance.analysis_period, in yr
- assumptions.finance.energy.electricity and assumptions.finance.energy.gas: Dutch non-household prices, in EUR/MWh (gas on GCV)
- assumptions.finance.carbon.price: EU ETS price, in EUR/t CO2
For each item give up to 3 rows from different sources when they exist.

Rules:
- One row per value.
- Copy numbers digit for digit from the source.
- Include the page, table or URL anchor.
- Prefer official statistics (CBS, KNMI, Eurostat, TNO, Danish Energy Agency, IEA) and peer-reviewed papers.
- Give me both CSV files, UTF-8, comma separated, values with a comma inside quoted.
```

# What geomind would like from gemini (for Sahand to review)

Nothing here has been sent to gemini. Sahand decides which items, if any, go to the gemini thread.
Collected 2026-11-03 from geomind 0.4.2 work (gemini 0.5.5 wheel). All are additive; none needs an API change.

| # | Need | Why geomind wants it | geomind today |
|---|------|----------------------|---------------|
| 1 | `units="display"` on `Results.get` / `Results.summary` (incl. pressure, mass flow) | agents and the app show readable units | geomind keeps its own unit map |
| 2 | `Comparison.to_dict(units="display")` | compare results go straight to the model and the report | reads display values from reports |
| 3 | complete `capabilities()["ranges"]` (every parameter at the plant's real size) | tools can name the exact missing range and its unit | partial list |
| 4 | capex and opex parts in display units | economist explains costs per part | only totals are readable |
| 5 | a `job` argument on the existing public `gm.case.missing(case)` (what a given job needs) | ask the user for all gaps of one job in one question | uses `gm.case.missing(case)` |
| 6 | faster `gm.evaluate` (it copies the plant per metric) | studies and verification are slow | — |
| 7 | a size-only study method | "size first" without a search | uses the full study call |
| 8 | public `to_dict` for minimize results, with history | store and show optimisation progress | private fields |
| 9 | `Plant.to_dict` including sizing quantities | store the sized plant exactly | partial |
| 10 | time units `day` and `hour` accepted (today only `d`, `h`) | models write `day`; error now lists valid units | error message shows accepted units |

Dropped by Sahand: "ship examples in the wheel" (geomind keeps its own test fixtures).

## Filtered 2026-11-03 08:35 UTC by Sahand's rule (only completely new features or bugs; no change to any existing structure or API)
SENT to gemini (GEMINI 1 thread):
- #7 a NEW size-only study function (size first, no search). New public name only; nothing existing changes.
- #8 a NEW public way to read minimize results with their history (e.g. a new to_dict on the result). Today geomind would have to read private fields.
NOT sent (each changes an existing function, its arguments or its output; geomind handles them itself):
- #1, #2, #4 display units (new argument / changed output): geomind keeps its own unit map.
- #5 job argument: NOT sent as an argument. Re-scoped and SENT as a NEW function: list every case value a plant's costs need before evaluating (same Issue shape as gm.case.missing); low priority.
- #9 Plant.to_dict with sizing (changes existing output): geomind stores sizing separately.
- #10 day/hour time units (changes existing parsing): geomind maps them to d/h.
- #6 faster gm.evaluate: already in GEMINI 1's speed-up work; no API change asked.
- #3 capabilities ranges: SENT as a BUG (evidence: ranges miss leaves that the example plant files give ranges for); same shape.
- #6 gm.evaluate per-metric plant copies: mentioned to fold into the existing speed-up, same API.

## 2026-11-03 08:45 UTC checks (Dell)
- Unit audit: geomind converted itself only in 2 places (case time step, setting durations); both now via gm.units; test forbids conversion factors in geomind. Gap: gemini has no "ms" unit (xfail test names it).
- Plant round trip: sizing kept (2 examples, 337 and 184 values, 0 differences). Item 9 dropped.
- Final copy-paste list given to Sahand in GEOMIND 1 (items 1-5 already sent 08:35, new 6 = "ms" unit). Sahand hands it to gemini himself.
- 08:50 UTC: item 6 ("ms") DROPPED: geomind accepts only s/min/h/d for setting durations; no gemini request.

## FINAL 2026-11-03 08:55 UTC (re-checked on gemini 0.5.5)
Only two items remain; GEMINI 1 told to drop the rest:
1. BUG capabilities()[cls]["ranges"] misses params.d1.nominal_flow for all two-doublet hackathon_2026 plants (d0 listed).
2. NEW function (low priority): list case values a plant's costs need before evaluating (Issue shape like gm.case.missing).
WITHDRAWN: size-only study (prepare size exists), minimize to_dict (Value.to_dict exists), evaluate speed (0.12 s/report), ms unit, display units, day/hour, Plant.to_dict sizing.

## 2026-11-03 11:40 UTC (live test 3) PROPOSED, waiting for Sahand
- NEW optional series key time_zone so date-only/naive CSV times are read in that zone; absent = unchanged (rejected).
  -> SENT by Sahand's OK 11:38, released in gemini 0.5.13.

## 2026-11-03 ~15:00 UTC (Designer test D1) PROPOSED, waiting for Sahand
- BUG: gm.Plant.from_dict raises KeyError('') instead of a ValidationError when a plant file's inlets give a bare value, e.g. {"flue_out": "gas"} (gemini/plants/_utils/ports.py, _check_reach). Not blocking.

## 2026-11-03 ~18:00 UTC (GEOMIND II per-agent tests) PROPOSED, waiting for Sahand
- BUG: on a class plant, gemini's plant check still lists inner doublet values (e.g. d0.reservoir.permeability, d0.reservoir.thickness) as missing after the doublet's top-level values are set, while the complete HackathonPlant needs none of them. Engineers then copy case values into the plant by hand. Not blocking. (geomind plan item 11, c1aa8ea)

## 2026-11-03 ~21:10 UTC FULL LIST re-checked on gemini 0.6.1 (GEOMIND II), waiting for Sahand
Priority (they cause agent mistakes): 11 inner doublet values listed missing on class plants; 13 Plant.from_dict KeyError('') on a bare inlet value; 12 Case.schema() does not say time.end is exclusive. Speed: 6 gm.evaluate copies the plant once per metric (~10x per report).
Other open items: 2 Comparison.to_dict(units="display"); 3 capabilities()["ranges"] incomplete, and set_range accepts any leaf; 4 value parts in display money units; 5 job= on gm.case.missing; 7 size-only study method; 9 Plant.to_dict carrying sizing; 10 time units "day"/"hour".
Dropped (already in gemini): 1 units= on Results.get/summary; 8 minimize result to_dict.

## 2026-11-03 23:55 UTC: economics basis mismatches found with the cited cost catalogue (requests 16-21, for Sahand)

16. revenue.subsidy.amount: accept a per-energy subsidy (EUR/MWh of delivered heat, optionally with a cap in full-load hours or MWh per year), as SDE++ pays; today only EUR/yr.
17. opex.fixed.<kind>: accept an absolute yearly cost per capacity (EUR/(W*yr), e.g. DEA's EUR/MW/yr) besides the share of capex (%/yr).
18. Cost basis per kind: capex.heat_exchanger per W of duty (DEA gives EUR/W) besides per W/K; capex.ice_storage / thermal_storage per stored energy (EUR/MWh) besides per m3; capex.production_pump per unit (EUR) besides per W.
19. Variable O&M per energy produced (EUR/MWh, e.g. CHP electricity, boilers): no economics key takes it today.
20. opex.variable consumables: list the allowed consumable names in the schema/describe (scale inhibitor, corrosion inhibitor, waste disposal ...), so a catalogue can match them.
21. Economics schema: a description per field (meaning, accepted units), like the case fields.
22. Case schema: a description per field (meaning, accepted units), incl. about, initial_state, demand.*.minimum/maximum_return_temperature, which have none today.

# geomind calls that no longer exist in gemini `dev` (b8d0282)

Checked 2026-11-01 15:20: geomind `main` 2964c69 (crust-team/geomind, last push 2026-10-31 19:40) against gemini `dev` b8d0282, by importing gemini and listing every `gm.*` name geomind uses.

| geomind uses (old) | gemini `dev` (new) |
| --- | --- |
| `gm.profiles.get`, `gm.profiles.names` | gone; demand comes from the case: `gm.Case.from_json(...)` (`demand.file`, `time_column`, services), or `gm.data.from_csv` |
| `gm.kpi.totals`, `gm.kpi.compute` | `gm.evaluate.totals`, `gm.evaluate.report(plant, case, results)` |
| `gm.checks.Limits`, `gm.checks.limits`, `Limits.to_dict/from_dict` | constraints live in the case: `gm.case.Constraint` (role, quantity, min/max/equals, over, when); checked by `gm.evaluate.constraints(plant, case, results)` |
| `gm.checks.run_all`, `gm.checks.plant_balance` | `gm.evaluate.run_all`, `gm.evaluate.plant_balance` |
| `gm.economics.Assumptions` (+ `model_fields`) | `gm.case.Assumptions` inside the case (`assumptions.finance`, `assumptions.emissions`), no defaults |
| `gm.economics.lcoh`, `gm.economics.lcoc` | `gm.evaluate.lcoh`, `gm.evaluate.lcoc`, `gm.evaluate.lcts` |
| `gm.plants.from_dict` | `gm.Plant.from_dict` / `gm.Plant.from_json` (and `to_dict` / `to_json`) |
| `gm.plants.from_template` | gone; plant classes (`gm.plants.HeatingCoolingPlant`, ...) or stored plant JSON |
| `gm.plants.spec_schema` | `gm.plants.schema()` |
| `gm.plants.example` | removed; `gm.Plant.from_json(...)`, or a plant class plus `plant.missing_parameters()` (path, quantity, units, bounds, description) |
| `gm.units.parse` | gone; `gm.units.Quantity(value, unit)` with `gm.units.Unit`; unit strings like `"2500 m"` are rejected |
| `gm.schedule(...)`, `gm.simulate(...)` | `gm.schedule(plant, case)`, `gm.simulate(plant, case, ...)` |
| (new) | `gm.study.size`, `minimize`, `sample`, `sensitivity`; `gm.evaluate.compare`; `gm.plants.capabilities()` |

Still the same: `gm.modules.get/names`, `gm.plants.validate/names/get`, `gm.errors.*`, `gm.units.convert/fits`, `gm.Results.from_bytes`, `gm.__version__`.

Changed by the study work (gemini `dev` 3cec98b, 2026-11-01 18:17):

| old | new |
| --- | --- |
| `gm.study.size(plant, case)` | `gm.study.size(plant, case, backup="peak" or "none")`; notes (broken constraints, unsized units, simulation status) in `plant.sizing` |
| `gm.study.sample(plant, case, distributions, metrics, count, seed=0)` | `gm.study.sample(plant, case, metrics, count, seed)`; distributions declared in `case.json` as `"uncertainty": {"kind": uniform/triangular/normal, ...}`; summary has a `failed` count |
| `gm.study.sensitivity(plant, case, parameters, metrics)` | `gm.study.sensitivity(plant, case, metrics)` (bounds from the case's uncertainty); table gains `value_unit` |
| `gm.data.synthesize`, `gm.analysis.injectivity`, `calibrate_pump`, `calibrate_corrosion`, `erosion` | removed (planned, listed in gemini's refactor-notes.md) |
| well `pipe_path` in a plant dict | `section_length`, `section_inclination`, `section_diameter`, `section_roughness` |
| `PipePath.subpath` | `geometry.path_between` |
| `report.to_dict()` in SI | display units by default (LCTS EUR/MWh, CO2 kt, ...), or `to_dict(units={metric: unit})` |
| `Comparison` values as floats | `Quantity` |
| `Best.to_dict()` without the plant | includes the plant dict |
| (new) | `gm.evaluate.failures(results)` (failed rows by module and code; also inside `report`); a trial with failed steps is infeasible with metrics `None` and a reason |
| (new) | every study, compare and report result has `to_dict()` that passes `json.dumps` |
| (new) | `gm.runtime.settings(processes=...)` runs independent trials in parallel |
| `Plant.validate()` | removed; `gm.plants.validate(plant.to_dict(structure=True))` (dev cca153b) |
| `Plant.from_legacy`, `gm.data` legacy readers | removed from the package (old-format helpers live in gemini's `scripts/legacy/`, not importable as `gm`) |

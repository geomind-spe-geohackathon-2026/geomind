# Changelog

`gd.__version__` follows semver below 1.0, the same rule as gemini: a breaking change to a frozen
interface raises the minor version, and an addition or a fix raises the patch version. The rule and
the list of frozen interfaces are in [.claude/docs/api.md](../.claude/docs/api.md#frozen-interfaces).

## [Unreleased]

## [0.4.107] - 2026-11-05

### Fixed
- QA-168: the analysis lead has `ask_economics`, and its prompt says to ask a missing economics
  with it, never with `ask_user` and values it writes itself.
- QA-186: a `set_case` economics patch drops the `about.sources` entry of every key it changes or
  removes without giving that key a source, so a value the user changed never keeps the
  Knowledge row of the value it replaced.

## [0.4.106] - 2026-11-05

### Fixed
- QA-166: `simulate` takes `plant_version` (a saved plant version of the project); without a
  design or a version it runs the latest version and its summary's `plant` says so ("plant
  version 2 (the project's latest)"), so a run of v2 is never reported as v1.

## [0.4.105] - 2026-11-05

### Fixed
- QA-172, QA-174, QA-183: the approval card of a `patch_plant` that sends its changes as a list
  `[{path, value}]` counts and names each path, instead of "Change 0 value(s)".

## [0.4.104] - 2026-11-05

### Fixed
- QA-169, QA-182: `read_knowledge` reads a bare name (`handbook-design.md`) as
  `knowledge/handbook-design.md` instead of refusing it as a project file; a section key of a
  number and a title that names no heading as a whole (`3 Wells`, `5.5 Gas use and disposal`)
  takes the heading whose title holds that title, else the one of that number; the outline of
  a refused section lists each number once (`3 The subsurface`, not `3 3 The subsurface`).

## [0.4.103] - 2026-11-05

### Fixed
- QA-181: an answered question whose `on_answer` may write (`ask_economics` approve all sets the
  economics) counts as a write for the repeat guard, so a later `read_case` or `case_changes`
  runs again instead of returning the stale result and stopping the run.

## [0.4.102] - 2026-11-05

### Fixed
- QA-165: a result tool sent a result of the project's Study page (listed by `list_studies`
  under `project_study`) says so and what to do: quote its `kpis` and `checks`, or simulate
  `design/v<plant_version>` for its series; the skill `comparing-designs` says the same.

## [0.4.101] - 2026-11-05

### Fixed
- QA-162: the explainer, the reviewer and the skills `reading-results` and `report` read the
  plant's feasibility from `check_results` `feasible` alone, never from a requirement's
  `passed` (a plant without cooling passed every requirement and was called passing).

## [0.4.100] - 2026-11-05

### Fixed
- QA-153: the case lead asks its ONE confirmation question (Knowledge values, server values,
  its own choices, the series' `time_zone`) before the first `set_case`, and saves them only
  after `approve all`, in one `set_case`; `source="project"` only for a project `case.json`.

### Changed
- QA-150: `web_search` takes up to 12 words.
- The design lead's briefs point to handbook-design 0.7 (design values) and 0.8 (hackathon
  limits).

## [0.4.99] - 2026-11-05

### Fixed
- QA-152: a plant of the project (Plant page, earlier chat) is `design/<its name>` or
  `design/v<version>` in every design tool, so the study tools (`sensitivity`,
  `sample_uncertainty`, `run_study`) run on it; an unknown design reference says so.
- QA-158: the case lead prompt no longer says dates without an offset are read as UTC: gemini
  refuses them without a series `time_zone`, which the lead proposes as an assumption.

## [0.4.98] - 2026-11-05

### Fixed
- QA-147: `read_stored`, `calculate` and `run_python` read a path through a dotted module key
  such as `d0.esp.fluid_in.volume_flow`: at each level the longest run of parts that is a key
  is one key (`stored.path_keys`); before, the path was split at every dot and `d0.esp` could
  never be reached.

## [0.4.97] - 2026-11-05

### Added
- QA-122: the agents see every plant version and study of the project, read-only, through the
  optional `Workspace.project_designs` and `Workspace.plant_version`: `list_plants` gives
  `project_versions`, `list_studies` lists the project's studies first (`project_study` with
  the results' KPIs and checks), and `read_plant(plant_version=N)` reads a saved version.

## [0.4.96] - 2026-11-05

### Changed
- QA-145: the design engineers propose changes from their brief (no plant, case or profile
  tool) and return a `Proposal` (changes with sources, evaluations, case changes, couplings);
  the design lead builds once, splits the missing values among up to four engineers in one
  `fill_parts` and applies all changes in one `patch_plant`; the lead prompt follows the gated
  design path of handbook-design ch 0 and reads the handbook with `read_knowledge`.
- `patch_plant` takes a change list `[{path, value, source}]`; a patch that changes nothing is
  refused `no_change` and stores no version.

## [0.4.95] - 2026-11-05

### Added
- IMP-019: `simulate` and the study tools fill a plant-level choice that is unset and that
  gemini allows exactly one value of (`params.control.dispatch` = least_cost,
  `params.control.outages` = lowest_demand); `simulate`'s summary lists each in `filled`.

## [0.4.94] - 2026-11-05

### Fixed
- QA-121: an approval of build_plant, patch_plant, set_ranges or set_case starts with one
  sentence of what the call does (plant, changed paths, ranges, removed ranges); the JSON
  below is cut at 1500 characters. designing-a-plant: a size question is one ranged search.

## [0.4.93] - 2026-11-05

### Fixed
- QA-143: `evaluate_module` with `design=` and a class name the design holds once uses that
  module's values; its inlet refusal says a design gives no stream state and shows both ways
  (inlets with `design`, or `result`); a call identical to one that failed, with no success
  since, is not run again (`failed_before`).

## [0.4.92] - 2026-11-05

### Fixed
- QA-140: the case lead always splits the case among 2 to 4 geoscientists in one `geoscientists`
  call (time and demand, ground and reservoir, brine and utilities, requirements); the single
  `geoscientist` tool is gone and a gap can be split again.

### Added
- `search_knowledge` and `read_knowledge`: the global Knowledge base only, for sub-agents
  (the geoscientist has them); a name outside `knowledge/` is refused.

## [0.4.91] - 2026-11-05

### Changed
- IMP-025 (user rule): only a team lead reads and writes the project's files; the geoscientist
  has no file tools and works from the report text the case lead puts in its brief; a team call
  takes at most 4 briefs; the lead merges, writes once and re-splits what is left.

## [0.4.90] - 2026-11-05

### Added
- IMP-025: a `Team` takes `briefs` as a list of `{role, task}` and runs one instance per entry at
  the same time, named `<Role> <Roman numeral>` (Geoscientist I, II, ...); every event of an
  instance's run carries the new optional field `instance`. The case lead's `geoscientists`
  team splits the subsurface work by field group in one call; skill working-in-a-team,
  "Parallel instances".

### Changed
- The cost catalogue is `knowledge/data-economics.csv` and `.md` (was cost-sources.*).

## [0.4.89] - 2026-11-05

### Changed
- designing-a-plant names the handbook by its new Knowledge name, `handbook-design.md`.

## [0.4.88] - 2026-11-05

### Fixed
- QA-131: `sensitivity` takes `values`, the case paths to move (only those); the economics skill
  and the analysis lead give the path for a chat sensitivity: the user's ranges into the case as
  `uncertainty` with `set_case`, then `sensitivity`, never `run_python`.

## [0.4.87] - 2026-11-05

### Fixed
- QA-129: designing-a-plant: a free plant with one doublet `d0` searches `size.doublets` (gemini
  0.6.15); an approved range is never dropped in silence; handbook-plant-design chapters 10, 11.
- QA-132: reading-results: the flow range is judged on `<doublet>.reservoir.liquid_flow`; the
  pump's intake volume flow counts free gas.

## [0.4.86] - 2026-11-05

### Fixed
- QA-125: `read_result` of a series carries `summary` (max and min with their time, mean,
  active steps and days, first and last active step); `read_result` of a module path carries
  `operation` (steps, operating steps and days, gemini's energy per output in MWh). The
  reading-results skill maps each result question to one call; run_python only beyond them.
- QA-124: reading-results points to `check_results` `requirements` for every requirement's
  value, limit, module and day.
- QA-123: with gemini 0.6.14, a module rated by conductance is no longer reported as unused; the
  skill says a module without an energy output was not idle.

## [0.4.85] - 2026-11-05

### Fixed

- QA-119: `set_case` returns `check` when `site.reservoir.reference_depth` moves while its pressure or temperature stay; the case lead treats a depth asked for the wells as the plant's `params.depth`.
- QA-120: `ask_economics` refuses a fraction key (`discount_rate`, a share) given a whole number with no unit, naming the fraction (8 -> 0.08).

## [0.4.84] - 2026-11-05

### Added

- `read_rag(name, outline=true)` gives a document's heading tree (`level`, `number`, `title`, `start`, `size`); `read_rag(name, section="3.2")` (or a title) gives that section with its subsections, paged inside it. `search_rag`'s knowledge hits carry `section`, their heading path. Usage in the skill `finding-sources`.

## [0.4.83] - 2026-11-05

### Fixed

- IMP-016: the design loop stops when one requirement failed in each of the last three rounds; the answer names it for the user to accept, change or stop.
- IMP-017: a design that passes every requirement and states search ranges goes once to the design lead to optimise, simulate and check the best.
- QA-097: `read_stored` says a key shown beside a reference is in the answer itself; a stored answer keeps its own note as `answer_note`.
- QA-099: `compute_kpis` and `estimate_costs` give five significant digits; the economist states the currency and price year, the sources and gemini's 365.25-day year.
- QA-114: `set_case` gives `version_is` (the problem state's count, not the app's case version); the prompts name no version number to the user.

## [0.4.82] - 2026-11-05

### Changed

- Every tool is explained in exactly one skill (`tools:` in its frontmatter), with the usage its docstring held; a tool's description is its one-line purpose and its skill's name. New skills: `setting-the-case`, `simulating-a-plant`, `finding-sources`, `memory`, `working-in-a-team`. `ask_user` and `ask_economics`, whose calls are questions, carry their own skill section in their description. A test fails on a tool in no skill or in two. The `memory` skill is not listed when the memory is off.

### Fixed

- IMP-018: `build_plant`, `patch_plant` and `merge_designs` are checked whole before the user is asked to approve them; nothing is stored by the check.
- IMP-014: a `not_allowed` patch names the engineer's own parts; an engineer's plant issues list its own first and mark each other one with its owner.
- IMP-015: a tool error that repeats the tool's previous error (same code and path) carries `repeated`: change the call or hand back.
- QA-116: a tool the user denied is not asked again in the same request, by any agent of the run; an explanation request is answered in text.

## [0.4.81] - 2026-11-05

### Added

- The first result of a tool in an agent's conversation carries the skill that explains it (`[skill <name>, sent with the first call of <tool>]`), once: an agent without `read_skill` (the engineers) gets it too. A text result gets it after the text, a dict result a `skill` key.
- `evaluate_module` takes `design` or `result` (with `time`) and a module id as `name`: the plant's values fill the parameters and controls the call leaves out, and a result gives T, p and m_dot of every required inlet at that step (the largest inflow without `time`); the call gives only each inlet's fluid (IMP-013). Its usage moved to the new skill `evaluating-a-module` (also `describe_module`, `list_modules`); the tool descriptions name the skill.

### Fixed

- IMP-012: `evaluate_module` fixes slips of form and says so in `notes`: a type in snake case or another case (`heat_pump` -> `HeatPump`), a control given as a parameter or the reverse, a plant-file `range` on a value, a `{value}` choice, `inlets: []`. `set_case` drops `over` and `when` on a requirement read over the whole period (`unmet_share`, `count`) and lists it in `converted`.
- QA-105: `ask_economics` keeps the per-energy map all given or all open (a map with the chillers open gave no cost metric); the case lead opens the whole map for a cooling case.
- QA-104: a requirement with no value in the reports geomind stores names the failed steps that cause it.

## [0.4.80] - 2026-11-05

### Changed

- The case lead takes economics values from an assumptions document in the knowledge base (or a project file) that covers the case before the cost catalogue, as `ask_economics` `{key, value, unit, source}` citing the document; keys no file and no knowledge give stay `open`; with such a document and no per-energy price, every `opex.per_energy.*` key is `open`. A return temperature an assumptions document gives is the design choice proposed. `ask_economics` says a `value` with `source` may come from a knowledge document.

## [0.4.79] - 2026-11-05

### Fixed

- QA-091: `set_case` judges a per-step temperature requirement on a heating or cooling supply `when: running` when it was given `always` or no `when`, listed in `converted` with the reason (an idle loop on a zero-demand day is no supply). The case lead writes the brief's fixed supply temperatures `when: running` and adds `heat_delivered` / `cold_delivered` (`unmet_share` at most 0.01, an assumption) over the whole year, as gemini's hackathon sample does.
- QA-090: the design lead stops after three changes aimed at one failing requirement, keeps the design that fails least (simulated and checked) and reports the open requirement (value, limit, steps, why); the project lead then asks the user once (accept, change the requirement, stop).
- QA-094: network return temperatures are a design choice of the team with a reason, within the case's limits, proposed in the one question; never a missing case value the design waits for.
- QA-095: the knowledge row `co2-grid-organisers-2026` (300 g/kWh, the GeoHackathon 2026 organisers' reference value) ships; the case lead recommends first a row whose note recommends it for the case's brief.

## [0.4.78] - 2026-11-05

### Fixed

- QA-074: `calculate` takes the named constant `g`, the standard gravity 9.80665 m/s2 (shown with its value in the expression); with gemini 0.6.12 (`m/s2`, `N/kg`, `kg/m2`) a density × g × depth gives a pressure. An unknown unit lists the nearest units gemini knows.

## [0.4.77] - 2026-11-05

### Added

- QA-088: a study record (`study/<name>`) of `run_study`, `size_plant`, `optimize` and `evolve_structure` holds `runs`, one per run: `{plant_name, case_name, design, result, report, run}` with gemini's evaluate report (`report.to_dict()`, display units), the run record (`run.to_dict()`, `null` for a study that ends with a design) and `result/<id>`, the run kept as `simulate` keeps it (series, plant, case). size, optimize and evolve simulate their stored design once for it; a design that does not run gives `{design, error: {code, message}}`. Additive: the other keys are unchanged.

## [0.4.76] - 2026-11-05

### Fixed

- QA-079 (the UTC question asked twice): a shared rule says an item the user approved in an answer ("approve A and B") is settled: recorded confirmed at once and never asked again; a follow-up asks only what is new (a value gemini derived from the answer).

### Changed

- gemini request 35 is closed by gemini 0.6.11 (the ESP's out_of_range names the negative curve windows).

## [0.4.75] - 2026-11-05

### Fixed

- QA-079 (geomind part): a typed answer to the economics question that approves all in its first sentence ("Approve all as recommended, with their sources. ...") sets the economics as the option does, and the rest of the text comes back as `user_note`; "approve all except/but/without ..." stays a change. Any other typed answer says `economics: not set` with what to do, so the same question is not asked again unchanged.

## [0.4.74] - 2026-11-05

### Fixed

- QA-084: `ask_economics` never recommends a subsidy row: the `revenue.subsidy` keys stay open unless the case lead names them because the user or the brief gives a subsidy.
- QA-085: the economics question marks each row of one country's prices (`prices of the Netherlands`, from the row id or a national scheme such as SDE++) and says they fit only a site there: approve them as an assumption or name the site's country.
- QA-086: in permission mode `auto` (the chat's auto-approve) a run at its step limit takes its steps again by itself, three times per agent run (`rule` `mode:auto`), then asks as before.

## [0.4.73] - 2026-11-05

### Added

- QA-081: `gd.errors.AlreadyAnsweredError` (a `RequestError`): `Run.resume` with the id of a request the run already settled raises it, so a caller that sent one answer twice treats the second as a no-op instead of failing the run. An unknown id is a plain `RequestError` as before.

### Fixed

- QA-087: `web_search` allows six searches per agent and run; each result says `searches_left`, and the next search is refused with the advice to propose a labelled assumption or name the gap. The `web-search` skill says three queries per value at most.

## [0.4.72] - 2026-11-05

### Fixed

- QA-082 (the cause): `simulate` ran, but its summary read an ESP's curves on the plant without the case applied, and gemini's "uninitialized parameters" error listed `d0.gradient`, `surface_temperature`, `permeability` and `thickness` as missing; every simulate with an ESP failure group failed so. The summary now gives that group without the curve, and the run's real failures (an ESP outside its flow window, negative pipe pressures, an unmet supply temperature) reach the agent.

## [0.4.71] - 2026-11-05

### Fixed

- QA-083: an unexpected exception in a tool reaches the agent as `internal` with its class, message and innermost file and line, and the advice to change the input, instead of a bare `<tool>: internal error`. With gemini 0.6.10 a bare inlet name in a plant file is a coded `invalid_connection`.

## [0.4.70] - 2026-11-05

### Fixed

- QA-082: `simulate`'s `changes` set the plant's own options: `{"control": {"dispatch": ..., "outages": ...}}`, `{"params": {...}}` or `{"backup": {"value": ...}}`; before, they were read as module paths and refused. With gemini 0.6.9 the check names a doublet's missing depth first, with why.

## [0.4.69] - 2026-11-05

### Fixed

- QA-080: the case lead writes a range the brief gives with both ends (a flow of 50 to 300 m3/h) as one requirement with `min` and `max`. With gemini 0.6.8 two one-sided rules also make one flow range.

## [0.4.68] - 2026-11-05

### Fixed

- QA-078: calculation ids (from `calculate` and `run_python`) are random, `C` and six hex digits, so calculations made at once never share an id; before, each counted from the state it saw and two nested runs both wrote `C1`, after which every state change of the run failed. A stored state with a repeated calculation or finding id loads again, keeping the first.

## [0.4.67] - 2026-11-05

### Fixed

- QA-076: `design.owners` written with an engineer's tool name (`reservoir_engineer`, `well_engineer`, `energy_systems_engineer`) or in words names that discipline; the reservoir and well engineers were refused their own parts (`patch_plant` not_allowed). With gemini 0.6.7, `read_plant`, `build_plant` and `patch_plant` return an incomplete plant's missing values as `issues` again instead of failing with `missing_value` (gemini 0.6.5 regression).

## [0.4.66] - 2026-11-05

### Fixed

- QA-072: no agent attributes to the user what the user did not write: a shared rule names a rule of geomind or gemini (dates without an offset are read as UTC), a file or the agent's own choice as what it is; the case lead's time-zone line says UTC is gemini's reading, and a zone no file or user message states is an assumption to confirm, never "the user's instruction".

## [0.4.65] - 2026-11-05

### Fixed

- QA-071: `web_search` asks SearXNG for English results (`language=en`) and refuses a query longer than 8 words or not in English (non-Latin letters, or common Dutch, German, French or Norwegian words), naming why. Its description and the `web-search` skill teach queries: one value, 3 to 6 English technical terms (quantity, technology, unit, region and year when they matter), never a sentence, chat text, the project itself or a value the files already give; 2 or 3 refined queries when results are weak, primary sources first; and first whether the value is needed at all (a detail the brief never mentions is a labelled assumption or a gap, not a long search).

## [0.4.64] - 2026-11-05

### Fixed

- QA-070: a nested agent's call (`Delegate`, `Team`) that a worker restart left open is asked again with the same brief when the run resumes (`reruns_after_crash`), instead of failing at once with `interrupted by a crash; it may have run in part` (0.0 s); its old nested run is still ended and its spending kept. The project lead never narrows the user's brief on its own: a failed team gets the same brief once more, and a second failure is said plainly (what was not done and why) or asked.

## [0.4.63] - 2026-11-05

### Added

- QA-047 (second part): every answer of a nested agent (`Delegate`, team members included, also after a pause) is kept as a finding: the whole answer as the chat artifact `finding-<id>`, and a `Finding` item `{id, agent, task, summary, reference}` in the problem state's new `findings` list (the newest eight are shown), which `update_state` cannot write. A run that stops before the work is written (a cancel, a pending approval) leaves it for the next run; the shared rules say to read a finding with `read_stored` before asking that teammate again. The project lead gets `read_stored`.

## [0.4.62] - 2026-11-05

### Fixed

- QA-069: `set_case` checks the stored case against each of the project's plants (`gm.check`) and returns `plants_need`, `[{path, message, plants}]`, the case values a plant still lacks (such as `site.air.pressure`), with a note; the case lead's checklist calls the case complete only when it is empty or each path was asked. `gm.case.missing` alone lists only what the case file needs.

## [0.4.61] - 2026-11-05

### Changed

- Agent tools feature, step 4 (move only how-to a role needs sometimes; core workflows stay in the prompts): new skills `connectors` (the case lead's server how-to), `economics` (the economist's uncertainty, sensitivity and study rules), `report` (quoting a structure search; the explainer gets `read_skill`) and `comparing-designs` (the design lead's superstructure and family comparison), each with a `read_skill('<name>') before ...` pointer where the text was.
- A skill whose `tools` names only tool names is listed only to an agent offered one of them (MCP tools count); `read_skill` still reads it.

## [0.4.60] - 2026-11-05

### Fixed

- QA-061: a question that repeats paths answered before no longer shows the agent's note (`Already answered in this run ... (request-530): "..."`) to the user; only a question that is just a list of paths gets one plain line, `You answered <paths> earlier in this chat; answer only <paths>.`

## [0.4.59] - 2026-11-05

### Fixed

- QA-065: the case lead maps a brief's limit on the number of doublets to a requirement `{on: doublet, quantity: count, min, max}` (no `over`, `when`, `unit`) and checks that every hard rule of the brief is a requirement or named as open; the design lead says the case states a rule only when `read_case` shows that requirement, and hands a missing one over as a case change.

### Changed

- Skill `calculator`: says that `power`'s integer `exponent` is the one plain number given outside the operands (structure, not data; Sahand).

## [0.4.58] - 2026-11-05

### Added

- Agent tools feature, step 3: `web_search(query, limit)` asks the SearXNG at `GEOMIND_SEARCH_URL` (results: title, url, snippet, engine, date) and `read_web_page(url, start)` reads one public HTML page or PDF (url, site, kind, title, publisher, author, date, text in 30000-character parts with `next_start`); both effect `external`, refused for non-public addresses at every redirect, not offered when `GEOMIND_SEARCH_URL` is unset. New skill `web-search`. The case lead gets `read_skill`, `calculate`, `web_search` and `read_web_page`; the five agents with `calculate` get the web tools.

### Changed

- `calculate` (Sahand): operands may also be plain numbers `{"number": 24, "unit": "h"}` (shown as `24 h (plain)`, source kind `number`) and constants `{"constant": "pi"}` or `"e"` (source kind `constant`), but every calculation needs one sourced operand at least; `run_python` takes the same inputs and needs one sourced input or a project file.

## [0.4.57] - 2026-11-05

### Added

- Agent tools feature, step 2: `run_python` (effect `execute`) runs model-written Python in `gd.sandbox.DockerSandbox` (back from 0.4.21: one container per call, no network, read-only root, in-memory workspace, limits from `GEOMIND_SANDBOX_IMAGE`, `_TIMEOUT`, `_MEMORY`, `_DISK`, `_CPU`, none with a default). Inputs are references to sourced values (as `calculate`'s operands) given to the code as variables; the code may hold no number above 10 as a literal; numbers written to `result.json` become calculations citing the code. `Run`, `Run.load` and `Engine` take `sandbox=`; a run without one does not offer `run_python`. New skill `python`; new settings `sandbox_*` and `search_url` (`GEOMIND_SEARCH_URL`); `gd.errors.SandboxError` is back.

## [0.4.56] - 2026-11-05

### Added

- Agent tools feature, step 1: skills are folders, `geomind/skills/<name>/SKILL.md`, with frontmatter (`name`, `description`, `tools`, `roles`); an agent's system prompt lists only its role's skills and `read_skill` refuses others; the three skills moved from `prompts/skills/` under the same names. New skill `calculator`.
- `calculate` (effect `compute`): derives a value from references to sourced values (case field, confirmed assumption, catalogue row, stored result part, earlier calculation), never a typed number; gemini converts every unit. The result is kept as a `Calculation` (C1, C2 ...) in the problem state's new `calculations` list with each operand's source; `update_state` cannot write it. Given to the design lead, process engineer, analysis lead, economist and reviewer.

## [0.4.55] - 2026-11-05

### Fixed

- QA-043: with gemini 0.6.5 a relative humidity takes `%`, so the case lead sets a server's humidity series in % as it is (`"unit": "%"`) instead of leaving it out and asking the user.

## [0.4.54] - 2026-11-05

### Changed

- QA-013 (IMP-001): `ask_economics` fills every catalogue key the case lead does not name with its recommended row itself (sourced over placeholder, verified over secondary, no upper bound or proxy, the latest year; a real discount rate before a social or nominal one; reference-only rows never), its other usable rows in `others`, and a key with only placeholder rows in `open`. The case lead sends only the exceptions (a row of the site's country, a key open, a value from a server or the user), so the call is short and no longer runs past the output limit. The question the user sees is unchanged.

## [0.4.53] - 2026-11-05

### Fixed

- QA-011: a nested run that a passing provider failure stopped (`OpenRouter: status = 504; Upstream idle timeout exceeded`, a timeout) is run again once by its delegate, with a note to go on from what the problem state already holds, instead of returning `nested_stopped` for the lead to start over.

## [0.4.52] - 2026-11-05

### Data

- Cost catalogue (`data/knowledge/cost-sources.csv`), Sahand's decision of 2026-11-05: the 19
  placeholder rows and the three rows that cannot be converted to EUR at 2015 prices (QA-045) are
  removed; four cited rows are added (QA-006: compression and absorption chiller fixed O&M,
  production pump replacement). 153 rows, none without a source. `cost-sources.md` lists them.

## [0.4.51] - 2026-11-05

### Fixed

- QA-009 (seen again): an answer that picks a fixed option (`approve all`) answers only the paths its question offered a value for; a key the question left open is still open, so asking it again no longer says "Already answered in this run, not asked again" for it. The repeated case questions of run f78c671a came from a delegated answer, which QA-010 (0.4.46) handles.

## [0.4.50] - 2026-11-05

### Fixed

- QA-050: a read-only MCP call a server refuses on its rate limit ("Minutely API request limit exceeded. Please try again in one minute") waits 61 s and is sent again, up to twice, inside the same call; still limited, it is `rate_limited` with the advice to do other work first and call once later, so the run no longer stops on the same-error guard.

## [0.4.49] - 2026-11-05

### Fixed

- QA-055: with no named pump and no curve, the well engineer sets the ESP's `pump_type` to `"unspecified"` and leaves the curves to the doublet, which derives them from its complete design values and the case's pump efficiency (as gemini's reference plant); `evaluate_module` of the ESP alone is no reason to ask. The design lead no longer asks the user for a pump curve or stage coefficients.

## [0.4.48] - 2026-11-05

### Fixed

- QA-052: `build_plant` and `patch_plant` take the plant options `params.backup`, `params.control.outages` and `params.control.dispatch` given as a bare string (`"none"`) as `{"value": "none"}`, instead of refusing the plant after the user's approval.
- QA-054: no prompt, and no tool message the model reads, names an internal bug id any more, so agents no longer tell the user "Per QA-015 I stop here".

## [0.4.47] - 2026-11-05

### Fixed

- QA-016 (reopened): a side-by-side engineer called alone (`well_engineer`, a `runs_beside` delegate) also never pauses for an approval: such calls of one step run together, and the pause of one never reached the chat (run 0cb4b436 waited 90 minutes). Its approvals are allowed with the rule `beside:<rule>`, as inside `fill_parts`.

## [0.4.46] - 2026-11-04

### Fixed

- QA-010 (Sahand's decision, option A): when the user delegates the open case values, the case lead searches the knowledge base and every connected server first, then proposes the values still without a source in one question, each labelled "engineering assumption, no source" with a one-line reason; on approval they are set and recorded as confirmed agent assumptions. The project lead briefs it so instead of finishing with an incomplete case.

## [0.4.45] - 2026-11-04

### Fixed

- QA-047 (part): after a stopped, cancelled or interrupted run, the project lead's brief names the design the problem state already holds and the design lead goes on from the latest stored design instead of building the plant again. The engineers' lost work of the reported run is QA-016's (fixed in 0.4.30). Findings not yet written (the geoscientist's answer of a run that stopped before set_case) still need a work-in-progress record: development mode.

## [0.4.44] - 2026-11-04

### Fixed

- QA-045: `ask_economics` leaves out a catalogue row with no 2015 value (`injection-pump-geophires-500kw`, `esp-geophires-500kw`, `corrosion-inhibitor-ouzounian-1989-dogger`) with a note, instead of refusing the whole question: a recommended row gives way to the key's first usable other row, or the key is open.

## [0.4.43] - 2026-11-04

### Fixed

- QA-043: the case lead leaves a server's humidity series in `%` (open-meteo) out of `site.air.relative_humidity` at once, tells the user it is not usable, and asks for the fraction, instead of retrying it and dropping it silently. gemini request 38 asks gemini to accept `%` on a fraction leaf.

## [0.4.42] - 2026-11-04

### Fixed

- QA-042: a `set_case` with only `files` and `columns` after a full call of the same run is refused with the step of that call and the ask to send it again whole with only the fix (such as each series' `time_zone`), instead of the empty case skeleton; with 0.4.40's check before an approval, the user is no longer asked to approve or deny such a call.

## [0.4.41] - 2026-11-04

### Fixed

- QA-041: the case lead recommends a catalogue row of the site's country, then its region, before another country's, and never a row its note calls an upper bound or a proxy (the COVRA radioactive-waste tariff) over a usable one; a user's price without a price year is named in the question's note and its year asked, as it is set as 2015 EUR.

## [0.4.40] - 2026-11-04

### Fixed

- QA-037: before the engine asks the user to approve a call, a tool's `precheck` may check it without its effect; `set_case` runs gemini's check of the whole case without storing anything. A call gemini refuses comes back to the model as its error at once, so the user approves only a case gemini accepts, once.

## [0.4.39] - 2026-11-04

### Fixed

- QA-034: the case lead's prompt says a demand is a series (file or values) or a constant power and no tool builds a series from a peak and an annual energy, so its question no longer offers that way in and then drops the user's answer.

## [0.4.38] - 2026-11-04

### Fixed

- QA-023: a project whose case is `ready` (the backend's state of a set case, as after Copy a case) is past the case stage, so a new chat offers the plant ("Design a plant"), not building the case.

## [0.4.37] - 2026-11-04

### Fixed

- QA-020: the reservoir, well and energy systems engineers' prompts say to read the case and the plant once, as the results stay in the conversation, and again only after their own patch.

## [0.4.36] - 2026-11-04

### Fixed

- QA-018: the process engineer's prompt says a plant with the `type` of a gemini class takes that class's modules exactly as `read_plant` returned them, so its first `build_plant` is no longer refused for a hand-written structure.

## [0.4.35] - 2026-11-04

### Fixed

- QA-014: `read_case` of a section the case does not set yet (`utilities`, `initial_state`, `economics`) returns `{section, unset: true, note}` with the sections the case has, instead of an error per section.

## [0.4.34] - 2026-11-04

### Fixed

- QA-012: when the provider reports the output limit (`finish_reason: length`) far below it (1 of 16,000 tokens), the model reads that the provider ended its answer early and to send the same step again, instead of being told its answer was too long and to think less.

## [0.4.33] - 2026-11-04

### Fixed

- QA-002: the case lead's prompt says an efficiency, a share or a rate is a fraction with no unit (70 % is 0.7) and a bound on one equipment value has no `over` or `when`, so `pump_hydraulic_efficiency` is no longer sent as 70 % and refused.

## [0.4.32] - 2026-11-04

### Fixed

- QA-026: an approval's message shows what the call sends (its input as indented JSON, cut at 4,000 characters), so the user sees the keys, values, units and sources of a `set_case` before approving; before, it read only "Allow set_case (write)?".

## [0.4.31] - 2026-11-04

### Fixed

- QA-015: the design lead stops as soon as gemini names a case value as missing (`site.air.pressure`) and hands over with `case change needed`, instead of building and filling parts for a sizing gemini refuses; the project lead sends the design team on only after the case lead asked the user for those values.

## [0.4.30] - 2026-11-04

### Fixed

- QA-016: a member of a side-by-side team (`fill_parts`: the reservoir, well and energy systems engineers) can no longer stop on an approval it cannot wait for. Its approvals are allowed and logged with the rule `beside:<rule>`; before, the request came back as `fill_parts` output, never reached the chat, left the run row `waiting`, and the engineer's work was lost when the lead called `fill_parts` again.

## [0.4.29] - 2026-11-04

### Fixed

- QA-009: every `ask_user` answer is kept in the problem state as a confirmed user assumption (`answer.<id>`, the question and the answer), so a later agent or a new case-lead run reads it instead of asking the same question again; the same question asked again replaces its answer.

## [0.4.28] - 2026-11-04

### Fixed

- QA-004: `ask_economics` checks a key that takes no unit before the user is asked. A row's ratio of one unit to itself (`kg CO2e/kg CH4` on `accounting.gwp.CH4`) is set with no unit and a note; any other unit there (`%`) is refused at once, so approve all is no longer lost on gemini's `invalid_unit`.

## [0.4.27] - 2026-11-04

### Fixed

- QA-007: `ask_economics` no longer refuses the whole question when a key in `values` or `open` is not an economics key (`utilities.electricity.co2_intensity`). The key is left out, the question names it ("Left out, not economics keys"), and the approve-all result lists it in `not_set` so the case lead sets it with `set_case` at its own path.

## [0.4.26] - 2026-11-04

### Contract changes for the backend

- Next-step suggestions are always English. The Persian labels and the choice by the language of the user's last message are gone (Sahand: no file holds Persian text). A suggestion the project lead proposes in Arabic script is refused and the stage's own list is shown.

## [0.4.25] - 2026-11-04

Fixes production run 86ddac2a: the case lead's `ask_economics` call ran past the 16,000-token output limit three times, arrived as `{}` (`values: Field required`) and the run stopped with a case and no economics.

### Contract changes for the backend

- `ask_economics` reads each named row's value, unit, source, year, url and status from the knowledge base's `knowledge/cost-sources.csv` itself; the case lead sends `{"key", "row"}` and the other rows' ids in `others` (a bare id or an object). A value the model typed for a named row is replaced by the catalogue's. A row id that is not in the catalogue, a row of another key and a row without a value are refused with the key's row ids. A run without the catalogue in its knowledge base keeps the fields of the input as before. Additive: `OtherRow.value` is optional.
- A completion whose output reached the call's `max_tokens` is a cut (`finish_reason` `length`, the provider's own in `reported_finish_reason`), so the model reads the cut note and answers shorter, instead of a tool call with an empty input.

### Prompts

- Case lead, step 5 and the catalogue rule: values by row id only, never copied.

## [0.4.24] - 2026-11-04

geomind 0.4.24 (on gemini 0.6.4) uses more of gemini 0.6.2 and 0.6.3 (evolve's stop, the evolution's explanation and table, `union_designs` over `gm.plants.union`, the economics' per-energy O&M, subsidy cap and ice storage) and fixes the bugs of a production run (B4 memory off, B5 bypass ownership, B6 the whole cost catalogue read, B10 MCP servers as plain dicts; B3, H2S in the dissolved gas, by gemini 0.6.4).

### Contract changes for the backend

- **Two new required settings**: `GEOMIND_EVOLVE_STOP_GENERATIONS` and `GEOMIND_EVOLVE_STOP_SECONDS`, each a number or `off`; a live run without them is refused, naming them.
- `evolve_structure` answers `stopped` and `why`; its stored result has `explanation` and `table`.
- New design-lead tool `union_designs`.
- New error code `memory_unavailable` (a memory store that fails); with the memory off no memory tool or memory text reaches any agent.
- `read_rag` takes `rows` (`{column: [prefix, ...]}`); a table still over 20,000 characters after `rows` and `columns` gives its outline and a note, never its text.
- MCP servers may be plain dicts `{name, url, transport, headers}`, as `Workspace.mcp`'s contract names them, besides `gd.mcp.Server`.
- Per-agent usage (additions only, below): `step.started` `session`, `context_window`; `step.finished` `usage` per call with `cached_tokens`, `context`; root `run.finished` and `RunResult` `sessions`, `agents`, `total`.

### Data

- The two discount-rate rows of the cost catalogue (EU financial 0.04, social 0.03) get their `value_2015` (a rate has no price year), so the case lead can offer them; they were never used.
- 18 cited rows from Sahand's second research batch (152 rows now): a Dutch geothermal discount rate (PBL SDE++ real 4.0 %, nominal 5.6 %; the social CBA rate 2.25 %), pipe O&M 1 %/yr (PBL Vesta MAIS), and proxies for circulation pump and ice storage O&M and for inhibitors; `cost-sources.md` lists them and the two that cannot be used (a per-m3 waste price, a 1989 franc price).

### Known issues

- gemini still refuses `opex.fixed.pipe` per MW per year (two catalogue rows unused); no per-energy catalogue rows yet for the chillers.
- gemini describes each map entry as "The entry of this map for <key>."; geomind shows the map's own description.
- gemini reports no SO2 from burnt H2S.
- An end-to-end run needs a pressure or the site's elevation, from a file, the knowledge base, an MCP server or the user: no default.
- The shortened-history note can invite a `{}` call; `run_manifest.json` `models` lists only the roles that started; `read_case` of a missing section is an error.

### E2E fixes: design

- E2E-13, `missing: 0` but `simulate` refused the plant (`params.control.outages is missing`,
  then `d0.riser: esp_depth = None`): the `issues` of `read_plant`, `build_plant`, `patch_plant`,
  `merge_designs` and `union_designs` now name every value `simulate` needs. Besides gemini's
  check: `params.control.dispatch` and `params.control.outages` when the plant does not state
  them (`missing_value`, `suggestions` the values gemini's schedule implements), and, once
  nothing else is missing and the state has a case, what a one-step run on gemini's schedule
  refuses, such as `params.d0.riser.esp_depth` (`invalid_design`; the path is taken from
  gemini's message only when the plant has that parameter). **Contract**: no new field or code;
  `issues` and `missing` may hold these entries, and a class plant read without its rules lists
  both. The run check adds about 0.1 s to a call on a ready plant, off the event loop.
- Prompts: the well engineer sets the pump depth (`well.esp_depth` and `riser.esp_depth` equal
  to the ESP's `setting_depth`, both segments) when it sets the pump by hand; the design lead
  sets the two control rules itself, sends an `esp_depth` issue back to the well engineer and
  simulates only at `missing` 0.
- gemini request 33 (`.claude/docs/plan.md`): `gm.check` should list both, and the run's
  `invalid_design` carry its path.
### E2E fixes: questions (asked-once guard)

- E2E-3, E2E-7, E2E-11, behaviour: asked-once applies to the same question about the same value, not to an earlier mention of the path. A path stays answered only when the new question offers nothing for it the earlier one did not; a number after the path the earlier question did not have, or a confirmation, makes it a new question, so a value found after an answer like "use Trondheim 2027 data" (an MCP value) reaches the user to confirm (`engine/questions.py`).
- Shortened list items after a full path are paths: `site.fluid.dissolved_gas.N2, .H2S` and `utilities.gas.composition.CH4, C2H6, CO2` (E2E-11).
- "Answer only <paths>" is added only to a question that is nothing but a list of paths with no value; a question with a confirmation or other content is asked whole, with the earlier answers under it (E2E-11).
- The "Not asked again" result no longer says "a value it does not give stays open"; it says a value found since is a new question to confirm with its source (E2E-7). The case lead's prompt says the same: an answer naming a source gives no value. No contract change.

### Bugs from a production run (0.4.24.dev2)

Run c8bf2381 (chat b96805e4) on 0.4.22.

- B4, memory off: the `internal` from `search_memory` was 0.4.22 taking the workspace's bound
  `memory` method itself as the memory (`memory.entries` failed); 0.4.23 already calls
  `Workspace.memory(project_id)`, and tests now pin, for every shipped agent and a nested run,
  with `GEOMIND_MEMORY=off` and with `Workspace.memory` returning `None`, that no memory tool or
  curator is offered and no prompt or tool description speaks of the memory. Role files mark their
  memory-only parts `<!-- memory -->` ... `<!-- /memory -->`; `Prompt.render(memory=True)` (new
  keyword) drops them when the memory is off, and the knowledge section's memory line goes too.
  "A number from memory" (what a model recalls) now reads "a number you recall". New tool error
  code `memory_unavailable`: a memory store that raises answers it with its error, never
  `internal`; an experience entry whose features are no numbers scores them as missing.
- B6, the case lead read the whole cost catalogue (about 21 steps at 55-80k input tokens):
  `read_rag` takes `rows={column: [text, ...]}`, the rows whose value starts with one of the
  texts, and a CSV or TSV still longer than `LARGE_TABLE_CHARACTERS` (20,000) after `rows` and
  `columns` gives only its `table` outline and a note naming `search_rag`, `rows` and `columns`,
  never its text or pages. The case lead reads the catalogue's rows of the missing keys only.
- B10: `gd.mcp.list_tools`, `McpClient`, `load_servers` and the run's `Workspace.mcp` take the
  plain dict `{name, url, transport, headers}` as well as `gd.mcp.Server` (addition); a bad dict
  is `bad_response` naming the server and the fields, never a header value. `failure()` names the
  server when it can (`mcp server` otherwise) and keeps the real error's class and text.
- B3 (gemini, H2S) is gemini's: not changed here.

### Context per agent

Context is each agent's own, steps each run's own, budgets the run tree's (Sahand 2026-11-04;
[context.md](../.claude/docs/context.md#per-agent-or-per-run-tree)). No context decision summed a
run tree before; the audit found none and tests now pin it.

- Compaction reads the larger of the agent's own rendered messages (estimated) and the input tokens
  of its own last call (`RunState.last_input_tokens`, from its `llm.completed`, cleared by its
  compaction), so tool schemas count; never `usage`, which includes nested runs.
  `is_over_threshold(messages, model, last_input_tokens)` takes the count (internal).
- Pinned: a parent whose nested runs used far past the window neither compacts nor gets a smaller
  `max_tokens`; a nested agent compacts on its own context only; each nested run counts its own
  steps (`max_steps`, `engineer_max_steps` per delegation).
- `TokenBudget` and `CostBudget` are run-tree spending caps, as their docstrings and
  `--max-tokens` now say; no token cap acts as a context window.
- Tests: `GEOMIND_CONTEXT_WINDOW` of the test settings is the test model's real window (1,048,576,
  was 128,000); the long-chat test sets its own window.
- B3 (gemini, H2S) is gemini's: not changed here; gemini 0.6.4 fixes it (below).

### E2E fixes: follow-up (economics input, ESP curves, stored paths, sizing issues)

From the e2e hunt (`.tmp/e2e-bugs/bug-list.md`) and the notes of the other fix sessions.

**Contract changes for the backend** (additive): `simulate`'s summary `failures[]` entry of an
ESP outside its curves (`out_of_range` at an `ESP` path) has a new field `curve` `{unit, flows,
resolution, negative_head, negative_power}`, and its `message` ends with those flow ranges.
`size_plant` now returns `checked_against`, `issues` and `missing` beside `design`, `study` and
`sizing`. `ask_economics` takes `row` as the row object too (its `id`) and `others[]` takes
`year`, `url` and `status`. An `invalid_input` of a call that does not fit the tool's schema has
a shorter `message` (one line per field and fault); its code, `path` and `suggestions` are as
before. No new error code.

- E2E-14: `ask_economics` was refused whole (47 and 30 pydantic errors, one per value, each with
  pydantic's link): the case lead sent `row` as the catalogue's row object and `others[]` with
  `year`. A row object is read by its `id`, its citation fields filling those left out
  (`economics.row_by_id`); one without `id` is refused saying `row` is the id; `others[]` takes
  the citation fields; the schema says `row` is the row's id as text. Any tool: a validation
  error is one line per field and fault, items of a list taken together ("values.*.row (47
  items, first values.0.row): Input should be a valid string (got dict)"), without pydantic's
  links (`dispatch.validation_message`).
- E2E-15: `simulate` failed 450 of 504 steps on the ESP curve and the design lead then patched
  `head_coefficients = [1e7, 0, ...]` with no source. The failure now names the flows from zero
  to `maximum_flow` where the curve's head or power is negative (`runs.curve_ranges`, by gemini's
  own `head_function`/`power_function` at its reference frequency). Prompts: the well engineer
  never types an ESP's curves (gemini derives them from the doublet's pump design values, or a
  named source gives them, or `question needed: the ESP curve`); the design lead never patches
  them, sends a curve failure back with its `curve`, and asks the user for a curve no source
  gives. gemini request 35 (plan.md).
- Case lead: `discount_rate` is never open; the rate is a real one of a financial appraisal
  (the catalogue's prices are real, EUR 2015): `discount-rate-pbl-sde-2025-geothermal-real` over
  the 2022 real row, the others in `others`; the 2026 erratum rows and the waste density row
  are never a value nor an other; `waste-disposal-tfa-france-per-kg-filter-density` (3.87
  EUR/kg) goes with its status, secondary, and each other row's status shows in the question.
- ESP rows per W electric: the question says the row is electric, not shaft power, "not
  converted, the user decides" (`unit_bridge.economics_unit`, for a row and a key on different
  powers: electric, shaft, heat); the case lead's `note` gives the catalogue's share (shaft
  power about 0.85 to 0.9 of the electric rating, research report 3, now in `cost-sources.md`).
- The case lead's economics reminder no longer names `currency` and `price_year`.
- `read_stored` with a wrong path no longer outlines the value (an MCP answer's long text filled
  the error): it names the path walked, the keys there and, for an answer, its tables with their
  rows; `suggestions` are whole paths, the tables first.
- `size_plant` returns the sized plant's `issues` and `missing` as `patch_plant` does
  (`plant_issues`), so the model sees what `simulate` still needs (the plant rules, the pump depth).

### E2E fixes: the case and its economics

From the e2e hunt on 0.4.24.dev2 (`.tmp/e2e-bugs/bug-list.md`).

**Contract changes for the backend:** none in the tool schemas. `set_case(source="project")`
also reads a `case.json` among the project's files (`Workspace.files`/`file`), with the files it
names beside it, when `Workspace.case` has none. `ask_economics` no longer needs `currency` and
`price_year` (it sets them, below) and has a new refusal, code `invalid_unit` at `values`, before
the question is asked.

- E2E-1: `set_case(source="project")` said "has no case" for a project whose `case.json` is a
  project file (`files/case.json`): `Workspace.case` reads only one beside the project's data.
  A single `case.json` among the files (in a folder or not) is now the project case, its files
  read beside it; two are refused by name, a JSON whose `kind` is not `case` too. The refusal
  without any says where it looked (`case.json` beside the data, among the files: `list_files`).
- E2E-8: fewer `set_case` rounds. On a new case, `requirements`, `economics`, `files` and
  `columns` inside `changes` are taken as those arguments (the run spent two calls on "changes
  has 'requirements'" and "key 'files'"); a case that has them still refuses them in `changes`.
  A requirement efficiency or fraction outside 0-1 (#130) now comes back with gemini's own
  problems in one error, not after they are fixed; a series without its `column` gets the
  columns of its file in `suggestions`.
- E2E-9: `ask_economics` sets `currency` EUR and `price_year` 2015 itself whenever a value comes
  from a catalogue row: the catalogue's `value_2015` in `unit_2015` are EUR at 2015 prices
  (`cost-sources.md`; a test reads both files). Either named in `open` is taken out; another
  value for either is refused with where they come from. A key with a value and in `open` is
  refused naming the key in both; a key null in `values` and in `open` is open once.
- E2E-10: approve all failed with `units: quantity = 'money_per_volume_or_money_per_energy'`:
  `explain.unit_retry` joined gemini's "a unit of money per volume or money per energy" into one
  quantity. Each quantity is now looked up alone (`explain.quantities`), so `capex.ice_storage`
  lists the units of both bases. `ask_economics` checks each unit against its key before asking,
  every refused unit in one error with the units the key takes; a basis word after a row's unit
  (`EUR/MWh cold`, `EUR/W electric`) is set as the unit before it (`unit_bridge.economics_unit`,
  a name, no factor) and the question shows the row's unit beside the key's basis ("which the
  key reads per W of shaft power at the nominal flow"), also kept as `basis` in the citation.
  gemini request (plan.md): carry `quantity` and `accepted` in an `invalid_unit` problem.
- E2E-2 (prompt): the air values are read from a connected weather or elevation server before
  any question; with only the location missing, the question asks for the location;
  `relative_humidity` is named a fraction 0-1 (gemini refuses 80). The MCP source lines of the
  prompt are another session's.
- Catalogue batch 3 in the case lead's prompt: `opex.per_energy` takes the four kinds the
  catalogue prices (`boiler`, `electric_boiler`, `heat_pump`, `chp`; a test ties the list to the
  catalogue) and names the chillers in `open`; the ESP rows of `capex.production_pump` are per W
  electric, the key per W of shaft power, said in the question; the waste rows in EUR/m3 and t/m3
  and the two `discount-rate-pbl-sde-2026-erratum` rows are never a value nor an other.

### gemini 0.6.4

- The pin moves to gemini 0.6.4 (`requirements/gemini.txt`, `[tool.uv.sources]`; the range stays
  `>=0.6,<0.7`). It is a bug fix and an addition, nothing in geomind's use of gemini changes: no
  API, message, snapshot, recording or fixture changed, and gemini's examples are the same.
- B3, fixed in gemini: a case whose `site.fluid.dissolved_gas` names `H2S` (even at 0 mol%) passed
  `set_case`, then failed in `build_plant`/`simulate` with `gas composition: species = 'H2S'`.
  H2S now burns in boilers, CHPs and flares (lower heating value 518.07 kJ/mol) and forms no CO2;
  `utilities.gas.composition` takes `H2S` too. Tests: `set_case` keeps `H2S` (5 and 0 mol%) as
  given and gemini's case reads it so (test_case); `simulate` of the hackathon plant with 5 mol%
  H2S in place of as much CH4 runs with no failed step and less CO2 (test_runs; it fails on 0.6.3).
- No geomind workaround existed for H2S, so nothing was removed.

### E2E fixes: MCP

**Contract changes for the backend** (all additive except the `list_mcp` rows):

- `list_mcp` rows are now an outline `{server, name, read_only, summary, arguments}` (`arguments`
  is `{name: type}`, `required` marked) plus `note`; the whole row `{server, name, description,
  read_only, input_schema}` comes from the new optional input `tool`: `list_mcp(server, tool)`.
- `read_mcp` and `call_mcp` answer `{origin, answer, tables, structured, text}`: `origin` adds
  `arguments`, `tool_description` and `future`; `answer` is the artifact key `mcp-<16 hex>` of
  the whole answer (a new chat artifact); `tables` is `[{path, rows, columns, units, time_zone,
  first, last}]`. An answer over 2000 characters comes back short (`structured` without its long
  values, the head of `text`, `note`).
- New tool `save_mcp_table(answer, table, file, time_zone?)`, offered with the MCP tools. It
  writes the case files `case/<file>` (CSV, `time` in UTC) and `case/<stem>.origin.json` (the
  origin), both served by `GET /assistant/chat/{id}/files/{name}`.
- `McpError` has the new code `invalid_arguments` (JSON-RPC -32602); the tools answer it as
  `invalid_input`, no longer `mcp_unavailable`.

- E2E-4: the listing of all tools with their schemas (54 KB for open-meteo) was stored behind a
  reference (`geomind/tools/mcp.py` `list_mcp`, over `tool_result_limit`), and the MCP tools'
  `keeps_result` was never seen because `kept_calls` (`geomind/engine/context.py`) looked up
  only the agent's own tools. Now the outline (6 KB) is kept for the run, `kept_calls` counts
  the MCP tools, and arguments missing a `required` one or not in a strict schema are refused
  before the call, `path` `arguments.<name>`, close names in `suggestions`; that refusal, the
  server's and -32602 end with the tool's whole `input_schema`. Tests: test_mcp_answers
  (`test_list_mcp_shows_server_tool_and_argument_names_in_the_history` and five more).
- E2E-5: an answer leads with `origin`, `answer` and `tables` (path, columns, units, time zone),
  so `structured.daily` and its units are read before the text; the answer is kept for the run.
- E2E-6: `origin.future` is true when a date of the arguments or of a table lies after the day
  of the call, and `origin.tool_description` is the server's own first sentence ("Long-range
  climate projections ..."); `save_mcp_table` converts the times of the answer's `timezone` to
  UTC (Europe/Oslo 2026-01-12T00:00 is 2026-01-11T23:00:00Z); an answer without a zone needs
  `time_zone`, never one of geomind's. Prompts: the `MCP` section, the shared rules and the
  case lead say to cite a `future` answer as a forecast or projection, with the dates, and that
  the case's times are UTC.
- E2E-12: `save_mcp_table` saves a table of an answer as a case file with its origin (server,
  tool, time, arguments); the file name is made safe (`open-meteo Trondheim climate 2027` is
  `open-meteo_Trondheim_climate_2027.csv`); `set_case` names it as a series' `file` and
  `column` (test: gemini reads the saved 2027 climate table as `site.air.temperature` of the
  hackathon case). The case lead's prompt says how.
- Fixtures: the open-meteo listing and two answers recorded in the e2e runs
  (`tests/fixtures/mcp_open_meteo/`); the fake server answers JSON-RPC -32602 for a call without
  `market`.
- Left open: `read_stored`'s error for a wrong path still outlines a value with a long text
  (`geomind/tools/stored.py` `_step`), outside this part.
### Context per agent

Context is each agent's own, steps each run's own, budgets the run tree's (Sahand 2026-11-04;
[context.md](../.claude/docs/context.md#per-agent-or-per-run-tree)). No context decision summed a
run tree before; the audit found none and tests now pin it.

- Compaction reads the larger of the agent's own rendered messages (estimated) and the input tokens
  of its own last call (`RunState.last_input_tokens`, from its `llm.completed`, cleared by its
  compaction), so tool schemas count; never `usage`, which includes nested runs.
  `is_over_threshold(messages, model, last_input_tokens)` takes the count (internal).
- Pinned: a parent whose nested runs used far past the window neither compacts nor gets a smaller
  `max_tokens`; a nested agent compacts on its own context only; each nested run counts its own
  steps (`max_steps`, `engineer_max_steps` per delegation).
- `TokenBudget` and `CostBudget` are run-tree spending caps, as their docstrings and
  `--max-tokens` now say; no token cap acts as a context window.
- Tests: `GEOMIND_CONTEXT_WINDOW` of the test settings is the test model's real window (1,048,576,
  was 128,000); the long-chat test sets its own window.

### Per-agent usage (contract addition)

**Contract changes for the backend** (`.tmp/handoff/usage-contract.md`; all fields optional,
nothing removed or renamed; a log before 0.4.24 has none of them and still loads, exports and
replays, and the frontend shows "n/a"). A session is one run of one agent (`session` = `run_id`):
the root run, one nested run per delegation, the routing run.

- `step.started` gains `session` (its run id) and `context_window` (the model's window for this
  agent, `null` when unknown or for a rule agent).
- `step.finished.usage` is this step's own model call (with a compaction summary made in the step),
  never a nested run's or a running total; it was the step plus its nested runs before. Its JSON
  now shows `cached_tokens` (part of `input_tokens`). New `context`: `{used, window, remaining}`,
  `used` = this call's input tokens, `remaining` = `window - used` (`null` without a window);
  absent for a step with no provider call.
- The root run's `run.finished` gains `sessions` (`{session, agent, parent, model, steps,
  tool_calls, usage, context: {peak_used, last_used, window}}`, own calls only), `agents` (the
  sessions grouped by agent: `{agent, sessions, steps, tool_calls, usage}`) and `total`
  (`{input_tokens, output_tokens, cached_tokens, cost, steps, tool_calls}`); nested runs have none.
  Each model call counts once: the sum of `sessions` = `total` = the last `usage` event =
  `RunResult.usage`. When a step ended the run before sending its `usage` (a crash, a cancel), one
  more `usage` event comes before `run.finished`.
- `RunResult` gains `sessions`, `agents` and `total`, the same as the root `run.finished`; `None`
  for a nested run and a run that waits. `usage` stays.
- The `usage` event and `runlog`'s usage are unchanged.
- `geomind.stores.usage.usage_report(events)` makes the three from a stored log; the export has a
  "Tokens by session" table. The test copy of the shared contract
  (`tests/fixtures/contracts/shared.md`) has the new optional fields in its three rows, ahead of
  the backend's next version.
- Tests: `tests/unit/engine/test_usage_per_session.py` (a lead delegating one agent twice: own
  calls per session, no double count, two sessions grouped, a second session starting from its own
  messages, per-call `step.finished.usage`, a log without the fields and the 0.4.22 log replay),
  `test_events.py`, `test_delegate.py` (the step's usage is its own call now), `test_export.py`,
  `test_usage.py` (the routing run is a session; three export totals).

### More of gemini 0.6.2 and 0.6.3 (0.4.24.dev1)

**Contract changes for the backend:** two new required settings, no default,
`GEOMIND_EVOLVE_STOP_GENERATIONS` and `GEOMIND_EVOLVE_STOP_SECONDS` (each a number or `off`; a
live run lacking one is refused, like the other `GEOMIND_EVOLVE_*`); `evolve_structure` answers
`why` beside `stopped`, and its stored study result gains `explanation` and `table`; a new
design-lead tool `union_designs`. `merge_designs` is unchanged.

- `evolve_structure` passes gemini's `evolve(stop=...)` from the settings `evolve_stop_generations`
  (generations in a row with no new design on the feasible front) and `evolve_stop_seconds` (a time
  limit); `off` leaves a key out and both `off` spend the budget. The study file records `stop`.
  An unset one is named in the error. `why` says in words why the search stopped, naming the
  setting (`budget`, `stalled`, `converged`, `seconds`).
- The stored result of `evolve_structure` (`read_study`) keeps gemini's `Evolution.explain()` as
  `explanation` and `to_frame()` as `table` (`{columns, rows}`, the front in display units). The
  explainer quotes them with the study key under `Decisions`, never computing from them; the
  design lead quotes `stopped`, `why`, `explanation` and `table`.
- `union_designs(designs, name)`: gemini's `gm.plants.union` of whole alternative designs as one
  superstructure (`optional`, `choices`), with `structures` (the structure of each design, by
  design reference) and `notes` (values the designs state differently), then what is missing as
  `patch_plant` gives it. A union gemini refuses is its `invalid_design`; nothing is stored.
  `merge_designs` keeps its own patch merge: its designs share one topology, and a union would keep
  the first design's value where the engineers' patches must both apply.
- Case lead: rules for `opex.per_energy` (only as a map complete for the plant's producing kinds,
  since gemini then asks a price for each), the subsidy's `cap` (in `h/yr` it needs `capacity`,
  from a file or the user) and the ice storage keys (priced only when given).
- Catalogue (`data/knowledge/cost-sources.csv`): the gas boiler, electric boiler and CHP fixed O&M
  rows now give the source amount in EUR/MW/yr (1950, 1070, 9750), which `opex.fixed.<kind>` takes
  since gemini 0.6.2, instead of a share of an assumed capex; new row
  `sde-full-load-hours-geothermal-pbl-2026-over-20mw` (`revenue.subsidy.cap`, 6000 h/yr, PBL).
  134 rows. `cost-sources.md` lists what still has no row (`opex.per_energy` but for the CHP).
- Fix: the plant's `bypass` belonged to no discipline, so the integration engineer, whom its prompt
  tells to set it, was refused; it is the integration engineer's now.
- Energy systems engineer: the cost sizes gemini may ask for also name an ice storage's `volume` and
  a pipe's `nominal_capacity`.

## [0.4.23] - 2026-11-04

geomind 0.4.23 runs on gemini 0.6.3. It removes the workarounds gemini now covers (the doublet values engineers copied by hand, the control check, the °C/km mapping, its own field meanings where gemini describes a key, private study metric names), reads plant values in display units, takes its memory from the workspace (`Workspace.memory`, None turns it off), and takes `site.air.pressure` as the site's elevation, from which code computes the ISA pressure (ISO 2533:1975) for the user to confirm.

### Release choices

- `tests/integration/test_attached_files.py::test_the_run_replays` moved to the slow tier: it runs a whole design loop and replays it whole (1.4 s alone, over the fast tier's one-second budget).

### Known issues

- gemini still refuses `opex.fixed.pipe` per MW per year: two catalogue rows stay unused.
- gemini describes each map entry as "The entry of this map for <key>.", which says nothing; geomind shows the map's own description instead.
- An end-to-end run needs a pressure or the site's elevation from the user: there is no default, so without one it stops before sizing.
- The shortened-history note can invite a `{}` call; the model recovers on the next step.
- `run_manifest.json` `models` lists only the roles that started.
- `read_case` of a section the case lacks is an error, not an empty result.

### gemini 0.6.3 (0.4.23.dev2)

- gemini 0.6.3 (wheel sha256 `2fe06435…4444f023`), range still `>=0.6,<0.7`; its examples are
  unchanged.
- `read_plant` (and `build_plant`'s view) gives the plant file in gemini's display units
  (`Plant.to_dict(units="display")`, request 30); the ranges are read from it. The explainer
  quotes them as given.
- `set_case`: a gradient in `°C/km`/`degC/km` goes to gemini as given (request 31), so the
  gradient mapping of `unit_bridge` is gone and nothing is listed in `converted` for it; the
  unit-name mapping (`m³`, `·`, `MWth`) stays.
- `set_case` takes `site.air.pressure` as `{"elevation": {"value", "unit"}}` and sets the ISA
  pressure in Pa (ISO 2533:1975, `geomind/tools/gemini/air.py`), the elevation converted by
  gemini, its source in `site.air.about` and an entry in `converted`; no elevation and no
  pressure leave it unset. The case lead searches the files and the knowledge base, else asks
  for the pressure or the elevation in its one question, and shows the value for confirmation.
  `test_no_unit_math` counts 101325 as a factor and allows that one line, with its reason.
- `evaluate_module`: a control given as a parameter is gemini's `invalid_call` (request 27);
  geomind still names an unknown parameter and a parameter given in `controls`.
- `fields.py`: a case field's meaning is gemini's description (request 22), followed by geomind's
  note of where its value comes from; `CASE_FIELDS` and `ECONOMICS_FIELDS` are replaced by
  `CASE_NOTES` and `case_fields()`; `undescribed()` reads the schemas and is empty. gemini's
  "The entry of this map for <key>." is skipped, so a map's description covers its entries.
- The analysis prompts name what a study reads from `gm.study.metrics()` (request 26);
  `STUDY_KPIS` is gone.
- `data/knowledge/cost-sources.csv`: every `path` is a case key (`economics.<key>`,
  `utilities.electricity.co2_intensity`), as gemini's catalogue now (request 17); the DEA pipe
  transmission row (EUR/MW/m) is usable for `capex.pipe` (request 16). `opex.fixed.pipe` per MW
  and year is still refused (two rows).
- Prompts: the design engineers fill a doublet's design values and set an inner value only while
  gemini lists it (requests 11, 28); the reservoir engineer leaves the reservoir values to gemini;
  the case lead's `time.end` text is shorter (request 12); the units skill lists `°C/km`, `kW/K`,
  `MW/K` and `EUR/MW/m` (requests 29, 31, 16).
- docs/rules.md: gemini requests are only real bugs, unit problems and unclear errors; gemini never
  provides data, defaults or derived inputs for other packages. plan.md: each request's status.

### Memory from the workspace (0.4.23.dev1)

- Contract: the optional `Workspace.memory(project_id)` gives a project's memory; `None` turns the
  memory off for that project, with no fallback to `GEOMIND_MEMORY_DIR` or the folder store (no
  memory tools, no curator, nothing written). It is asked once per project and engine. Before, a
  `memory` attribute of the workspace was read and `None` fell back to the folder store.
- `GEOMIND_MEMORY_DIR` is required only with `GEOMIND_MEMORY` on and a workspace without a
  `memory` method (the command line); a run that needs it and lacks it raises `RunError` naming
  it. A memory the engine or the workspace gives needs only `GEOMIND_MEMORY_SIMILARITY`.
- `runtime.model_problems(memory_source)` and `runtime.memory_problems(memory_source)` take where
  the memory comes from (`settings`, `store`, `off`); new `runtime.memory_settings(source)`,
  `RunSession.memory_source()`.
- `.claude/docs/releasing.md`: gemini range `>=0.6,<0.7`; `main` takes `dev` with
  `git merge --ff-only`.

## [0.4.22] - 2026-11-04

geomind 0.4.22 on gemini 0.6.2 (`>=0.6,<0.7`, the 0.6.2 wheel pinned). Its agents run on
DeepSeek and on nemotron with the same prompts and fixtures; every team (case, design, analysis,
support, project) has its own per-agent tests; agents read the RAG knowledge base and MCP servers
through verb-first tools (`search_rag`, `read_rag`, `list_mcp`, `read_mcp`, `call_mcp`); a run
ends with next-step suggestions. The sections below are the 0.4.22 development steps, newest first.

Release choices (made without questions, as asked): released from `dev` at the merge of tracks k, l
and m, on gemini 0.6.2 as tested; no new live model runs; the version is 0.4.22 with no other change
to code or snapshots.
- Contract: `gd.runtime.model_problems(memory_source="settings")` and `memory_problems` take the memory's source (`settings`, `store`, `off`); called with nothing they behave as in 0.4.22, so the backend's `model_problems()` keeps working.

### Known issues

- `site.air.pressure` has no source in the brief or the knowledge base, so an end-to-end run stops
  before sizing (gemini request 32).
- The shortened-history note can invite a `{}` call (a tool called with no arguments).
- `run_manifest.models` lists only the roles that started, not every role of the run.
- `read_case` of a missing section is an error, not an empty answer.

### gemini 0.6.2 (0.4.22.dev64)

No version bump in this piece.

- geomind runs on the gemini 0.6.2 release wheel (`requirements/gemini.txt`, sha256 `8c4fde3e67922eff0ff2316a7b883001f0c1592a83d338df2ddc69ffdfba9b7c`; `[tool.uv.sources]`); the range stays `>=0.6,<0.7`. 0.6.2 is additive; gemini's example projects geomind copies are unchanged.
- Prompts: the case key trees and `describe_case` read each economics field with gemini's own description (`Economics.schema()`, requests 19/21); `ECONOMICS_FIELDS` keeps only the four fields gemini leaves undescribed (`format`, `kind`, `name`, `about`). The full case tree (read by part through `describe_case`) grows to about 20k characters; the prompts' `case_compact` is unchanged in size.
- Prompts: a superstructure may turn a whole part on or off, the peak boiler with its gas makeup and gas grid, or the cooling branch (process engineer); a module's off path is the plant's `bypass` `{module: {inlet: outlet}}`, `{}` removing it (integration engineer); the design lead reads `evolve_structure`'s `rejected`. `build_plant` with `from_class` carries `choices` and `bypass` to gemini unchanged.
- Contract (addition): `evolve_structure` answers `rejected` (each structure gemini refused before any simulation, `{structure, reasons}`) and `stopped` (why the search ended, gemini's `budget.stopped`).
- Behaviour: `set_case` no longer turns a gas fraction in `mol%` or `%` into the fraction: gemini 0.6.2 takes `mol%` (request 15), and `%` or `mol %` is only named `mol%` (listed in `converted`, the same number). `percent_fraction` and the one-line allowlist of `test_no_unit_math` are gone. The gradient mapping (`°C/km` to `K/km`) stays: 0.6.2 still refuses `degC/km` (request 31).
- Behaviour: a case gemini rejects at several paths (0.6.2 judges the whole case, request 13) comes back as one error starting `set_case: the case has problems at <n> paths, all listed here; fix every one in the next call:`; each `accepted units` suggestion names its field (`site.ground.gradient: accepted units: K/km, K/m`).
- Prompts: `module_reference` and `describe_module` show a list of quantities (gemini 0.6.2's `type: array`, request 14) as `array {value: [<number>, ...], unit}`.
- Prompts and data: the case lead's examples of a refused unit are those 0.6.2 still refuses (`capex.pipe` per MW and m, `opex.fixed.pipe` per MW and year); a key may take several bases, each its unit. The energy engineer gives `nominal_duty` or `energy_capacity` when the economics prices an exchanger per W of duty or a storage per MWh. Seven `path` cells of `data/knowledge/cost-sources.csv` name 0.6.2's keys (`opex.variable.chemical`, `opex.variable.waste_disposal`, `opex.per_energy.chp`; listed in `cost-sources.md`); a test checks every catalogue row's key and unit against gemini's schema, the three pipe rows gemini still refuses listed.
### Old logs are read (0.4.22.dev64)

- Behaviour: a replay of a log recorded before the case lead (geomind older than 0.4.22.dev7, or no version) that differs raises `ReplayError` saying the log was recorded by geomind <version> before the case lead and can be read, shown and exported but not re-run, with the first difference after it. Tests: the 0.3.1 compare log loads, maps its class paths (`RENAMED_CLASSES`), shows (`geomind show`, text and md) and exports (JSON run log, Markdown), and its replay raises that message.

### The slow tier green again (0.4.22.dev63)

The release profile's slow tests failed on dev62; none ran on a push to dev. No version bump in this piece.

- Fix, behaviour: `ComparisonDriver` (the `CompareLoop`) takes the project's case it loads by rule (`set_case`) and a case lead's run as the design loop does; it went from that `set_case` straight to the explainer, with no family designed (since fdbfed8).
- Fix, behaviour: a replay reads a recorded reference index (`results.index`, `designs.index`, `studies.index`) without the references the replayed runs make again, so an `unknown_name` message at a step lists what the run had there, not what it stored later.
- Evals: a task with `max_steps` that ends at its step limit (the question answered `stop`) does not fail as a run; its criteria decide. `challenge2/tight_budget`: a round without a design is no repeated failure (70b2c43), so the loop's own 7 steps end it with the partial answer; its recording has a third round.
- Evals: `challenge2/verifier` is `challenge2/reviewer`, task and recording. The `design_lead` tasks set the project's case in `setup`. `challenge2/colder_reservoir` and `user_profile` (hand-written): the design lead names the case change and the case lead's `set_case`/`save_profile` make it, the same calls and numbers; their first reply, for the case question the loop no longer asks, is gone. `evals/reports/summary.md` regenerated.
- Tests: the 0.3.1 compare log loads and exports; its replay now stops at the driver's first move, which changed by design (case lead, case by rule, `design_lead`/`reviewer`), with `ReplayError`; the reused-call schema rule stays pinned in the unit tests. `test_studies` sets `max_steps` in its module fixture.

### The third end-to-end run (0.4.22.dev62)

Run 4ca94d6e (`.tmp/e2e-final4/`), fixes #138 to #143; no version bump in this piece.

- Fix (#138), behaviour: a call identical (tool and whole input) to an earlier successful call of the same run does not run when its tool `repeats_same` (a pure tool not `runs_alone`, or a write with the new `Tool(sets_input=True)`, which `set_ranges` is) and no tool that is not pure ran with success between; its result is "same result as step N: <reference or outline>", `tool.result` `source` `repeat`. More than `max_retries` such steps in a row stop the run (`error`). A design lead had sent one `set_ranges` call 37 times (12.7k characters each) until two step limits.
- Fix (#139), behaviour: a new economics file starts from its header (`format`, `kind`, `name`), so `ask_economics`'s approve all on a case without economics is stored instead of refused as an older shape (seq 424).
- Fix (#140), behaviour: asked-once matches per path: a path named inside a multi-path question that was answered is answered (`site.air.pressure`, item 4 of request-259, then request-2872). A question with only answered paths takes the earlier answers; one with new paths too is asked with the earlier answers under it and only the new paths to answer.
- Fix (#141), behaviour: an object or array sent as JSON text that does not parse is refused naming `json`'s message, line, column and character and the text around it, and a Python literal there (`None`), instead of pydantic's "Input should be a valid dictionary".
- Fix (#142), contract (tool schema, additive): `ask_economics` takes null for every field of a value but `key` (`others: null`, `source: null`); a value of null is an open key; a value needs its `row` or its `source`.
- Fix (#143), contract (tool schema, additive): `build_plant(from_class=...)` builds a free plant from a class's modules, connections, size, params and fluids with the plant's added modules, connections (one at a single-connection port replaces the class's) and `optional`. A plant with `type` naming a module its class lacks is refused naming `from_class`. The process engineer's prompt says so. It had spent its 15 steps on a free plant with `thermal_storage`.

### The step-limit question keeps its shape (0.4.22.dev61)

- Contract (pinned): the backend (1.1.7) takes typed text for every question with options except the step-limit one, which it knows by options exactly `continue` and `stop` and no call id. A test pins that shape; no marker is added. The contract copy's "Answers to options" says a question with options also takes typed text, which geomind marks as typed.

### The second end-to-end run (0.4.22.dev60)

The end-to-end run again on dev59 (nemotron for every role, memory off, e2e-final3); each fix
pinned by a test with the run's inputs where it had them. No version bump in this piece.

- Fix (#132), behaviour: `patch_plant` takes a module's parameters written at the top (`d0`, `d0.well`, `degasser`), dotted (`modules.d0.well`) or inside `modules` as under `params`; a module's `type` stays in `modules`. An engineer's parameter path that `design.owners` names no prefix of belongs to the discipline of its module's gemini type (`OWNED_MODULES`, now in `tools/gemini/ownership.py`, then the type's category), so an engineer can always write its own modules; a named owner still decides. The run had 31 `not_allowed` with the owners recorded.
- Fix (#133), contract: a question with options takes typed text: text that is no option's value is the user's own answer (`validate_answer` no longer raises), and the model reads it as "The user typed this answer instead of choosing an option: ...". The step limit's question still takes `continue` or `stop` only. The shared contract's "Answers to options" (backend `422`) needs the same change. The case lead's answer after `change some` with no later question is refused once (`changes not asked`).
- Fix (#134), behaviour and new tool: `ask_economics(values, open, note)` on the case lead: each economics key with its value, catalogue row, source and the other rows; `currency`, `price_year` and `discount_rate` required in `values` or `open`. Code writes the one question; on `approve all` it sets every value with `set_case`, keeps each row in `economics.about.sources` and records a confirmed assumption `economics.<key>` with its citation. `Tool.on_answer(context, input, text)` makes the result of an answered question; a replay calls it again from the result's `answer`. The prompt: a multi-row key recommends the row of the latest year and lists the others.
- Fix (#135), behaviour: the repeat guard compares the tool and the whole input, and a failure counts once per step for both the repeat and the validation count: parallel calls of one step are sent before the model saw an error. #49's rule (the same input the error names) is gone.
- Fix (#136), behaviour: an older assistant message shows a long call input as `{}` and its outline as a line of its text; a call whose input is `{"shortened": ...}` is an error result naming the tool's arguments, no validation failure.
- Fix (#137), behaviour: a tool's question naming exactly the case paths of an earlier answered question in the run tree is not asked; its result is the earlier answer ("Not asked again: ..."), read from the root's log (`engine/questions.py`).
- Settings: `GEOMIND_MAX_OUTPUT_TOKENS=32000` for nemotron runs goes in the run's env (`.tmp/e2e-final4/env.sh`); no code default.

### What the end-to-end run showed (0.4.22.dev59)

The end-to-end run on nemotron for every role (memory off, e2e-final), each bug pinned by a test
with its recorded input.

- Fix (#124), behaviour: `Agent.answer_problem(context)`, checked before an answer (a `finish` or a text answer) is accepted; its text goes back to the model as `finish` feedback. The case lead refuses once an answer of a run that called `set_case` and left the case with no economics and asked no `ask_user` naming economics, with its step 5. Prompts: the project lead's case brief asks for the economics and leaves the questions to the case lead; the case lead follows its workflow in a delegated run too and asks with `ask_user`, never in its answer's text. The delegated case lead had read the catalogue, set no economics and asked nothing.
- Fix (#125): `list_profiles` lists a service with no return temperature as `null` instead of crashing.
- Fix (#126), behaviour: a call with an argument the tool does not have is an error result naming the tool's arguments (code `invalid_input`, `path` the unknown name, `suggestions` the real names), and no validation failure: it does not count toward "2 invalid calls in a row". `read_plant with_schema` had ended two design-lead runs.
- Fix (#127), behaviour: with the memory off, the curator is not offered (`needs_memory`) besides the memory tools, and a call of a tool the run does not offer is answered `not_allowed` without running. The support lead's prompt says to finish at once then.
- Fix (#129), behaviour: JSON text of a list whose object closed before its last key (`"reason": "x"}, "citation": null}]`) is read with that `}` deleted, as nemotron's `update_state changes` (`tests/fixtures/live/h_update_state_early_close.json`).
- Fix (#130), behaviour: `set_case` refuses a requirement on an efficiency, fraction or share (no unit) with a bound outside 0-1 (code `out_of_bounds`, "an efficiency is a fraction 0-1: 0.7, not 70"; no number of geomind's own: the fixed example only). nemotron wrote `pump_efficiency` 70.
- Fix (#131), behaviour: `search_rag`'s "already searched in this run" note follows the run's conversation in call order, so a resumed run and `geomind replay` give the note the live run gave; the run tree's in-process set of searches is gone. A replay had failed on two calls of one step with the same words.
- #128, no change of behaviour: the suggestions of `run.finished` keep one step from outside the stage's own, as before; `finish`'s description says so. gemini request 32 (`site.air.pressure` from the site's elevation) in plan.md.

### The case team, fifth round (0.4.22.dev58)

The case team after the A4 rerun on both models; each bug pinned by a test.

- Fix (#121), prompt: the case lead works by a numbered workflow; economics are its required step 5 once the case is accepted: the cost catalogue read once, ONE `ask_user` question listing every economics value with its catalogue row (`id`, source, year, link, status; rows with different values offered there), then `set_case(economics=...)`; the checklist and the stop rule name them. nemotron had set the project case and no economics.
- Fix (#122), behaviour: `read_rag` on a page this run already read, `force` or not, returns the note "already read at step N; its text is in your context; call set_case next" (`work from it` for an agent without `set_case`), with `already_read` (each read with its `step`), `start` and `total`; after a compaction since the read, the note names `read_stored` and `force` reads the page again, as before. DeepSeek had read the same pages 48 times and never set a case.
- Evals (#123), contract: the `question` criterion takes `contains_any`, a list of texts of which one must be in a question (`contains` stays; one of the two is required); `geomind/schemas/eval_task.json` regenerated. The flawed case task accepts any name of its count flaw.
- Evals: the `sourced` criterion takes a read float written with noise in its last digits (relative 1e-12), as nemotron wrote 37.50773379868328 for 37.507733798683276.

### The case team, fourth round (0.4.22.dev57)

The case team after the A3 rerun on both models; each bug pinned by a test.

- Fix (#117), behaviour: JSON text of an object or array with a stray closing bracket in the middle (`json`'s "Extra data" before a `,`, or "Expecting ',' delimiter" at a `}` or `]` that closes nothing open) is read with that bracket deleted, up to three times, and only when no closing bracket is made up; the schema's type is still checked (`parsed_json`). nemotron's `set_case` (`..."°C"}}}}, "requirements"`) and `update_state` (`}}]}`) inputs had ended two runs; the recorded strings are the test fixtures (`tests/fixtures/live/a4_stray_brackets.json`).
- Fix (#118), behaviour: `set_case` maps unit names as sources write them to gemini's name of the same unit, no factor: `m³` `m3`, `kg/m³` `kg/m3`, `Nm³/m³` `Nm3/m3`, `m³/h` `m3/h`, `mPa·s` `mPa.s`, `MWth` and `MWcool` `MW`, where the key's units hold the name (a requirement's unit: where gemini knows it). Contract: each is a `converted` entry with the reason `unit name`.
- Fix (#119), prompt: a flaw of a loaded case is always a question with `ask_user` before the case lead finishes, never only a line of its answer (do/don't from nemotron's flawed run); the checklist says so too.
- Fix (#120), behaviour: `read_rag`'s `already_read` note for a page this run read no longer says "after a compaction, read_stored a reference" and shows no reference while no compaction happened since the read: DeepSeek's project run called `read_stored` 16 times on pages in its conversation. After a compaction the note names `read_stored` and the reference.

### The case team again (0.4.22.dev56)

The Track A rerun on dev51 on both models; each bug pinned by a test.

- Fix (#68): `read_case` and the other case tools without a case in a project that has a `case.json` say so in their `no_case` error: "the project has a case file: set_case(source='project') loads it". nemotron had read `no_case` as "the project has no case" and raised none of its flaws.
- Fix (#69), prompt: the case lead sends the SAME full `set_case` again after `case_incomplete` or a refused full call, fixed where it names, never files alone; never calls the geoscientist after `already_asked`; writes file names as `list_files` gives them (case-sensitive).
- Fix (#115), behaviour, reversible: `set_case` maps a `site.ground.gradient` in `degC/km`, `°C/km` or `C/km` to `K/km` (`/m` to `K/m`), the same number, and turns a value in `%` or `mol%` on `site.fluid.dissolved_gas.*` or `utilities.gas.composition.*` into the fraction (value, range and uncertainty / 100) (`geomind/tools/gemini/unit_bridge.py`). Contract: `set_case`'s result gains `converted`, `[{path, from: {value, unit}, to: {value, unit}, reason}]`, when it mapped or converted a value. To be removed when gemini requests 15 and 31 land; `test_no_unit_math` now knows the percent factor and allowlists that one line. Prompt: units as the source writes them, each `converted` entry in the one confirmation question; `search_rag` for each missing value and the cost catalogue, always, before that question.
- Evals (#116): `Outcome.partial` marks the answer the engine wrote from the record at a limit (stop reason `step_limit` or `denied`); `sourced` leaves it out, so the cap's numbers are no longer flagged.

### The project team on both models (0.4.22.dev55)

Rounds E1 and E2: the coordinator, the reviewer, the explainer and the project lead, each alone (the lead's teams scripted), live on DeepSeek. Each bug is pinned by a test.

- Prompts: the coordinator's prompt ends with every `Route` option and what it means (`ROUTE_OPTIONS`, kept equal to `Route` by a test), and says when `design` and `compare` apply. The reviewer's ends with gemini's verdict: each kind of reason, read from `gm.evaluate.verdict`'s docstring, and the shape of `failures`. The reviewer's and the explainer's end with gemini's metrics from `gm.evaluate.metrics()` (`geomind/tools/gemini/verdict_text.py`). Each of the four has do and don't examples from real failures.
- Fix (#105): the metrics section said `compute_kpis` gives the costs; it gives gemini's totals and report metrics, and the costs (`capex`, `annualised_cost`, `lcoh`, ...) come from `estimate_costs`. The explainer had asked `compute_kpis` for `annualised_cost`.
- Fix (#106): the reviewer and the explainer read their results again and again as they shrank (17 `read_stored`, 42 `read_result`, the explainer's whole input set three times): the reviewer keeps them for a few turns (`Tool.kept`), the explainer for the run.
- Fix (#107): `read_case(section=...)` of a section gemini knows but the case has not set says it is unset (`unknown_name`, with the sections the case has), instead of "expected one of about, ...; did you mean 'about'?".
- Fix (#108): the reviewer's prompt says the problem state is a message of the conversation; it had tried `read_stored("state")`.
- Fix (#109): the project lead skips the case step when the state holds an accepted case, and stops briefing a team that gave the same unusable answer twice.
- Fix (#110): the explainer converted plant values (`1500000.0 W/K` written as `1.5 MW/K`): capacities come from `compute_kpis`'s `capacities`, and `read_plant`'s values are quoted in their own units.
- Fix (#111): the project lead asked the user for a case value with an example number of its own (`e.g. 70`): a case value is the case lead's to ask, and a question offers no value.
- Fix (#112), behaviour: a tool input that the schema wants as an array or an object and that comes as JSON text of that type (`"[{...}]"`) is decoded before validation (`Tool.validate`, `decoded_strings`). nemotron sent `update_state`'s `changes` so twice, and the run stopped; once with one `}` too many at the end, which is taken as the value when only closing brackets follow it. Any other string still fails.
- Evals: an `answer` criterion (`pattern`, `present`) checks an answer's words, such as a route or a verdict.
### The design team on both models (0.4.22.dev54)

Rounds D1 to D3 had started the engineers from a class plant given by its header alone, so gemini listed about a hundred inner values as missing and every engineer ran out of budget inventing them. The class's whole project file checks clean against the case.

- Prompts: each design agent's appendix is made from gemini when its prompt renders (`geomind/agents/design/reference.py`): the plant file's keys and gemini's `describe()` of the modules the engineer owns (`OWNED_MODULES`, with parameters, units, list forms and ports); the plant classes with their summary and children for the process engineer; every module's ports for the integration engineer. A test fails when gemini drops or renames a module.
- Prompts: the reservoir, well and energy engineers work in four steps (read the case and the plant together, decide, one `patch_plant` with every change, stop when no issue names their own path), answer in at most twelve lines, and carry do/don't examples from D1 to D3 (a case value is no plant value; a stored name is not reused; `evaluate_module` is not run on a whole `Doublet`).
- Fix (#76): `evaluate_module` checks parameter and control names before gemini: a control given as a parameter (`temperature_setpoint` of a heat pump) raised a bare `KeyError` in gemini, seen as `internal`; it is `invalid_input` now, saying to give it in `controls`, and an unknown name gets close matches.
- Fix (#77): the process engineer builds from the project's plant file of the chosen class (`read_plant(project_plant=...)`), which holds every value; `read_plant(plant_class=...)` gives a header and modules only.
- Docs: `patch_plant` takes every value of one module or several in one patch.
- Fix (#81): the integration engineer finishes without a patch when gemini's issues name no connection, port, fluid or boundary, and never describes a module for its ports.
- Fix (#80): the engineers copy each value with the unit its source writes it in; both models had shown 320.15 K as 47 degC.
- Fix (#79): `evaluate_module` names each required stream inlet a call leaves out, with the form of its fluid, `T`, `p` and `m_dot`; the energy engineer evaluates only a machine it changes.
- Fix (#78): the design lead records `design.reference` and `design.result` before every `finish`, also for a handed design it only checked; nemotron finished with the verdict in its answer alone.
### Evals: a delegate that failed (0.4.22.dev53)

- Evals: the `tool` criterion has `succeeded` (default false, the behaviour before): with `succeeded: true` at least one call of the tool must return no error, so a lead's task no longer passes when its delegate's nested run failed (Track C, nemotron). `Outcome.succeeded` lists the tools whose result was not an error, in order, old names mapped as in `Outcome.tools`. Schema `eval_task.json` (and the agents snapshot) gain the field.
- Evals: the `sourced` criterion takes a read number written with up to 8 decimals (0.0833333 for 0.08333333333); it took 4.

### The analysis team alone (0.4.22.dev52)

Round C1 (Track C): the analysis lead and the economist alone, two tasks each, on the C1 case and the D-round design (`HackathonPlant` on it), live (DeepSeek), 0.028 USD: 2 of 4 passed, each number checked against gemini's own.

- Prompts: the analysis lead and the economist carry a gemini reference made when the prompt renders (`geomind/agents/analysis/reference.py`): every metric of `gm.evaluate.metrics()` with its title, display unit and whether a study may minimise it, and the economics keys with units and meanings. A test pins gemini's objectives (`annualised_cost`, `lcts`, `lcoh`, `lcoc`, `co2`) and checks that every metric the prompts cite is gemini's.
- Prompts: the economist has `read_case` (its prompt sent it to the case's economics without the tool), names metrics as gemini does, reports a breakdown and a comparison as gemini gives them (ranks and both values, never a difference, a share or a sum it worked out), and reports a missing price with its economics path. The analysis lead no longer chooses a time zone alone, and gives gemini's values side by side instead of a share.
- Fix (#85): the economist runs uncertainty and sensitivity only when the task asks for them.
- Fix (#87): `Tool.validate` reads a list or an object sent as its JSON text, as nemotron sends `update_state`'s `changes`; any other string stays for the schema to judge.
- Fix (#88): the analysis reference says `compute_kpis` has names of its own (gemini's totals and one result's report): call it without `names`; costs come from `estimate_costs`.
- Fix (#89): a list or an object whose JSON text lacks only its closing brackets is read (nemotron's `changes` without its final `]`), and `"None"` or `"null"` is null where the schema takes a null.
- Fix (#90): the analysis reference names the metrics a study reads (the objectives and `heating_coverage`, `cooling_coverage`, `cop`, `peak_heat`, `peak_cold`), never `capex` or `opex`; a test pins them to gemini's private list (gemini request 26).
- Fix (#86), evals: the `sourced` criterion reads the problem state's `Case:` line. Evals: the `number` criterion reads a thousands separator (`111,667.68 MWh`).
### Next-step suggestions (0.4.22.dev51)

- Contract (addition): `run.finished` has `suggestions?`, the next steps `[{label, message}]`: one to three, on the root run that ended `done` only; `label` at most 40 characters, `message` (what the app sends as the user's message when one is picked) at most 200; in the user's language (Persian when the user's last message is in Arabic script, else English). A nested, waiting, failed or cancelled run has none, an empty list is left out, and a log before this has none; a replay compares the answer as before and makes the same list again.
- Code picks the stage from the problem state and its steps (`geomind/tools/suggestions.py`): no case → build the case from the files (with files only), by questions, or which files are needed; a case without `design.reference` → design a plant, check the case and its unsourced values, compare plant options; a plant without a result → optimise, economics, check the design; a result → report, sensitivity, explain.
- The project lead's `finish` takes `suggestions` `[{step, label, message}]` to reword, reorder or replace one; each must name one of the app's twelve steps, fit the limits and the user's language, and at most one may come from outside the stage, else the stage's own list is used. `Finish` has `suggestions`.
- API (addition): `gd.suggest(problem, files, project=None)` gives the list of an empty chat before its first message: sync, no model call, in the language of the chat's goal (English when it has none).
- Contract v4 (addition): the optional `Workspace.project_state(project_id)` returns `{case, plant, study, results, report: {state, label}, case_version, plant_version, study_case_version, case_changed_after_study}` (states `empty`, `incomplete`, `ready`, `running`, `done`); when it answers, the stage follows the project, not the chat: case not done → build it; plant neither done nor ready → design; study or results not done → optimise, economics, check (a running study: wait or explain, no new study); report not done → report, explain, sensitivity; all done → more studies (uncertainty, structure search, another objective, another case). A stale study puts "run the study again" first, an incomplete item "finish the <label>"; a new chat in a project with a case never builds one. `FileWorkspace.project_state` reads it from the project folder (`case.json`, `plants/`, `studies/`, `results/`, `report/`; stale when `case.json` is newer than the newest study). Without the method or with `None`, the chat's problem state decides, as above.
- Contract v5 (addition): `RunResult` has `suggestions?`, the same `[{label, message}]` as the run's `run.finished` event: on a root run that ended `done` only, `None` on a nested, waiting, failed or cancelled run.
### Case fields from gemini's code (0.4.22.dev51)

- The seven case fields gemini's schema leaves undescribed (`about`, `initial_state`, `economics.about`, `demand.{heating,cooling}.{minimum,maximum}_return_temperature`) read with a meaning taken from gemini 0.6.1's code, each naming its source; `heating.maximum_return_temperature` and `cooling.minimum_return_temperature` say gemini does not use them. `undescribed()` no longer lists them (plan.md, gemini request 22).
### Model-agnostic tool inputs (0.4.22.dev51)

- Fix (#67): on `nvidia/nemotron-3.5-super-vl:free` the case lead sent `set_case`'s `changes` as its JSON text (`'{"format": 1, ...}'`), was refused twice and the run ended; `Tool.validate` now reads a string as JSON for a parameter whose schema takes an object or an array and no string, when the text gives that type. Any other string is refused as before; a string parameter keeps its string. Every tool, the hand-made ones too.

### The support team alone (0.4.22.dev50)

Rounds D0 to D3: the support lead, the summarizer and the curator alone, nine tasks, live (DeepSeek, 0.04 USD; nemotron free); the curator on a scratch memory. Each bug is pinned by a test.

- Fix (#95): `search_memory` gave the curator only its own role's lessons, so it could not see a case lead's lesson and wrote it again; the curator now reads every role's lessons and the user's facts.
- Contract (addition): `write_lesson` refuses a `role` that is no agent's snake name or `all` (`unknown_name`, with a close match): a lesson for `designlead` reached no agent.
- Fix (#96): the curator wrote "the GEMINI brief" into a lesson; its prompt now says every field of an entry (`kind`, `role`, `text`, `source`, `id`), lists the roles from the agents themselves, and gives do and don't examples from the runs.
- Fix (#97): the support lead was told to hand the summarizer references, which the summarizer, with no tools, cannot read; it now hands the material itself, whole.
- Fix (#98): the summarizer spent 16,000 output tokens reasoning before a 2.7k-character handover and wrote nothing; it runs at temperature 0 and writes in one pass. Its prompt covers a handover as well as a compaction, and keeps every number, source, id and open question as written.
- Fix (#99): on nemotron, the curator called the memory tools it was not offered when the memory was off; its prompt says the memory is off when those tools are not offered.
- Round F ran every task once on DeepSeek and once on `nvidia/nemotron-3.5-super-vl:free`: 9 of 9 on both (plan.md, Model comparison).

### The case lead asks its geoscientist once (0.4.22.dev49)

The fresh project case on DeepSeek (0.086 USD, 31 steps, 1423 s) set no case: the case lead began its work again four times, read the brief again each time and asked its geoscientist six times, until its steps ran out.

- Contract (addition): `Delegate(..., once=True)` runs its agent at most once per run; a second call is the error `already_asked`, whose message says the findings are in the conversation. The case lead's geoscientist is such a delegate.

### The case lead chooses among the catalogue's rows (0.4.22.dev48)

Sahand's cost catalogue now has 133 rows (61 verified, 53 secondary, 19 placeholder), several for many keys.

- Prompts: the case lead takes a sourced row over a placeholder and a verified one over a secondary; rows left with different values go into one question for all such keys, each with its 2015 value, unit, source, year and link. A row whose unit the key does not accept (`describe_case`) never goes in and is listed; a basis word is no other unit (`EUR/W heat` is `EUR/W`). It reads the catalogue's `year` and `url` columns for the citation.
- Data: the catalogue's rows whose unit gemini's key does not accept, listed for Sahand: `capex.ice_storage` (EUR/MWh cold; the key takes EUR/m3), `capex.heat_exchanger` (EUR/W; EUR/(W/K)), one `capex.pipe` row (EUR/MW/m; EUR/m), `capex.production_pump` (EUR; EUR/W), `opex.fixed.heat_pump` and `opex.fixed.pipe` (EUR/MW/yr, EUR/MW/km/yr; %/yr), `revenue.subsidy.amount` (EUR/MWh; EUR/yr). Paths that are no economics key: `emissions.CO2.electricity` (the case's `utilities.electricity.co2_intensity`), `opex.chemical`, `opex.waste_disposal` (gemini: `opex.variable.waste_disposal`), `opex.variable.chp`, `opex.variable.corrosion_inhibitor`, `opex.variable.scale_inhibitor`.

### Shared rules for every agent, gemini's module reference, and set_case loads the files the case names (0.4.22.dev47)

- Prompts: every role prompt ends with `prompts/shared/rules.md`, said once for all 17 roles: the source order (user, files, knowledge base, MCP, then ask), citations, the user's confirmation of a value no file gave, no defaults, units and physics left to gemini, and applying an error's fix.
- Prompts: `module_reference(*names)` and `modules_of(*categories)` (`geomind/tools/gemini/skeleton.py`) give gemini's own `describe()` of modules as prompt text, made when the prompt renders, for an agent's appendix. A test checks that every module or plant class a prompt names in backticks is one of gemini's.
- Behaviour (#65 again): `set_case` loads every project file a series of `changes` names, without `files`. The case lead of the project run still sent the files alone three times and stopped; `files` alone on no case says so.

### The design team alone (0.4.22.dev46)

Rounds D1 and D2: each design agent alone on the C1 case, live (DeepSeek). Each bug is pinned by a test.

- Fix (#70): an input whose string holds tool-call markup (`</parameter`, `</invoke`, `function_calls`) is refused before the tool runs, `invalid_input` with the value before the markup as its suggestion; DeepSeek had sent a garbled plant name three times alike.
- Fix (#71), contract (addition): `read_profile` gives `summary`: `peak` and `minimum` `{value, time}`, `mean`, `energy` `{value, unit: "MWh"}` and `unit`, computed by code over the window. `Tool.kept()` returns a copy whose results stay whole for a few turns; the design engineers keep `read_case`, `read_plant` and `describe_module` so, and read each once. They had read the case up to 16 times.
- Fix (#72): the design lead records a design handed to it complete, once checked, as `design.reference` and `design.result`.
- Fix (#73): the process engineer compares plants with `list_plants` and reads only the one it chooses, in one call.
- Fix (#75): a markup slip is an error result but no validation failure, so two in a row no longer end the run; a lone `</` or a leading `">` counts as markup; `finish`, `ask_user`, `update_state` and `write_lesson`, whose inputs are prose, are not checked.
- Fix (#74): the well engineer's prompt gives the form of a well path's section lists, `{"value": [..], "unit": "m"}`; gemini describes them as numbers (gemini request 14).

### What the second Track A round showed (0.4.22.dev45)

With the provider pinned to DeepSeek the six case tasks cost 0.035 USD instead of 0.112, and from_files 15 model calls instead of 39; it stopped on #65.

- Fix (#65): after a call that named data files it did not pass, the retry said `changes=<the same changes>`; the case lead sent the files alone three times and the run stopped. The retry now says to send the files with everything else of the call, since a rejected call stores nothing, and `set_case` with files alone on a chat without a case says they go with the changes that name them (still `case_incomplete`, with the skeleton).
- Fix (#66): a wrong unit whose quantity has two words (`temperature gradient`) was read as its first word, so `degC/km` got `{'unit': 'degC'}` and the units of temperature; the whole quantity is read now (`K/km, K/m`).
- Evals: the `sourced` criterion reads a number after a JSON line break (`\n3.1`), takes a read number written with fewer decimals (34.64 for 34.6364) and a space as a thousands separator (`111 667.7`).

### The case team re-reads nothing (0.4.22.dev44)

The first live round after dev43 still spent 10 `read_stored` calls in from_files: on pages the case lead read before its geoscientist, on search results, on `describe_case` answers and on the geoscientist's findings, each shrunk to a reference one step after it came.

- Behaviour: `read_rag` counts only this run's reads as already read. A nested run (a delegate, a design round) reads a page another run read itself, once, instead of getting a note and spending a `read_stored` call.
- Behaviour: `search_rag` keeps its results whole for `compaction_keep_turns` turns, `describe_case` for the run, and the case lead keeps its geoscientist's findings for the run.
- Evals: the `sourced` criterion skips numbers joined to a word (`A14`, `CO2`) and list markers (`13.`).

### The case team: fewer calls, fewer tokens (0.4.22.dev43)

The case lead's from_files run took 39 model calls and 1.15M input tokens. It read the brief again four times with `read_stored` once the page shrank after six turns, read the 40k-character cost catalogue three times, asked for the same missing values three times, and rounded catalogue prices.

- Contract (addition): `Tool.keeps_result` may be `"run"`: the result stays whole in the history for the whole run (until compaction). `read_rag` keeps its pages so; other kept tools (`read_plant`, `read_stored`) keep the window of `compaction_keep_turns`. The `already_read` note of a page this run read says it is in the conversation, even when it was stored.
- Contract (addition): `read_rag(columns=[...])` reads only those columns of a CSV or TSV, in that order; the result names `columns`. A column the table lacks is `unknown_name` with the header; a file that is no table is refused. The cost catalogue read by id, path, 2015 price, unit, status, source and page is 11.6k characters instead of 40k.
- Contract (addition): tool `describe_case(path)` returns `keys`, the lines of the case or economics keys under a dotted path with their units, meanings and sources (`requirements` also gives what each option means). An unknown path is `unknown_name`.
- The case lead and the geoscientist carry the compact key tree (`trees("case_compact")`, 8.2k characters instead of 13.5k): each key, its form and its source tag (`[brief/report]`, `[derived]`), the requirement options, and no unit lists or meanings. `set_case` names the accepted units of a wrong one, and `describe_case` gives the meanings.
- Prompts: independent tools run in one step; a page once read is never read again; the case is set in as few `set_case` calls as possible; the cost catalogue is read once by its columns; numbers are copied digit for digit; the user's answer is final, so a value left open is never asked for again.

### Verb-first RAG tools and three MCP tools (0.4.22.dev42)

Sahand's naming: a tool's name starts with its verb.

- Contract (rename): `rag_read` is `read_rag` and `rag_search` is `search_rag`. Old logs and recordings still replay: `RENAMED_TOOLS` maps `rag_read`, `rag_search`, `search_knowledge` (and the older `read_document`, `search_documents`) to the new names.
- Contract (removal): `search_knowledge` is gone. `search_rag` is one search over the project's documents and files and the knowledge base. Each match has `scope` (`project` or `knowledge`), `text`, `score` and `citation`: `{document, title}` for a project document, `{file, page}` for a passage of a project file, and `{document, title, page}` for a knowledge passage, whose `name` is `knowledge/<document>` for `read_rag`. The best of each scope come in turn, because their scores come from different rankings. With neither a project nor a knowledge base it answers `not_allowed`. Its no-match note now says to try MCP and then ask the user for a value of the case, and to choose and record an assumption only for a design choice.
- Contract (MCP, replaces `<server>__<tool>`): every agent that has tools is offered three fixed tools when the run has a server that answered. `list_mcp(server?)` returns `tools` `[{server, name, description, read_only, input_schema}]`. `read_mcp(server, tool, arguments)` calls a read-only tool and answers `not_read_only` for any other. `call_mcp(server, tool, arguments)` calls any tool, and a tool that is not read-only asks for approval (`request` kind `approval`) through the new `Tool.for_call(session, input)`. Kept: `tool.started` and `tool.finished` carry `mcp` (the `server` input); header values are never logged, stored, echoed or replayed; `GEOMIND_MCP_TIMEOUT` is required when a server is given; `mcp_unavailable` answers a run without a server or a failing one; an unknown server or tool is `unknown_name`. `Engine.mcp_tools` is now `Engine.mcp_servers`. A log with `<server>__<tool>` calls still replays (tested on a dev41 log).
- Prompts: the shared `KNOWLEDGE` and `MCP` sections name the new tools; the case lead and the geoscientist search the knowledge base with `search_rag`, then a server through `read_mcp`, before they ask.
- Evals: `Outcome.tools` holds the new names, also for old recordings.

### A missing value is searched before it is asked for (0.4.22.dev41)

Sahand's rule: a value the user's files lack comes from the knowledge base, then from an MCP tool, and only then from the user; the user confirms what was found, with its source. Prices come from the knowledge base's cost catalogue.

- Prompts: the case lead takes each value from the first of: the user, the project's files, the knowledge base (cited by document and page, or a table's row `id`), an MCP tool (cited by server, tool and time), and only then asks the user for the value itself. Economics are built from `knowledge/cost-sources.csv`, one row per key by its `path` column, in its `value_2015` prices; a `placeholder` row is named as having no source. A key that takes a constant or a series (the outside air) may take a cited constant, said to be constant.
- Prompts: the geoscientist searches the knowledge base, then MCP, for a quantity the reports lack, as an `estimated` proposal with its source, before it calls the quantity missing; an MCP value's `source.file` is `<server>__<tool>`.
- Evals: a `before` criterion (`tool`, `then`) fails when `then` is called before any call of `tool`.

### Agents write no number they worked out (0.4.22.dev40)

Round C2 of the case team passed 6 of 6, but in one question the case lead worked out a room dew point (14.6 degC) itself. Replaying C2 with the new eval criterion found more: a reservoir temperature worked out from the gradient, a GWP recalled from memory, an end date and a step count worked out by hand.

- Fix (#64): the case lead's prompt forbids any number it worked out or knows from memory, in its questions, notes and answer as in the case; a derived number is left to gemini or asked for.
- Contract (addition): `rag_read`'s `table` of a CSV or TSV has `last_row` and `span` (`start`, `end` exclusive, one step after the last row, and `step` as a case writes it, `{value, unit}`), or `span: null` when the first column is not evenly spaced times. The case lead copies the case's time from it.
- Evals: a `sourced` criterion (`small`: the largest whole number that needs no source) fails when the answer or a question holds a number that no message the agent was sent holds; the agent's own turns and its problem state do not count. `Outcome.read` holds that text.

### What the case team alone showed (0.4.22.dev39)

Round C1: the case lead and the geoscientist alone, six tasks live (DeepSeek, 0.062 USD): 6 of 6 passed. The case lead caught every flaw of a flawed case file (a duration stored as a count, a chilled-water return colder than its supply, a span one day short, a derived temperature set by hand) and asked; it invented no value. Each bug is pinned by a test.

- Fix (#61): `FileWorkspace.files` and `file` list and read the data files `case.json` names beside it, not only `files/`; the case lead had said the project held no files while its case named two demand files.
- Fix (#62): the case lead reads the case before and after a change and reports the value before as the case showed it; it had said a cap "was 200" where the case held 300.
- Fix (#63): an eval task's workspace has the knowledge base of `GEOMIND_KNOWLEDGE_DIR`, as the command line's has; the case lead had found no cost catalogue.
- Evals: an answer rule may be `only_options`, kept off questions that ask for typed text.

### The case team knows the case format (0.4.22.dev38)

- The case's key tree (`case_tree`, in the case lead's and the geoscientist's prompts) says after each key what it means and where its value comes from (brief, data, report, user, economics), marks the keys gemini derives (leave them unset), and explains every option of the requirements (`on`, `quantity`, `over`, `when`), with how operating days and counts are written (`geomind/tools/gemini/fields.py`). gemini's schema has no descriptions; the texts are geomind's, from gemini's docstrings; `undescribed()` lists the fields gemini describes nowhere. About 13,500 characters, in the cached prefix.
- The case lead's prompt holds the case format's facts and a checklist before it hands over: `time.end` exclusive and the span equal to the data; demand files (time column, unit, rows, time zone); supply and return sides; durations never counts; the brine's gas never the grid gas; flaws of an existing case asked about, never corrected silently; a change of one value changes nothing else.
- Evals: a task's `answers` may be rules `{match, answer}`: the first rule whose pattern is in the question answers it; a question no rule covers is answered as a user who does not know (an option that leaves the value open, or `unknown`) and listed in the outcome's `unanswered`. `eval_task.json` gains the rule form (additive).

### MCP: the tools of the servers a run is given (0.4.22.dev37)

**Contract changes for the backend (contract v2 and v3 names):**

- Optional `Workspace.mcp(project_id) -> [{name, url, transport: http|sse, headers}]`: the project's MCP servers. `name` matches `[a-z0-9_-]{1,32}`; header values are secrets geomind never logs, stores, shows in an error or replays (they join the log's secrets).
- New public module `gd.mcp`: `list_tools(server) -> [{name, description, read_only}]` (sync; `read_only` from `readOnlyHint`, false when missing), `McpError` with `.code` `unreachable`, `auth_refused` or `bad_response`, `Server`, `McpClient`, `servers_from_text`.
- In a run, each server's tools are offered to every agent that has tools, named `<server>__<tool>`; a read-only tool has the effect `read`, any other `external`, so the `ask` mode asks for approval (request kind `approval`). Each result carries its origin `{server, tool, time}`.
- `tool.started` and `tool.finished` have a new optional field `mcp`, the server's name (`null` for a geomind tool); public events and `events.json` gain it (additive).
- New tool error code `mcp_unavailable` (a server that failed during a call). A server that fails while its tools are listed is left out, with an `error` event naming it.
- The command line needs `GEOMIND_MCP_SERVERS` (a JSON list, `[]` for none) for a run with a project and `GEOMIND_MCP_TIMEOUT` (seconds, a plain number) when it names a server; no defaults.
- A replay reuses the recorded answers and never reaches a server.
- Agents read a shared prompt section on connected servers: cite a server's value with its origin; it enters the case or the plant only after the user confirms it.

### Documents are "rag" (contract v3 names, 0.4.22.dev36)

**Contract changes for the backend (renames; the backend keeps its old methods until this release):**

- `Workspace.documents(project_id, query)` is `Workspace.rag(project_id, query)`. `files`, `file`, `memory` and the `knowledge_*` methods are unchanged.
- The tool `search_documents` is `rag_search`, and `read_document` is `rag_read` (it also reads `knowledge/<name>`): tool calls, `tool.started`/`tool.finished` and the runlog name the new ones.
- An older log or recording that names `read_document` or `search_documents` still replays and resumes: the engine finds the renamed tool by its old name (`RENAMED_TOOLS`).
- Prompts and docs use the new names.

### Knowledge is a document base (retrieval); memory is experience only (0.4.22.dev35)

Contract v2 with the backend: knowledge and memory are never mixed.

**Contract changes for the backend:**

- Optional `Workspace.knowledge_search(query) -> [{id, document, title, page, text, score}]`, `knowledge_files() -> [{name, size, media_type}]`, `knowledge_file(name) -> bytes | None`: the shared knowledge base. Without them, or with no document, `search_knowledge` answers the new tool error code `knowledge_unavailable` and the tool is not offered.
- `search_knowledge(query)` now searches the knowledge base and returns `{passages}`, each with its citation; `read_document` reads a knowledge document as `knowledge/<name>`. A value taken from knowledge is cited and confirmed by the user like any value no project file gives.
- The command line needs `GEOMIND_KNOWLEDGE_DIR` (a folder of documents, `FolderKnowledge`) for a run with a project, no default; `.env` points it at `data/knowledge`, where the cost catalogue `cost-sources.csv` is now a document.
- Memory keeps only `experience`: designs that passed (written by code, with `origin` `{run, source: code}` and `project_id`) and the curator's lessons and the user's facts (with `origin` and `project_id`). **Removed:** the memory's `knowledge` section, `write_memory`, `read_knowledge`, `checked_knowledge`, `catalogue_entries`, `search_knowledge` of `geomind.stores.memory`, and `geomind memory seed`. `search_memory()` takes no argument (was `query, section`) and `read_memory(id)` no section.
- The reviewer and the explainer read the knowledge base, never experience; user preferences stay in the problem state.
- Document text extraction moved to `geomind/stores/documents.py`, shared by the project's files and the knowledge base.

### A superstructure searched by gemini's genetic algorithm (0.4.22.dev34)

**Contract changes for the backend:** a new tool `evolve_structure` (design lead) and four new required settings, no default: `GEOMIND_EVOLVE_EVALUATIONS`, `GEOMIND_EVOLVE_POPULATION`, `GEOMIND_EVOLVE_SEED`, `GEOMIND_EVOLVE_POLISH` (a live run lacking one is refused; the tool names any unset one). A study `study/<name>` of `tool: evolve_structure` and gemini's `method: evolve` (`study.recorded` as any study); its front designs are stored as `design/<name>_<n>`. The plant file's `optional` and `choices` (gemini 0.6.1) pass through `build_plant` and `patch_plant` unchanged.

- The process engineer builds a superstructure when more than one way to meet a service is sensible: `optional` modules and `choices` `{choice: {group: [modules]}}`, each option with its reason; `patch_plant` gives both keys to the process engineer. The integration engineer wires every option as if on; the reservoir, well and energy engineers fill every option they own.
- `evolve_structure(design, objectives, name)` runs `gm.study.evolve` (the settings above) and returns the front compactly: each design's reference, `structure`, `metrics`, `feasible` and `reason`, then `best`, `evaluations`, `invalid` and the study key. The objectives come from the case or the brief, never the agent. The design lead takes the chosen design on to size, simulate and check, and the reviewer checks it from scratch.
- With a superstructure there is no design per family; the project lead's `comparison` is for designs the user names.

### A flat layout for every agent (0.4.22.dev33)

**Contract changes for the backend (module paths; `gd.agents.<Class>` is unchanged):**

- Each agent is `geomind/agents/<team>/<name>.py` (was `geomind/agents/<team>/<name>/agent.py`): `agents/analysis/lead.py`, `analysis/economist.py`, `case/lead.py`, `case/geoscientist.py`, `design/lead.py`, `design/process.py`, `design/integration.py`, `design/reservoir.py`, `design/well.py`, `design/energy.py`, `project/lead.py`, `project/coordinator.py`, `project/reviewer.py`, `project/explainer.py`, `support/lead.py`, `support/curator.py`, `support/summarizer.py`.
- Each prompt is `geomind/prompts/<team>/<name>.md` (was `geomind/agents/<team>/<name>/prompt.md`); `Prompt("<team>/<name>")` is unchanged. Skills stay in `geomind/prompts/skills/`.
- The project lead's other modules are siblings: `agents/project/review.py` (was `project/lead/review.py`), `agents/project/drivers.py` (`DesignDriver`, was `project/lead/design_driver.py`) and `agents/project/comparison.py` (`CompareDriver`, `ComparisonDriver`, was `project/lead/comparison_driver.py`).
- Tests mirror it: `tests/unit/agents/<team>/test_<name>.py`.
- A log naming an old class path (`geomind.agents.<team>.<name>.agent:<Class>`, `geomind.agents.project.lead.design_driver:DesignDriver`, ...) still resumes and replays (`RENAMED_CLASSES`).

### gemini 0.6.1

- geomind runs on the gemini 0.6.1 release wheel (`requirements/gemini.txt`, sha256 `fca120290b87ac87a1dd4aca4ab85a725c6459986c5b8ccd53884eeae8d45655`; `[tool.uv.sources]`). 0.6.1 is additive: optional modules and choice groups of a plant, its structures, and `gm.study.evolve`; nothing breaks, and every test passes unchanged. The range stays `>=0.6,<0.7`.

### What the second end-to-end run showed (0.4.22.dev32)

Run E2: the case lead found two flaws of the test project's own `case.json` (the 330 operating days stored as a count of 330 doublets; a cooling return colder than its supply) and asked instead of guessing. Each bug is pinned by a test.

**Contract change for the backend:** `read_profile` returns two more keys, `case_time` (the case's start, end and step, `end_is: "exclusive"`, `steps`) and `file` (`{name, rows, first, last}` of the data file the series comes from, or `None`).

- Fix (#60): `read_profile` showed the case's demand clipped to the case's time with no word of it, so a year ending at an exclusive 31 Dec read as a file of 364 values; it now shows the window and the file's own rows beside the series.
- Fix (#58): the case lead knows `time.end` is exclusive and that a span that differs from the data's rows is the span's fault, never the data's; it had proposed to cut 31 Dec.
- Fix (#59): `ask_user` says that with options the answer is exactly one option's value, and that a typed answer needs a question without options; the case lead had asked for a path and a value with options three times.

### Cost cuts from the first end-to-end run (0.4.22.dev31)

E1 spent its 1 USD cap before a verified design: 7.0M input tokens (3.9M cached) over about 400 model calls, 119 of 334 tool calls failing. Measured offline on its log.

**Contract changes for the backend:** a new required setting `GEOMIND_ENGINEER_MAX_STEPS` (required for a live run, no default): the steps of one engineer's run, at which it ends with what it has instead of asking the user to continue.

- Fix (#56): the process engineer recorded owners as `params.d0.reservoir`, and the ownership check looked up `d0.reservoir...`: every engineer's patch was refused as owned by no discipline (61 refusals in the last segment, 21 on one path). A prefix with or without `params.` is found.
- Fix (#57): `build_plant` reads a `format` given as text (`"1"`) as its number; it had been refused as an old header four times.
- `Delegate(..., steps=SETTING)`: a nested run with its own step limit that ends at it and answers from what it has (`step_limit`), with no question; the design team's delegates use `engineer_max_steps`. `RunSession.delegate` and `run_child` take `max_steps`.
- The design lead designs one family unless the request or its brief asks to compare (then 2 to 6); the project lead uses `comparison` only when the request compares. E1 designed two families for a request that compared nothing.
- Tool descriptions keep the whole docstring (#50): the design lead's tools are about 7,400 tokens, sent from the cache; E1's cost came from the calls and the refusals, not from them.

### gemini 0.6.0 (0.4.22.dev30)

**Contract change for the backend (breaking):** geomind now needs gemini `>=0.6,<0.7` (was `>=0.5,<0.6`) and pins the 0.6.0 release wheel (`requirements/gemini.txt`, sha256 `738567e46cc706ca48051bcf115926774d9d8013534ed0bee1713edc2451f2a8`; `[tool.uv.sources]`). The backend moves to gemini 0.6.0 together with this geomind. gemini 0.6 replaces `Inlet` and `Outlet` with one `Port`; geomind used neither outside a test fixture of the removed module sandbox, now deleted. The plant file format is unchanged: every example and project plant builds, and results are byte-identical to 0.5.14.

- A connection gemini 0.6 refuses comes back as `stream_mismatch` at its path, naming both ends and what each carries, with gemini's suggested ports (`build_plant`, `patch_plant`, `merge_designs`); `plant_issues` (`gm.check`, or `plant.check()` without a case) also lists `generic_conflict` and `unconnected_port` before the design lead's review. No tool for `plant.suggest` yet (waits for Sahand).
- Old logs replay: a log of another version replays with its recorded tool results.

### What the first end-to-end run showed (0.4.22.dev29)

Run E1: the coordinator, then the project lead with every team, DeepSeek, memory off, capped at 1 USD (it stopped there, 0.997 USD, before a verified design). Each bug is pinned by a test.

**Contract change for the backend:** a new tool `fill_parts` of the design lead, which runs the reservoir, well and energy systems engineers as nested runs at the same time (their events interleave under `design_lead`).

- Fix (#55): the design lead called the reservoir, well and energy systems engineers one by one; `fill_parts` (`Team` in `geomind/tools/delegate.py`) takes one brief each and runs them side by side in code, within `design_concurrency`, a failing member's error beside the others' answers. A single engineer is still called alone to send it back a problem of its own.
- Fix (#53): the project lead asked the user again about a case value the user had just approved through the case lead; a change the user confirmed is accepted (`accept_case`), never asked again.
- Fix (#54): the design lead made up a grid gas composition and tried to put that case value under three plant paths; the design lead and the engineers hand a value gemini asks for at a case path over at once, never into the plant and never with a number of their own.

### gemini 0.5.14

- geomind runs on the gemini 0.5.14 release wheel (`requirements/gemini.txt`, sha256 `91b8cc2428d1bfde4da936fe49308de8ac0c736bfa205023f75ac261b0a7e6ec`; `[tool.uv.sources]` in `pyproject.toml`). 0.5.14 runs a `Study`'s plants and cases in worker processes when gemini's runtime `processes` setting is above 1, with the same results in the same order and no API change; geomind does not set it. No sandbox image is needed any more.

### What each agent alone showed, live (0.4.22.dev28)

Every agent ran alone on a fixed input from the earlier runs (15 tasks, DeepSeek, 0.43 USD); all passed their criteria, and their outputs were read one by one. Each bug is pinned by a test.

**Contract change for the backend:** a tool's `description` (in `tool_schemas()` and the `tools.json` snapshot) is its whole docstring without `NOTE:` paragraphs, one line per paragraph, instead of the first paragraph only.

- Fix (#50): a model saw only the first paragraph of each tool's docstring, so no usage rule, shape or example written there reached it (`evaluate_module`'s inlet form, `patch_plant`'s ownership, `set_case`'s details). `tool_description` gives the whole docstring but its `NOTE:` paragraphs.
- Fix (#47): `evaluate_module` shows a whole inlet with its fluid and gemini's fluid fields, each property as `{value, unit}`; engineers had sent `kind` beside the inlet and a bare density.
- Fix (#42): a run with the memory off no longer offers the memory tools, nor their prompt sections; agents had called `search_memory` again and again and were refused.
- Fix (#43, #44): the case lead computes nothing (a value gemini derives, such as the reservoir temperature from the ground's gradient, stays unset) and proposes no number with no source: knowledge with its source, or a question to the user.
- Fix (#45): the engineers and the design lead compute nothing by hand (no formula, conversion or derived value); a module's top-level values come first and gemini derives the inner ones; the reservoir engineer had computed a productivity index from Darcy's law.
- Fix (#46): an empty text is no answer: the model is asked for it; the energy systems engineer had ended with `''`.
- Fix (#48): a reference wrapped in quotes (`'"result/…"'`) is read as the reference.
- Fix (#51): a design or study name stored with other content is refused with a free name in `suggestions` (`<name>_2`) and the advice to send the same call with it; the well engineer had spent its last steps on the refused name and stored nothing.
- Fix (#49): the same bad input value failing the same way counts as the same failure even beside other input; the explainer had asked six times for a result it made up, each with another `path`.

### Evals: a fixed start and a live cap (0.4.22.dev27)

- A task may hold `setup`, tool calls `{tool, input}` that code runs in the task's chat before its agent (`SetupAgent`, no model), so an agent is tested alone from a fixed state: a case loaded, a design built and simulated, owners recorded. A setup call that fails stops the task. `eval_task.json` gains `setup` (additive).
- `python -m evals.run --live` needs `--max-cost USD`, the cap of each task with OpenRouter's prices; without it nothing is called.

### The engineering team, step 4: ProjectLead, SupportLead, Curator (0.4.22.dev27)

**Contract changes for the backend:**

- New required settings, no fallback: `GEOMIND_PROJECTLEAD_MODEL`, `GEOMIND_SUPPORTLEAD_MODEL`, `GEOMIND_CURATOR_MODEL`.
- `Route.loop` has a new value `project` (the coordinator's route for design, comparison and case changes), and `LOOPS["project"]` is `ProjectLoop` with the `ProjectLead`. `run.started.loop` is `project` for such a run, and its agent `project_lead`, with the nested teams below it (`project_lead.case_lead`, `project_lead.design_lead`, `project_lead.reviewer`, `project_lead.analysis_lead`, `project_lead.explainer`, `project_lead.support_lead`, `project_lead.comparison`). `design` and `compare` stay as the rule-driven loops.
- `Route` gains optional `task` (the coordinator's brief for an app event; it follows the user's message as a second user message starting `The coordinator's brief: `) and `preferences` (`{name: value}`).
- The problem state gains `preferences` (`{name: value}`, default `{}`), rendered for every agent; `problem_state.json` is regenerated (additive).
- New tools: `write_lesson` (curator); `support_lead` on the project, case, design and analysis leads; `economist` on the analysis lead.
- Experience gains lesson entries `{id, kind: lesson|user_fact, role, text, origin: {run, source}}`; `search_memory` returns `lessons` with the experience section.
- `DesignDriver`, `CompareDriver` and `ComparisonDriver` moved from `geomind.loops.design`/`geomind.loops.compare` to `geomind.agents.project.lead.design_driver`/`comparison_driver`; old logs naming the old class paths still resume and replay.

- New agent `ProjectLead` (`agents/project/lead/`), a model that plans case, design, review, analysis and explanation, writes each team a brief, routes each failure to its owner, never loosens the case, asks the user only what teams cannot settle (one question, options, recommendation first) and stops when the review passed and analysis is done, or on `repeated_failure`. Code guards: the project's case file loaded by rule before its first call; its `reviewer` tool runs gemini's verdict after the `Reviewer`, lists each failure with the team it goes to first (gemini's domain as a hint), flags a repeated failure on a changed design, and keeps a passed design as experience by code; the `Verified` hook; the engine's budget, step limit, output limit and repeated-call stop. Its `comparison` tool runs the rule-driven comparison.
- New agents `SupportLead` (`agents/support/lead/`: routes the other leads' support requests to the summarizer or the curator and checks the answer) and `Curator` (`agents/support/curator/`: the run's general per-role lessons and the user's facts into experience with their origin; a digit in a lesson is refused).
- The `Coordinator` routes design work to `project`, writes a brief for app events and keeps the user's preferences.
- The `AnalysisLead` leads the analysis team: its `economist`, and improvement proposals for the design lead.
- `remember_design` became `keep_design(context, found, rejected)` in `geomind/tools/memory.py`.

### The engineering team, step 3: the design team (0.4.22.dev26)

**Contract changes for the backend:** new required settings `GEOMIND_PROCESSENGINEER_MODEL`, `GEOMIND_INTEGRATIONENGINEER_MODEL`, `GEOMIND_RESERVOIRENGINEER_MODEL`, `GEOMIND_WELLENGINEER_MODEL`, `GEOMIND_ENERGYSYSTEMSENGINEER_MODEL` (no fallback) and `GEOMIND_DESIGN_CONCURRENCY` (how many engineers run side by side; required for a live run, no default). New nested agents under `design_lead`: `process_engineer`, `integration_engineer`, `reservoir_engineer`, `well_engineer`, `energy_systems_engineer`; the three last run at the same time, so their events interleave. A new tool `merge_designs` (`tool.started`/`tool.finished` as any tool).

- New agents in `agents/design/`: `ProcessEngineer` (`process/`: the modules, a reason each, `design.modules` and `design.owners`), `IntegrationEngineer` (`integration/`: connections, inlets, outlets, fluids, boundaries), `ReservoirEngineer` (`reservoir/`), `WellEngineer` (`well/`), `EnergySystemsEngineer` (`energy/`). Each prompt is method only, with experience a starting point only.
- The `DesignLead` leads them: process, then integration, then reservoir, well and energy in one step side by side (bounded by `design_concurrency`), `merge_designs`, its review checklist, each problem back to its owner, then size, simulate, check and optimise as before.
- `patch_plant` refuses an engineer's change to a part another discipline owns (`not_allowed`, the path and its owner in the message); the design lead and other agents are not checked.
- `merge_designs(base, designs, name)`: joins designs patched side by side from one base; a value two designs set differently is a conflict naming the path and both designs, and nothing is stored.
- `Delegate(..., limit=SETTING)` bounds how many delegates of one limit run at once in a run; an unset limit is refused naming its variable.

### The engineering team, step 2: the Geoscientist (0.4.22.dev25)

**Contract changes for the backend:** a new required setting `GEOMIND_GEOSCIENTIST_MODEL` (no fallback); a new nested agent `geoscientist` under `case_lead` in events and the runlog (`design_driver.case_lead.geoscientist`).

- New agent `Geoscientist` (`gd.agents.Geoscientist`, `agents/case/geoscientist/`): reads each report whole once and proposes the ground, reservoir, brine and dissolved-gas values (salinity, CO2, CH4, GWR when given; transmissivity, not permeability alone) as typed `Findings` (`values` with page, table, depth, quote, quality and range with the base case; `missing`; `disagreements` with both sources; `files_read`). It never sets the case and never fills a gap with a typical value. The `CaseLead` asks it through its new tool `geoscientist` and puts each value in the case with its page as the source.
- Fix: a delegate gave a typed answer back as Python's repr of a dict (`{'values': ...}`), which the parent model could not read as JSON; it is JSON text now.

### The engineering team, step 1: renames, removals and the folder layout (0.4.22.dev24)

**Contract changes for the backend (breaking, listed for the backend update):**

- **Models:** every model agent has its own required setting, with no fallback: `GEOMIND_ANALYSISLEAD_MODEL`, `GEOMIND_CASELEAD_MODEL` (was `GEOMIND_FORMULATOR_MODEL`), `GEOMIND_COORDINATOR_MODEL`, `GEOMIND_DESIGNLEAD_MODEL`, `GEOMIND_ECONOMIST_MODEL`, `GEOMIND_EXPLAINER_MODEL`, `GEOMIND_REVIEWER_MODEL`, `GEOMIND_SUMMARIZER_MODEL`. **Removed:** `GEOMIND_MODEL`, `GEOMIND_CHEAP_MODEL`, `GEOMIND_FORMULATOR_MODEL` and the runtime setting `default_model`. A live run and `geomind check-live` name each unset one (`designlead: set GEOMIND_DESIGNLEAD_MODEL or designlead_model`). Runtime role settings are renamed: `analyst_model` to `analysislead_model`, `designer_model` to `designlead_model`, `verifier_model` to `reviewer_model`, `formulator_model` to `caselead_model`; `role_models()` keys are the class names in lower case (`designlead`). A stored run with the old names still resumes (`REMOVED_SETTINGS` are dropped).
- **Sandbox removed:** `gd.sandbox` (`LocalSandbox`, `DockerSandbox`, `Sandbox`, `SandboxProvider`, `Manifest`), `Run(sandbox=...)`, `Run.load(sandbox=...)`, `Engine(..., sandbox=...)` (it was the fourth positional parameter), `gd.errors.SandboxError`, the internal events `sandbox.provisioned` and `sandbox.closed` (an old log holding them still loads: unknown types are skipped), the settings `sandbox_timeout`, `sandbox_memory`, `sandbox_disk`, `sandbox_cpu`, `geomind run --sandbox`, `make sandbox-image`. The shared contract's section 3 (`SandboxProvider`, `sandbox=gd.sandbox.DockerSandbox()`) must drop them; the backend passes no `sandbox` any more.
- **Tools removed:** `run_python`, `read_file`, `write_file`, `write_module`, `test_module`, and the skill `writing-a-gemini-module`. No code runs in geomind; a family that needs a model gemini lacks is `blocked`.
- **Agents renamed** (event `agent` and the dotted runlog paths change): `Formulator` to `CaseLead` (`case_lead`), `Designer` to `DesignLead` (`design_lead`), `Verifier` to `Reviewer` (`reviewer`), `Analyst` to `AnalysisLead` (`analysis_lead`). The design loop's nested runs are `design_driver.case_lead`, `design_driver.design_lead`, `design_driver.reviewer`; a comparison's family run is a `design_lead` (the delegate tool `family_design_lead`), no longer `family_designer`. **Removed:** `Assistant`, `CodeAssistant`, `FamilyDesigner`.
- **Route:** `Route.agent` is `analysis_lead` only (was `analyst` or `code_assistant`); `AGENTS` in `run.py` holds `analysis_lead`. `geomind chat --agent` and `geomind run --agent` take the new snake names.
- **Memory:** the Reviewer and the Explainer read the knowledge only (`search_knowledge(query)`, `read_knowledge(id)`, new tools), never experience; the Reviewer no longer writes memory. The case, design and analysis teams keep `search_memory`, `read_memory`, `write_memory`.

**Layout:** each agent is `geomind/agents/<team>/<name>/agent.py` with its `prompt.md` beside it (`project/coordinator`, `project/reviewer`, `project/explainer`, `case/lead`, `design/lead`, `analysis/lead`, `analysis/economist`, `support/summarizer`), tests in `tests/unit/agents/<team>/<name>/test_agent.py`; `gd.agents.<Class>` is unchanged as the import. `Prompt("design/lead")` loads the role file by `<team>/<name>`; skills stay in `geomind/prompts/skills/`. Eval suites `analyst` and `designer` are now `analysis_lead` and `design_lead`.

- `geomind run --model ID` sets every role's model (it set `default_model`).
- Fix: an eval task's `max_steps` is its limit: the runner answers the step-limit question `stop` instead of giving it the task's reply (`challenge2/tight_budget` ended with `RequestError`, and the checked-in report was stale).

**Required settings (backend):** `GEOMIND_MAX_OUTPUT_TOKENS` (the most output tokens of one model call), `GEOMIND_MEMORY` (`on` or `off`; with `on` also `GEOMIND_MEMORY_DIR` and `GEOMIND_MEMORY_SIMILARITY`), `GEOMIND_FORMULATOR_MODEL` names the new Formulator's model; it has no fallback to `GEOMIND_MODEL`. `GEOMIND_MAX_STEPS` (or `--max-steps`) has no default any more: a run without it refuses to start. It is how many steps an agent takes before the run asks the user to continue; set it next to `GEOMIND_RETRY_COUNT` and `GEOMIND_RETRY_DELAY`.

- `patch_plant(design, changes, name)`: build a plant in small steps, a JSON merge patch of one module's values at a time on a stored design, each checked by gemini and stored under a new name, with what is still missing (`missing`). The Designer builds the header and type first, then patches; the whole-file path of `build_plant` still works. A class's whole file is 2,100 to 7,700 characters of structure (5 to 28 modules, 7 to 61 connections) with 92 to 136 values to fill.
- Fix (#41): `build_plant`'s `plant` schema names every top-level key of `gm.plants.schema()` and requires the header (`minProperties`), instead of a bare object; an empty plant is refused as such, with the smallest file as an example. The provider's answers were whole (`finish_reason: tool_calls`): the model had sent `{}` to a schema with no keys.
- Fix (#40): the same call failing the same way more than its tool's `max_retries` times in a row stops the agent's run (`step_limit`-like `error` with the reason) instead of spending; a designer had sent `build_plant` with an empty plant 35 times.
- Fix (#39): a plant's issues are compact (`path`, `code`, `kind`, the message without its path, `units` as one `a|b` text: 30,800 characters became 21,200 for one class), and `read_plant` keeps its result whole for the kept turns; the designer had read one plant file back in 29 parts.
- Fix (#38): a plant issue at a case path (site, demand, utilities, time, economics, requirements) suggests handing over `case change needed: <path>: <why>`; the designer had tried 12 times to put a case value in the plant file.
- Fix (#37): when the project holds a `case.json`, the design loop loads it by rule (`set_case(source='project')`) before any agent, and the Formulator runs only for what it lacks; the Formulator had asked the user for the whole case.
- One builder makes the compact key tree of any gemini public schema (`key_tree`, `tree_text`, `trees(...)`): the case and its economics for the Formulator, the plant file and the study for the Designer, the study for the Economist; each agent gets only the trees of its tools, in its cached system prompt, and a test checks every top-level key of each schema is in its tree. Sizes: case about 7,500 characters, plant about 1,900, study about 350.
- The Designer's system prompt carries the plant file's key tree (`plant_tree`, from `gm.plants.schema()`, with gemini's module types), and `describe_module` returns a module's compact description built from gemini's `describe()`: each parameter and control on one line with its quantity's accepted units, bounds and options (* when it has no default), its ports, outputs and children, about a quarter of the size.
- Fix (#36): one model call's output is bounded by `GEOMIND_MAX_OUTPUT_TOKENS` (required, no default), the least of the limits of each call; a single runaway completion had written 103,404 tokens. A completion the limit cut (`finish_reason: length`) runs nothing: the model is told so (`feedback: length`) and answers again, shorter.
- Fix (#35): the key tree holds the economics file's keys too (`gm.case.Economics.schema()`), so the Formulator no longer reads the economics schema part by part. It sets the case in parts, each `set_case` with only the keys it adds or fixes.
- A kept result (`Tool.keeps_result`: a document page, a stored part) is stored again and stays whole in the history for the last `compaction_keep_turns` turns, then shrinks to its outline and reference like any other, instead of staying whole for the whole run.
- The Formulator's system prompt carries the case's key tree (`case_tree`), made at render time from gemini's public `Case.schema()`: every path with its form, units or options, and `*` when required, about 4,000 characters. A key gemini renames shows at once; there is no copy. `Prompt(role, appendix=...)` adds such text when a prompt renders.
- Shared memory for every agent (`.claude/docs/memory.md`): `knowledge` (cited reference values with source and status) and `experience` (designs that passed verification, written by the design loop in code); `search_memory`, `read_memory`, `write_memory`; experience only above `memory_similarity`, a starting point that is simulated, checked and optimised again. `FileMemory` for the CLI, `Workspace.memory` or `Engine(memory=...)` for a backend. `geomind memory seed FILE` loads a cited catalogue; `data/knowledge/cost-sources.csv` is a copy of gemini's cost catalogue (v0.5.13), owned by geomind. An assumption may cite a knowledge entry.
- Design change: a new agent, `Formulator` (`gd.agents.Formulator`, `agents/formulation/`), owns the case. The design loop runs it before round 1 when the case is missing (from the project's files or its `case.json`) and again when a round names `case change needed: <path>: <why>` or the user's case must be restored; the `Designer` reads the case and no longer has `set_case`, `save_profile`, `list_files`, `read_document` or `search_documents`, so later rounds never read the files again. Every case value no file gives is confirmed by the user in one question (`approve all`, `change some`, `stop`) and recorded as an assumption with its source or reason. The event shapes are unchanged: the backend sees one more nested agent, `formulator`.
- Fix (#31): a plant value gemini lists as missing that no file gives (an equipment parameter) is the designer's assumption with a reason, never a question for a datasheet.
- Fix (#32): a document page (`read_document`) or a part of a stored result (`read_stored`) up to the result limit stays whole in the history and is not stored (`Tool.keeps_result`); it had shrunk to an outline after one step, so the run read the same brief again and again.
- Fix (#33): an assumption carries an optional `reason` and `citation` (title, publisher, year, price year, currency, page or link, note), shown in the problem state; the Formulator records the values the user confirmed with them. `problem_state.json` gains the two optional fields; nothing existing changes.
- Fix (#34): `read_stored` of a part too long to show whole returns its keys (or length), an outline and the call that reads one deeper, instead of the same outline again; a path with `/` reads as `.`.
- The Formulator builds a case from the chat too: the design loop starts with it whether or not the project has files; it takes the user's words first, then files, then values it proposes; without files it asks a few grouped questions with units; a value the user typed is recorded as the user's, with `citation: {"origin": "user message"}`, and needs no confirmation.
- `geomind run --loop tool --agent NAME` runs one shipped agent alone, such as `formulator`.
- The step limit no longer ends an agent's work: the run waits on a question with the options `continue` and `stop` (point `steps`). `continue` gives it as many steps again and `stop` ends it with `step_limit` as before; a budget still bounds the cost, and a replay takes the recorded decisions.

What the fifth live run showed, each pinned by a test on its recorded calls.

- `search_documents` returns `{matches, note}` instead of a list: without a match the note says the project does not state it (an assumption with its reason, or `ask_user`); the same words searched again in the run tree are noted; a file's name alone is no match.
- A series naming a column by its old name after `columns` renamed it gets the new name in `suggestions`.
- A table (CSV, TSV) is not searched as text: its rows matched words of the brief.
- The design loop's next round after a question on the case carries the last round's answer (at most 6,000 characters), so it goes on from there instead of reading everything again.
- Fix: a run waiting on a nested run's question reports that run's usage too (segment 7 printed 0.033 USD of 0.093).
- Fix: the round after a failed verification carries the last round's answer as well.
- Fix: two rounds that recorded no design (their steps ran out) no longer stop the design loop as `repeated_failure`; it goes on to its round limit.
- Fix: a step that asked the user a question gives its step back (`RunState.questions`), so an answer to a question on the last step is acted on.
- Fix: an object sent as JSON text gets the suggestion to send the object itself, beside pydantic's error.
- Fix: a PDF reads in layout order (pypdf's layout mode, runs of spaces shortened), so a table drawn word by word keeps each row on one line instead of one word per line.
- `geomind run --replay FILE --replay-steps N` answers the first `N` calls from a recording at no cost and the rest live, so a run after a fix goes on from where it failed; both or neither, no default. `Recorder` writes an `input_digest` of the tool results each call answered; a line whose digest differs from this run's goes live at that step. `ReplayThenLive` is the provider.

## [0.4.21] - 2026-11-03

What the fourth live run showed, each pinned by a test on its recorded calls. CLI and tools only.

- Fix: a free-text answer to a question with options ended `geomind run` with exit 1. The contract takes only an option's value, so the CLI asks again with the options shown, at most `--answer-retries N` times (no default: unset, never), and then, or at the end of the input, stops the run as `waiting` (exit 2) with the `geomind resume` line.
- New `geomind resume <run id> --request ID --answer TEXT`: answers a waiting run in a new process, with the provider, mode and caps given again.
- Fix: `search_documents` never searched the project's attached files, so the brief's values were not found (six searches, all `[]`); it now also returns passages of every project file that reads as text, with `name` and `start`.
- `read_stored` no longer stores a long part again under a new reference (`Tool.stored_input`), which made the run read copies of copies.

## [0.4.20] - 2026-11-03

What the third live run showed (run 9bc9e7b7), each pinned by a test on its recorded calls. Runs on gemini 0.5.13 (wheel sha256 `cc598bef…387c510`, image `gemini-sandbox:0.5.13`), whose only change is the optional series key `time_zone`.

- Fix: an `invalid_unit` beside missing values kept its code and path (it became `case_incomplete` at `demand.heating.power`, and the corrected field was lost); the missing paths follow in one suggestion.
- Requirements of another shape give one suggestion with the shape from gemini's schema instead of a `requirements[i].on` and `.quantity` path per requirement.
- gemini errors are shown with each path once, and the same problem on many rows of a file as one line with the count and the first and last row (730 lines became 2). Codes, paths and gemini's text are unchanged.
- `read_document`: nested runs share what the run tree read, and once a document was read whole, `force=true` no longer reads it again (the run read the PDF about 60 times).
- A series takes gemini's `time_zone` (an IANA name) through `set_case`; geomind has no zone of its own and rewrites no value. gemini's "has no offset" error (one summarised line per file) suggests the exact retry with `time_zone` on each series, the zone chosen by the model, the one `time.start` is meant in, and recorded as an assumption; the Analyst and Designer prompts say so.
- CI, lint and the release run only Python 3.12, the backend image's, during the hackathon; the other Pythons are commented out ("disabled during hackathon, re-enable after (Sahand 2026-11-03)"). `requires-python` and the classifiers are unchanged.

## [0.4.19] - 2026-11-03

What the second live run showed (run f90f3e12), each pinned by a test on its recorded calls.

**Required settings (backend):** `GEOMIND_RETRY_COUNT` and `GEOMIND_RETRY_DELAY` have no default any more. A live run and `geomind check-live` refuse while either is unset; set them next to `GEOMIND_MODEL`, `GEOMIND_CHEAP_MODEL` and `GEOMIND_CONTEXT_WINDOW` (the old values were 3 and 0.5). A scripted or fake provider needs neither.

- Fix: a call's `max_tokens` is at most the model's window less the input bound, so a budget's room no longer asks for more than fits (the run asked OpenRouter for 1,598,258 output tokens and four designer rounds got a 400).
- OpenRouter's 400 for a too long call is `ProviderError(code="context_exceeded")`; a run it ends keeps the message, and a delegate answers with the tool error `context_exceeded` (new in `TOOL_ERROR_CODES`) instead of `internal`.
- `set_case`: a series naming a file not passed gets the retry with `files=[...]`; `invalid_unit` gets the field corrected and the accepted units; `requirements` inside `changes` gets the call with `requirements={...}`.
- `build_plant` without a header: `old_format` with the smallest plant file of `gm.plants.schema()` in `suggestions`.
- `read_stored` with a path on a text says to read it without a path.

## [0.4.18] - 2026-11-03

Additive: what the first live run showed, each pinned by a test on its recorded calls.

- `set_case(columns={file: {old: new}})` renames CSV header names before gemini reads the file; gemini's error about a first column that is not `time` carries the exact retry call in `suggestions`.
- `case_incomplete` for a case without its header adds a minimal case made from `gm.Case.schema()`; `set_case`'s `changes` description shows it, and the Analyst and Designer prompts point at it.
- `read_stored` with a wrong path lists the keys or first indexes there.
- `read_document` remembers the pages a run read: a repeat is `already_read` with the reference of the stored result, unless `force=true`.
- `geomind run --loop design` takes a project with attached files and no `case.json`.
- `GEOMIND_RETRY_COUNT` and `GEOMIND_RETRY_DELAY` set the provider backoff. The defaults stay 3 retries from 0.5 s: in the live run three retries did not outlast two OpenRouter 504s, so a host may raise them.
- `tests/fixtures/live/` holds the run's recording and its two CSVs.

## [0.4.17] - 2026-11-03

Additive. Runs on gemini 0.5.10 (wheel sha256 `4d46a750…fc0a84`, image `gemini-sandbox:0.5.10`), which changed nothing existing.

- `optimize` keeps the history of gemini's search in its study (`history`, from `gm.study.Search.to_dict()`); `best`, `feasible` and `evaluations` are as before.
- Costs: `gm.evaluate.missing` lists every economics value the costs need, so each `case_incomplete` of `estimate_costs` and of `compute_kpis` `errors` has the same, full list in `suggestions` instead of the first value of one metric.
- Durations take any time unit gemini converts, `ms` again among them.
- The CLI reads `<repository>/.env`, then `~/.config/geomind/live.env`, before a command; the real environment wins and no value is shown. `.env.example` lists the names; `.env` and `*.env` are ignored, and a test fails if one is tracked. Tests read no `.env` and have no key.
- gemini's examples are the same in 0.5.10, so the test copies stay; the fast tier runs in about 60 s instead of 85 s, as gemini's report copies the plant once.

## [0.4.16] - 2026-11-03

No output shape and no unit string of a tool changes; a duration in `ms` is refused.

- geomind converts no unit itself. The case step shown by `set_case` and the profile tools (`readable_step`) and the durations of the settings (`parse_duration`) now go through `gm.units`; geomind still chooses its display units (`READ_UNITS`). A test fails on any conversion factor in the package.
- `parse_duration` (the durations of the settings, such as `sandbox_timeout`) takes `s`, `min`, `h` and `d`, the units gemini converts. `ms` is no longer accepted, and an unknown unit is an error that lists the accepted ones.

## [0.4.15] - 2026-11-03

Additive.

- `TimeLimit` bounds the call in flight: a model call or an async tool that passes the time left is cancelled, and the run stops with its partial answer (new `gd.errors.TimeLimitReached`). A sync tool or gemini work in a worker thread cannot be cancelled: the run stops waiting at the limit and the thread finishes on its own.
- `geomind run --retries N` sets `compare_retries`.
- `evals/scripted.py`, the scripted model that wrote the `alternatives/three_families` recording, is committed, with a slow test that runs it offline.
- `AGENTS.md` and `.claude/docs` point at `docs/rules.md`, `.claude/docs` and the copy of the shared contract instead of a `../docs` folder no clone has. `.claude/docs/evals.md` says why old tasks meet fewer criteria in the report's `CompareLoop` table: their recordings belong to other loops.

## [0.4.14] - 2026-11-03

Tests only; the package is unchanged.

- The copy of the shared contract is version 52 (backend `7f0bc92`), which has the `study.recorded` row. The event-table tests check it with the other types, and its two checks no longer skip: no test is skipped.

## [0.4.13] - 2026-11-03

Additive; it takes back the change of shape of 0.4.12.

- `compute_kpis` has the output shape of 0.4.11 again: a cost gemini gives no value for is its report entry (`{value: null, unit, reason}`), or left out as `npv` and `payback` are without revenue. 0.4.12 added `error` inside entries and turned an absent `npv` into a dict; both are gone. The new `errors` key maps each such cost to its error, `case_incomplete` with the path in `suggestions`. A test pins the 0.4.11 shape of every key.
- The flaky replay check of `tests/e2e/test_scripted_design.py` was geomind's test, not gemini: the explainer calls `estimate_costs` and `compute_kpis` in one step, they run side by side, and their results are logged in the order they finish. In 60 runs under load the two results came the other way round twice, every value equal. The test now compares each step's results in the order of its calls, as replay itself does; a different value still fails.

## [0.4.12] - 2026-11-03

Additive; one change of shape the backend sees.

- `compute_kpis`: a cost gemini gives no value for has `error`, `case_incomplete` with the path in `suggestions` and gemini's message, beside the report's `reason`. A cost the report left `null` (`npv`, `payback` without revenue) is now `{"value": null, "error": {...}}`. Before, such a cost had only a `reason` text, or was `null`, and no code.
- The 15 tests of the event table against the shared contract run again, on a copy of `backend/docs/app-build/contracts.md` version 51 in `tests/fixtures/contracts/shared.md`; they skipped, looking for a sibling `docs/` folder. The two checks of `study.recorded` still skip: the shared table has no row for it.

## [0.4.11] - 2026-11-03

Additive.

- New setting `gemini_threads` (`GEOMIND_GEMINI_THREADS`): gemini work runs in a pool of that many threads; unset, as before. On five heavy slow tests in one Python 3.14 process: 3.5 GB at the end (peak 3.9 GB) with neither, 2.3 GB (2.5) with `GEOMIND_GEMINI_THREADS=2`, 2.0 GB (2.1) with `MALLOC_ARENA_MAX=2` and 2.3 GB (2.5) with both. The arenas are the stronger fix; see `.claude/docs/releasing.md`.
- CI: the checked-in eval report is checked one cell per test, and the slow tier runs in five shards balanced by measured times (about 480 s of serial work each). Shard 1 held the whole report test and took 16 to 18 minutes on GitHub.

## [0.4.10] - 2026-11-03

CI and tests only; the package is unchanged.

- CI is split into a `fast` job (fast tier and e2e, every event) and a `slow` job in four shards (everything but a `dev` push). Every job runs `-n auto`, with `timeout-minutes` and `fail-fast: false`. Before, the full suite took 25 to 42 minutes per Python in one job, and a dying runner ended it at 98 %.
- `--shard i/n` balances the slow tests by the measured times in `tests/fixtures/shard_times.json`: about 420 s of serial work each.
- CI sets `MALLOC_ARENA_MAX=2`, and the report test uses one process per usable core, at most eight. The Python 3.14 runner deaths were memory: glibc gives each worker thread its own arena, and a test process grew to about 3.5 GB; two xdist workers plus the report's eight processes measured 17.6 GB. With two arenas the same tests stay at 1.0 to 1.7 GB (peak 2.4 GB). No Python object leaks: repeated runs plateau at about 380 MB. A long-running host, such as the backend's workers, should set `MALLOC_ARENA_MAX=2` too; see `.claude/docs/releasing.md`.

## [0.4.9] - 2026-11-03

Additive.

- A replay of a stopped run ends as the run did: a waiting run waits on the same request, a budget or time limit stop has the same reason and partial answer, a cancelled run is cancelled. Before, each ended `cancelled`.
- `CompareLoop(retries=N)` (setting `compare_retries`, `GEOMIND_COMPARE_RETRIES`): a family gemini rejects is designed again, told the reason, up to N times; unset means no retry. Mode `ask` stays one family at a time.
- The eval report runs its cells in processes (`--workers N`), one task through one loop each: the report test takes under three minutes instead of 11.5, with the same table.

## [0.4.8] - 2026-11-03

Additive.

- A delegate whose nested run stopped without an answer says why: new code `nested_stopped` with the run's message (a step limit, a refusal, invalid calls); a crash stays `internal`, its text in the log only. `RunResult.message`, which the shared contract lists and geomind lacked, carries why a run stopped, `None` for a crash. A failed family of a comparison now keeps that reason.
- CI: a push to `dev` runs the fast tier and e2e, everything else the full suite. Before, a `dev` push selected no test. A test pins the workflow and its Python matrix to the versions `pyproject.toml` declares.

## [0.4.7] - 2026-11-03

Additive, with one changed code.

- No overshoot with runs side by side: a bounded call holds its worst case (input bound plus the output it may use, priced when a price is known) until it returns, `total_usage` counts what other calls hold, and a call that would pass the cap is not sent.
- New eval `alternatives/three_families` for the `CompareLoop`: a scripted model, every tool real. gemini rejects the heating-only plant, and the other two are verified and ranked. It replays in the slow tier. `--agent compare` keeps running its recording on `StudyCompareLoop`; the report's `CompareLoop` table is the new loop, so old tasks meet fewer criteria there.
- `geomind run --concurrency N` sets `compare_concurrency`.
- `estimate_costs`: a cost missing a case value is `case_incomplete` (it was `missing_assumption`), with the path in `suggestions`, as other tools do.
- The Economist's comparison task names each family beside its result.

## [0.4.6] - 2026-11-03

Additive: `compare` is a real comparison. Old logs and recordings keep their loop.

- `CompareLoop` plans the families (from the request or the case, else proposed by the Designer: confirmed with the user, or unconfirmed assumptions in an `auto` run), designs each in its own `FamilyDesigner` nested run, verifies each feasible design once, compares the verified ones with the Economist and explains with the Explainer. There is no fixed number of families.
- `concurrency` (setting `compare_concurrency`, `GEOMIND_COMPARE_CONCURRENCY`): families side by side; unset means one at a time, and mode `ask` always is. A failed or infeasible family stops nothing and keeps its reason.
- `design.alternatives` entries are `{family, design, result, verdict, reason}`; `design.comparison` holds the ranking, the Pareto set and the recommendation. `show --format md` has a `## Comparison` table, and a stop lists the finished alternatives.
- Budgets and time limits cover runs side by side: `total_usage` counts a running sibling. A model call in flight counts when it returns.
- New `Delegate(runs_beside=True)`, a lock for the chat's index artifacts, `gd.loops.StudyCompareLoop` (the loop up to 0.4.5, on which old logs and the `two_families` recording run).

## [0.4.5] - 2026-11-03

Additive, with one changed code.

- A design run replays and resumes with its recorded `max_rounds`: replay rebuilt the driver with the default, so a run stopped at its own limit did not replay. New `Agent.load_loop_state`; `DesignLoop.load_state_dict` takes the logged limit, so a resumed run keeps it over the new loop's.
- Tests pin the replay of a budget stop, a time limit stop and a pending question.
- A case that reads but lacks what a plant needs is `case_incomplete` too, with gemini's message and the paths in `suggestions`. A tool that returned `missing_value` or `missing_assumption` on a case path now returns `case_incomplete`; a missing search range keeps gemini's code.

## [0.4.4] - 2026-11-03

Additive: agents read the files the user attaches. Logs, stores and recordings of 0.4.x still load and replay.

- Optional `Workspace.files(project_id)` -> `[{name, size, media_type}]` and `Workspace.file(project_id, name)` -> bytes or `None`, on `MemoryWorkspace` and `FileWorkspace` (`files/` of the project). A workspace without them keeps working.
- New tools `list_files` and `read_document(name, start, length)`: CSV, TSV, JSON, Markdown and text as text, a CSV also with its columns, row count and first rows, a PDF as text with page markers. New dependency `pypdf`. Pages of at most 20,000 characters; long reads are stored by reference.
- Error codes `files_unavailable` and `not_text`.
- `set_case` takes `files`: project files whose bytes go to gemini, so a data file is never retyped. A case with values missing is `case_incomplete`, with every path in `suggestions`.
- The design and compare loops send a project with files to the designer first, instead of asking for the case. The Analyst gets `set_case`.

## [0.4.3] - 2026-11-03

Additive: geomind installs from releases and publishes its own.

- gemini comes from its release wheel everywhere: `requirements/gemini.txt` pins it with its hash, `make install` has no `-e`, `make gemini-version` prints it and `make sandbox-image` pulls its image. `pydantic>=2.10`.
- CI runs on our gemini, on pushes to `dev` and `main` and on pull requests, with no gemini checkout.
- New workflow `release.yaml`: a `v*` tag on `main` builds the wheel and sdist, tries the wheel in a clean venv and creates the GitHub Release.
- Tool error codes `no_case` (the chat has no case) and `case_incomplete` (the case misses values; `suggestions` lists the paths). The messages are unchanged.
- The package readme is `README.md`.
- `docs/rules.md`: the two long-lived branches, what happens to other branches, and tests on local servers only.

## [0.4.2] - 2026-11-03

Additive. Runs on gemini 0.5.5 installed from its release wheel.

Context of a design run: 295,953 tokens before, about 146,000 after the smaller context, about
128,000 after the Designer prompt cut. The last figure is chars/4 of every request of the recording
`challenge2/hackathon` (20 calls, 15 of them the Designer's, each 1,262 tokens smaller).

- The 0.3.1 log test skips the macOS `._*` entries of its archive, which failed it on Linux.
- The repository has a `README.md` and a `docs/` folder for people: `docs/rules.md` holds every project rule, moved out of `AGENTS.md`, and this changelog moves here. `.claude/docs/` stays for agents.
- Every git worktree goes under `.tmp/`. A test fails when a path under `.tmp/` is tracked or `.gitignore` stops ignoring it. `.tmp/live/t.md`, force-added in the 0.4.2 work, is removed from the history.
- The root `conftest.py` moves to `tests/conftest.py`.
- Tests: the designer tasks that size a plant or run a real search (`designer/project_plant`, `designer/missing_range`, the designer's shipped tasks) move to the slow tier. Eight xdist workers replace `-n auto`: the fast tier takes half the wall time here and no test nears the one-second budget.
- Designer prompt: "Choices" is reworded to "Decisions", the name gemini removed stays out of the package.
- Tests run on the published gemini wheel: it ships no examples, so `tests/fixtures/gemini_examples/` holds gemini's `hackathon_2026` and `shallow_district` from tag v0.5.5, and `example_folder` reads them there.
- Designer: search ranges come only from the user or the case. A missing one is recorded in `questions` and asked with `ask_user` (values proposed with a reason); `set_ranges` only after confirmation. The Designer prompt is cut from about 2,800 to about 1,500 tokens (tool detail stays in the tool descriptions and the `designing-a-plant` skill). New offline recording `designer/missing_range`.

Additive: geomind holds no model id (Sahand, 2026-11-02: no Anthropic model anywhere).

- `FIXED_DEFAULT_MODEL` and `FIXED_CHEAP_MODEL` are removed. `default_model`, `coordinator_model`
  and `summarizer_model` are `None` unless `GEOMIND_MODEL` / `GEOMIND_CHEAP_MODEL` set them;
  A run on a real provider (`needs_models`) is refused before `run.started` with a `RunError`
  naming each role's missing setting (`designer: set GEOMIND_MODEL or designer_model`);
  `OpenRouter` also refuses a call without a model. Fake runs need no model.
- `run.started` records `models` (the model of every role; optional, old logs load) and the export
  header lists them.
- Context window: new setting `context_window` (`GEOMIND_CONTEXT_WINDOW`), else the provider's
  `context_length`, read once per process off the event loop at the start of a run on a real
  provider (a fake run never fetches); unknown raises `RunError` at the start (before, an unknown model got a guessed 128 000, and
  `CONTEXT_WINDOWS` / `DEFAULT_CONTEXT_WINDOW` held three Anthropic models).
- Caching: `CACHED_MODELS` is removed; new setting `cache_marked_models` (`GEOMIND_CACHE_MARKED_MODELS`)
  lists the model id prefixes that get cache breakpoints, none by default; DeepSeek caches on its own.
- `geomind check-live` lists every role with its model and fails on a role without a model or an
  Anthropic model id. A test greps the package, evals and docs for Anthropic model ids.

Additive: tool schemas and error texts tell the model what the call needs, so it does not learn
reference forms, sizing ranges, units and state shapes from failures.

- Every argument that takes a stored reference has a JSON Schema `pattern` and a description with
  an example (not enforced by the input model). A wrong reference gets `unknown_name` listing the
  stored references of its kind; `designs.index` and `results.index` are new chat artifacts.
- `size_plant`, `optimize` and `run_study` name each missing search range and give the
  `set_ranges` call that adds it, with the unit of the leaf and no number. `size_plant`'s
  description says sizing reads the ranges and `params.backup`.
- A unit gemini rejects (`save_profile` step `day`, any tool) gets gemini's message plus the units
  gemini accepts, read from `gm.units`.
- `update_state` offers a typed `changes` schema (`op` enum, `path` pattern, `value` over the
  state's models) and a refused change returns the shape expected for its path. The input model
  is unchanged, so every input valid before stays valid.
- Fix: `save_profile` read the case and its files on the event loop; it now reads them in a worker
  thread (`asyncio.to_thread`), as the docs said.

- Fix: the Economist task no longer crashes on a `design.start_result` or `alternatives[].result` that
  is an object. The problem state's design section is typed (`DesignState`); `update_state` refuses an
  object for a reference, and a stored state with one loads converted or under `design.unreadable`.

- The Designer starts from the project's plants: `read_plant(project_plant=...)`, then `build_plant`
  before sizing or searching; a new plant only when none fits, with the reason as an assumption.
  The `DesignLoop`'s first task names the project's plants (none when there are none). The prompt
  shows the size-then-optimise sequence. New offline recording `designer/project_plant`.

Additive; nothing renamed or removed. Cuts the input tokens of long tool loops.

- Tool results over 2000 characters are stored as `result-...` (their `tool.result` has the
  `reference`); the history shows them whole for one step, then as the reference, the small values and
  an outline. New tool `read_stored(reference, path)` reads them again, whole or in part. Results over
  `tool_result_limit` now keep their small top-level values and a structural outline (names of
  list items, keys) instead of the first 500 characters.
- Call inputs over 800 characters in older assistant messages are shortened to an outline.
- Agents with `read_stored` get a shared "Stored results" text after their prompt (`STORED_RESULTS`,
  `geomind/prompts/prompt.py`); `tests/unit/snapshots/tools.json` gains `read_stored` (additive).
- `list_plants` takes `plant_class` and `with_schema`; without them it returns `project_plants` and the class
  names with summaries only (its former `capabilities` and `roles` for all classes passed the result
  limit). `plant_class` returns that class's `capabilities` and `roles`; `with_schema` gemini's plant
  schema. `build_plant` offers a short `plant` schema (validation unchanged).
- `update_state` offers `changes` without `$defs` and `anyOf`: the shape of each list's item is in
  the description of `value` (half the tokens); the tool still checks the value and returns the shape
  expected for a path. Every input valid before stays valid.
- `Tool.schema()` drops `title` and `default` annotations and the long text of definitions. 0.4.x logs replay and export unchanged.

Also additive: a run ends at or below its cap, and a run that a limit stopped still answers.

- `CostBudget(prices=...)`, `TokenBudget(bound_input=True)` and `ProjectBudget` fit each LLM call
  before it is made: the input bound times the input price plus `max_tokens` times the output
  price. A call that passes the cap gets a lower `max_tokens`; one whose input does not fit is
  denied. Off when unset. Prices come from OpenRouter's public model list, fetched once per process
  with the context windows (`geomind.utils.models.fetch_prices`); a library caller fills
  `prices` with `await load_prices(models)`, which raises `ValueError` for an unpriced model.
  Fixes runs that overshot the cap by one call (9% of 0.50 USD, 63% of 0.01 USD in live tests).
- `answer_reserve` and `answer_agents` on the budgets keep an amount for the agent that writes the
  answer. No default; off when unset. A hook argument, not a `gd.runtime` setting.
- A delegate whose nested run a budget or `TimeLimit` stopped fails with the new tool error code
  `budget` and the message `<agent>: run <limit and what was spent of the cap>`, no longer `internal`.
- `TimeLimit(max_seconds)` denies an LLM call once the root run has run that long.
- A root run that stops on a budget, `TimeLimit` or the step limit gets an answer built with no LLM
  call from the problem state and the log (`geomind/engine/partial.py`), streamed like an answer;
  `stop_reason` and `status` are unchanged. `geomind export` shows it in a `## Stop` section.
  Logs of 0.4.1 and earlier, whose such stops have no answer, still load, replay and export.
- `ProjectBudget` reads `UsageLedger.spent` in a worker thread, as the docs said.

## [0.4.1] - 2026-11-02

Additive: models and OpenRouter providers can be chosen by deployment configuration.

- `GEOMIND_CHEAP_MODEL` sets `coordinator_model` and `summarizer_model` (else `FIXED_CHEAP_MODEL`),
  as `GEOMIND_MODEL` already sets `default_model`.
- New setting `provider`, from `GEOMIND_PROVIDER` (comma-separated OpenRouter provider slugs, for
  example `relace/fp4`): `OpenRouter` sends it as `provider: {"order": [...]}`. `None` sends nothing.
- `runtime.load_state` accepts a state stored before a setting was added (`ADDED_SETTINGS`); the new
  setting takes its default, so older runs still resume.

## [0.4.0] - 2026-11-02

Breaking (minor): `name` is now required on `run_study`, `sample_uncertainty` and `sensitivity`.
Additive otherwise: new tools, a new public event, a new hook and protocol; nothing renamed or
removed. Supports gemini `>=0.5,<0.6` (tested on 0.5.1).

- Every study tool (`size_plant`, `optimize`, `sample_uncertainty`, `sensitivity`, `run_study`)
  stores the chat artifact `study/<name>`, written once like `design/`: gemini's `study.json` that
  ran, its result, the designs read and written, the case id, the tool and the versions. `name` is
  now required on `run_study`, `sample_uncertainty` and `sensitivity`, and every study tool returns
  `study: "study/<name>"`. `studies.index` lists the chat's studies without listing artifacts by
  prefix, so `RunStore` is unchanged; `study` is a reference kind of `FileRunStore`.
- Fix: `run_study` stored every run as `design/<plant>_best`, so a second study over a design was
  refused as a changed design. A run is now stored as `design/<study name>_<plant name>`. A taken
  `name` of `optimize`, `size_plant` or a study is refused before the study runs, naming the taken
  design or study.
- New public event `study.recorded` `{run, index, call_id, study, tool, method, designs, best?}`,
  sent once after the artifact is saved; callbacks get `on_study_recorded`.
- New read tools `list_studies` (with `current`: the state's case is still the one the study ran
  on) and `read_study`, given to the Designer, Economist, Analyst and Explainer.
- Unknown event types: `events_from_dicts` skips a type this version lacks and
  `FileRunStore.load_events` uses it, so a newer log opens in an older reader. Every consumer,
  the backend included, must ignore unknown event types. `event_from_dict` still raises.
- `Context.call_id` and `Context.for_call`: a tool knows the call it serves.
- Replay of a log of another geomind version (or with none recorded) keeps the recorded results
  of pure tools, and still compares completions, calls, steps and
  answers: a 0.3.1 log with study calls (no `name`, other outputs) replays. Tools that write the
  state still run.
- A log of 0.3.1 without `study.recorded` loads, replays and exports. Recorded model calls of
  `run_study`, `sample_uncertainty` and `sensitivity` from 0.3.1 lack the new `name`, so the
  recordings of this repository carry one (`families`, `draws`).
- Fix: `Engine.replay` matches a run's recorded results by step and call id, not by call id alone.
  A model that reuses an id in a later step (`explainer/unverified`, `analyst/module_lookup`) no
  longer gets the input of the later call at the earlier step. New test replaying every eval
  recording.
- `UsageLedger` (`spent(project_id) -> Usage`), `MemoryUsageLedger` and `FileUsageLedger` in
  `gd.stores`; `gd.hooks.ProjectBudget(ledger, project_id, max_tokens=None, max_cost=None)` denies
  an LLM call once the project's finished runs plus this run reach a cap. No cap is
  `gd.errors.BudgetError`. Pass it in `gd.Run(hooks=[...])`.
- `geomind run --project-max-tokens` and `--project-max-cost`, valid with `--project`; a live
  `--mode auto` run still needs `--max-cost` or `--max-tokens`.

## [0.3.1] - 2026-11-02

Additive: a new optional event field and a stronger replay; nothing renamed or removed.

- `Engine.replay` replays every nested run of a loop run, not only the root: each nested run runs
  again with a `FakeLLM` of its own recorded completions, and its calls and answer are compared,
  so a difference names the run and its agent. The replayed log has the same runs, steps, LLM
  calls and tool calls. New keywords `replayed=` (a list that receives the replayed events) and
  `workspace=` (and `geomind replay --project`); a run with a project replayed without a workspace
  reuses its nested runs as before. 0.3.0 logs replay unchanged.
- `run.started` records `versions` (`geomind`, `gemini`, `python`) on every run, nested ones
  included; it is not streamed and `public_fields` is unchanged. A 0.3.0 log has none and still
  loads, recovers, replays and exports (the export falls back to `run_manifest.json`).
- The export header reads the versions from the log, so runs of the backend, chats, `gd.Run` and
  evals no longer show "not recorded".
- Fix: the export header showed the first user message of the run, a chat's oldest; it shows the
  last, the run's own request.
- `geomind replay` prints `nested runs reused: ...` when a run with a project is replayed without
  `--project`; a run that starts in a replay with no recorded run to follow raises `ReplayError`.
- `geomind replay` prints one line `versions differ: ...` when a version differs from the recorded
  one; `version_differences(events)` in `geomind.engine.replay` returns the difference.

## [0.3.0] - 2026-11-02

Breaking: geomind runs on gemini `>=0.5,<0.6` (pinned in `pyproject.toml`; a test fails on another
installed version). gemini's problem is a project folder (`case.json`, `economics.json`, `data/`,
`plants/`), pass or fail is `gm.evaluate.verdict`, and a plant is a file with ranges. geomind keeps
no copy of gemini's logic. `gm.evaluate.run_all`, `gm.physics.control`, `gm.data`, `gm.case.roles`
and `gm.plants.validate` are not used anywhere.

Problem state and backend contract:

- `Requirement.case_requirement` (the name of a requirement of the case, `str | null`) replaces
  `Requirement.constraint`; `ConstraintKey` is removed (schema `problem_state.json` and its sample).
- `case_origin` now compares the case's requirements by name (added, removed, changed) and its
  files, `economics.json` included.
- `Workspace.case(project_id)` returns `(case dict, {file name: bytes})` (was `(case dict,
  folder)`); the files are the ones `case.json` names, `economics.json` included, by relative
  name such as `data/demand.csv`.
- `Workspace.plant(project_id)` is removed. `Workspace.plants(project_id)` returns `{file stem:
  plant file dict}` from the project's `plants/*.json`, `{}` without plants. `MemoryWorkspace`
  takes `plants={project: {name: dict}}`; `FileWorkspace` reads the folder; `check_workspace`
  checks both. The backend implements `plants` and the new `case`.
- `RunStore.save_chat_artifact(chat_id, key, data)` and `RunStore.load_chat_artifact(chat_id,
  key)` are new (`FileRunStore` keeps `<root>/chats/<chat id>/artifacts/`; `check_run_store`
  tests them). Artifacts live in the chat, not in the root run: the case files (`case/<path>`), the
  designs, the results, the modules and the cut tool outputs are read by every later message of the
  chat. A run without a chat uses its root run id as the chat id. The per-run methods remain in the
  protocol. `FileRunStore` accepts the key kind `module/<file name>`.
- A design is written once: `design/<name>` with the same content is accepted, other content is a
  `ToolError` that asks for a new name.
- Replay falls back to the recorded chat's artifact space.

Tools:

- Added: `set_ranges(design, ranges, name, options=None)` (search ranges and options on a copy of a
  design, stored as `design/<name>`), `run_study(designs, method, objective=None, evaluations=None,
  seed=None, samples=None, metrics=None, prepare=None)` (one `gm.Study` over several designs,
  `method` is `run`, `minimize`, `sample` or `sensitivity`; each run's plant is stored as
  `design/<name>_best`), `write_module(name, code)`.
- `set_case(source, changes, requirements, economics)`: `requirements` and `economics` are new
  arguments; `save_profile` writes the demand file in one step.
- `read_case` sections `economics` and `schema` are new (the case, its economics or gemini's
  schema).
- `read_plant(design, plant_class, project_plant)`: `plant_class` and `project_plant` are new (at
  most one of the three; none reads the project's only plant file, several plant files need
  `project_plant`). It returns `{plant, ranges, options, issues, checked_against}`; `issues` is
  `gm.check(plant, case)` against the state's case (`checked_against: "case"`) or `plant.check()`
  (`"plant"`), and `missing_parameters` is gone. `ranges` are in display units.
- `build_plant(plant file, name)` builds with `gm.Plant.from_dict` (no `gm.plants.validate`),
  returns `{design, checked_against, issues}`, and a bad file is gemini's error.
- `list_plants` gains `roles` (`gm.plants.roles()`) and `project_plants` (the project's plant file
  names); `capabilities` carries `ranges`.
- `evaluate_module` returns display units (`units="display"`: MW, Pa for pressure) and takes
  `state` and `dt`; every inlet needs a `fluid`.
- `simulate` summary: `report`, `verdict` and `unmet` (requirement checks that failed); `constraints`
  and `violated` are gone. A window cuts the case's time too.
- `check_results` returns `{feasible, reasons, requirements, failures, metrics}`; `passed`,
  `constraints` and `balances` are gone. `feasible` and `reasons` are `gm.evaluate.verdict`.
  `gd.verify.verify(plant, results, case)` returns `{passed, checks, failures, metrics}`; a
  failure carries `kind`.
- `size_plant(design, name)` loses `backup` (the policy is `params.backup` of the plant).
- `optimize(design, objective, evaluations, seed, name)` loses `variables` and `constraints`:
  variables are the design's ranges (`set_ranges`), constraints are the case's requirements; `seed`
  is required.
- `sample_uncertainty(design, metrics, samples, seed)`: `count` is renamed `samples`.
- `compare` reads display values from each run's `Report.to_dict()`; no column labels are parsed.
- `test_module(name, example=None)` moved to `modules.py` and checks the stored `module/<name>.py`
  with `gm.modules.check` in the gemini sandbox (`gemini-sandbox:<gm.__version__>`, no network);
  it was `test_module(path)` over a file, a stub. A local sandbox is `not_allowed`. New skill
  `writing-a-gemini-module` flow: `write_module`, then `test_module`.
- Study tools: `shown_value`, `shown_values`, `to_quantities` and `check_plant_variables` are
  removed; the study tools time out after 900 s.

Agents and loops:

- `CompareLoop` is added (`geomind/loops/compare.py`, name `compare`): the Designer builds one
  design per plant family, `run_study` ranks them, then the design loop's Verifier, Economist and
  Explainer. `Route.loop` and `LOOPS` hold `tool`, `design` and `compare`; `geomind run --loop`
  takes `compare`.
- `MakerCheckerLoop` is removed.
- The Designer gains `set_ranges`, `run_study`, `write_module` and `test_module`; the Economist
  gains `run_study`; the Analyst gains `write_module` and `test_module`. The agent chooses a
  setting the request does not give (backup, objective, evaluations, seed, samples, ranges) and
  records it as an unconfirmed `agent` assumption.

Command line and evals:

- New `geomind check-live [--max-tokens N] [--max-cost USD]`: checks the role models against
  OpenRouter's public list and what a first live run needs.
- `geomind run --mode auto` with OpenRouter and no spending cap is refused; a recording is exempt.
- `geomind show --format md` is the competition export (`geomind/export.py`): the request, the
  versions and models, every LLM call with the messages added since the last call, each agent's
  prompt once, and the token tables by agent and step. Two runs of one recording export the same
  text.
- Eval task field `max_steps` (caps the steps of every agent, for a tight-budget task); new suite
  `compare`; `python -m evals.run --report` writes `evals/reports/summary.md` (a table per loop),
  and `--agent X` writes `evals/reports/X.md`.
- The eval projects are copies of gemini's examples in gemini's layout (`case.json`,
  `economics.json`, `data/`, `plants/`): `hackathon`, `hackathon_plant`, `shallow_district` and the
  variants `more_cooling`, `colder_reservoir`, `higher_gas`, `user_profile`. The old `doublet`
  project is removed.

## 0.2.0 (unreleased)

Breaking: geomind runs on gemini `dev` (cca153b8), whose problem is a `gm.Case` (`case.json` and a
demand CSV). gemini does every engineering job (checks, costs, sizing, search, uncertainty);
geomind keeps no copy of that logic and no default for an engineering assumption.

Problem state and backend contract:

- `ProblemState.case` (a case dict as `case.json` holds it, or `null`) replaces `ProblemState.brief`;
  `case` replaces `brief` among the keys a patch may change. gemini's `Case.from_dict` validates it.
- `Requirement` is `{id, text, constraint, status}`: a numeric requirement is a constraint of the
  case, and `constraint` names it by `{on, quantity, over, when}` (`ConstraintKey`), never by its
  place in the list. `metric`, `target` and `tolerance` are gone.
- `ProblemState.case_origin` (`{case, files}` or `null`): the case the user or the project gave,
  and `case_origin` among the keys a patch may change. `update_state` refuses `/case` and
  `/case_origin` (`not_allowed`); only the case tools write them.
- New protocol method `Workspace.case(project_id) -> (case dict, folder) | None`, implemented by
  `MemoryWorkspace` (`cases=`) and `FileWorkspace` (`<root>/<project>/case.json`), checked by
  `check_workspace`.
- Run-store artifact keys: `case/<file name>` (bytes, the files a case names) is added and
  `profile/<name>` is removed. A run keeps `<id>.results`, `<id>.plant` (the plant dict) and
  `<id>.case` (the case dict it ran on) and `<id>.files` (`{file name: sha256}`) beside
  `result/<id>`, and each case file once by its content as `<sha256>.file`; `<id>.run` is gone. An
  older run reads the files it ran on, not a file overwritten later under the same name, and the
  case and files it stores are the ones it read (`ran_case`), not the state's after a parallel
  `set_case`.
- Removed from `geomind.context`: `Brief`, `PRESETS`, `preset`, `with_changes`. No preset of any
  case is left in the package.

Tools:

- Removed: `set_brief`.
- Added: `case_changes()` and `accept_case()` (the design loop's driver only); `set_case` takes
  `source="origin"`.
- Added: `set_case(source=None, changes=None)` (a JSON merge patch on the case, `source="project"`
  for the project's case), `read_case(section=None)`, `size_plant(design, backup, name)`,
  `sensitivity(design, metrics)`, `compare(references, by)`.
- `save_profile(name, values, unit, start, step, service)` writes the profile into the case's demand
  file (`quantity` became `service`).
- `optimize(design, objective, variables, evaluations, name, constraints=None)` and
  `sample_uncertainty(design, metrics, count, seed)` are real (`gm.study.minimize`, `sample`), no
  longer stubs; `budget`, `samples` and `distributions` are gone (distributions are the case's).
- `simulate` loses `profile`: the demand is the case's. `read_profile(service, start, end)` reads
  the case's demand (`name` became `service`); `list_profiles` lists the case's services.
- `check_results` loses `limits` (a limit is a case constraint) and returns gemini's report;
  `estimate_costs` loses `assumptions` (they are the case's).
- `read_plant` returns `{plant, missing_parameters}` and reads a stored design, the project's plant
  or a gemini plant class; the `example/` and `template/` sources are gone. `build_plant` validates
  with `gm.plants.validate`. The input bridge `apply_inputs` is gone: `Plant.from_dict` restores
  inputs.
- `read_result` takes ISO times for `start` and `end`.

Verification: `gd.verify.verify(plant, results, case)` (was `requirements`, `limits`, `brief`);
pass or fail is gemini's report, and each failure carries the domain that should fix it.
`not_given`, `not_assessed`, the reservoir check and the operating-days reason are gone.
`verify_design` fails a result whose case differs from the state's (`result_off_case`), and a case
that differs from the one the user gave (`case_changed`, with the changes) until the user approves
it: the design loop asks, then accepts the case or sends the designer back to it. The Verifier
reports case changes, a stale result and unconfirmed assumptions, and the Explainer reads that
report and the case. The Designer and the Economist choose a study setting the request does not
give (backup, objective, variables, evaluations; count, seed) and record it as an unconfirmed
`agent` assumption with its reason, instead of stalling; the Designer records
`design.start_result` and `design.alternatives`, and the Economist compares only those.

Routing: `Route` loses `brief` (nothing read it; the loop reads the user's message), and
`Route.loop` and `LOOPS` hold only the built loops, `tool` and `design`, so a live request is never
routed to a stub; `geomind run --loop` takes the same two.

Agents and loops: the design loop's request is the run's own message (the last user message), not
the first message of the chat, and `Run.load` keeps a design loop's `max_rounds`. The hackathon
skill note is gone. The DesignLoop runs Designer (size, simulate,
self-check, optimise) → Verifier (once, on the final design) → Economist → Explainer, and asks the
user for a case before designing when the state has none or it has no demand.

Tools: `optimize` refuses a `case` variable (the case is the user's); the study tools time out
after 900 s with a `timeout` result; `compare` keeps gemini's own value when a column label is not
`name [unit]`, instead of failing. A file the project's case names but does not have is an `unknown_name` error that names
it, and an empty case file is a file, not a missing one.

Tests: no fast test of a gemini tool runs a year in its body; module fixtures run each year,
window and tool call once and cache it, so the 1 s budget holds under parallel load.

Evals: eval projects are copies of gemini's example cases (`evals/projects/`); `challenge2` tasks
are case variants. The eval schema and recordings follow the new tools.

## 0.1.1 (unreleased, superseded by 0.2.0)

Additive changes only: a new key of the problem state, a new tool and new output fields. Nothing the backend uses
changes shape, and an existing caller sees the same behaviour.

- `ProblemState.brief`: a `Brief` (or `null`), the brief as data, and `brief` among the keys a
  patch may change. The backend stores it with the state; an older state without it loads as
  `null`. `geomind.context` exports `Brief`, `PRESETS`, `preset` and `with_changes`; the one preset
  is `hackathon_2027`.
- New tool `set_brief(preset=None, changes=None)` (effect `write`).
- `simulate` and `check_results` use the state's brief; without one they keep the hackathon numbers
  as before. `simulate`'s summary adds `brief`, `demand` and `rules`, and its result id now covers
  the rules. `check_results` and `gd.verify.verify` add `not_given` and `brief`; `verify` takes
  `brief=None`.
- New tool `save_profile` (effect `write`): a demand profile the user gave, stored as
  `profile/<name>` in W. `list_profiles` and `read_profile` include stored profiles, and
  `simulate` and the brief's demand take them. A store must accept the key `profile/<name>`;
  `check_run_store` tests it.
- Verification checks each doublet against the reservoir values the brief gives, and
  `verify_design` fails a result that ran on another demand or rules than the brief's
  (`result_off_brief`); `simulate` keeps `<id>.run`.
- The eval format adds the `verified` criterion and `equals` on the `state` criterion; the suite
  `challenge2` runs through the design loop.
- `Usage.cached_tokens`: input tokens read from OpenRouter's prompt cache, which an Anthropic
  model now gets on the agent's system prompt (setting `prompt_caching`, on by default). The
  public usage JSON of `step.finished` and the run log keeps its three fields; the schemas list
  the new one as optional.
- `geomind run --max-tokens N --max-cost USD`: a spending cap over the whole run. `TokenBudget`
  and `CostBudget` now count the runs above a nested run too (a fix: before, a delegate saw only
  its own usage, so a long delegate could pass the cap).
- `RunResult.usage` includes the routing call's tokens, as the run's log always did.

- `geomind run` takes `--loop`, `--project`, `--recording` and `--record`: `--loop` chooses the loop
  and skips the routing, `--recording` runs from recorded completions and `--record` writes them.
- `gd.Run.start` asks the `Coordinator` first when no agent or loop is given; the routing call is a
  nested run of the run, logged before it starts. The backend still names no loop and no agent.
- `read_plant` reads `example/<Name>` and `template/<name>` and returns the plant's spec beside its
  description; `check_results` returns `failures` and `not_assessed` beside `passed` and `checks`;
  `estimate_costs` returns `lcts`.

## 0.1.0 (2026-10-31)

The first frozen state.

- Every interface the backend and the agent developer depend on is pinned by snapshots in
  `tests/unit/snapshots/`, and the exchanged documents have JSON schemas and samples in
  `geomind/schemas/`.
- The full tool catalogue up to S4 exists; tools not built yet raise `gd.errors.NotImplementedYet`
  and give an error result with `code: "not_implemented"`.
- Tool error results take gemini's Problem shape, `{"error": {path, code, message, suggestions}}`.
  The former `{"error": {class, message}}` is gone.
- `read_result` returns gemini's Value shape, and a summary without `path` or `field`.
- `LOOPS` holds `tool`, `design`, `makerchecker` and `compare`; a route to a loop not built yet ends
  the run with `stop_reason="not_implemented"`.
- `gd.verify.verify` and `gd.hooks.Verified` have their final signatures.
- `FileWorkspace.plant` loads through `gm.plants.from_dict`, and `FileRunStore` accepts the artifact
  keys `design/<name>` and `result/<id>`. `gd.testing.check_run_store` now checks them.

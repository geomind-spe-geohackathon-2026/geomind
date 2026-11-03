# Changelog

`gd.__version__` follows semver below 1.0, the same rule as gemini: a breaking change to a frozen
interface raises the minor version, and an addition or a fix raises the patch version. The rule and
the list of frozen interfaces are in [.claude/docs/api.md](../.claude/docs/api.md#frozen-interfaces).

## [Unreleased]

### The analysis team, C

Round C1 (Track C): the analysis lead and the economist alone, two tasks each, on the C1 case and the D-round design (`HackathonPlant` on it), live (DeepSeek), 0.028 USD: 2 of 4 passed, each number checked against gemini's own.

- Prompts: the analysis lead and the economist carry a gemini reference made when the prompt renders (`geomind/agents/analysis/reference.py`): every metric of `gm.evaluate.metrics()` with its title, display unit and whether a study may minimise it, and the economics keys with units and meanings. A test pins gemini's objectives (`annualised_cost`, `lcts`, `lcoh`, `lcoc`, `co2`) and checks that every metric the prompts cite is gemini's.
- Prompts: the economist has `read_case` (its prompt sent it to the case's economics without the tool), names metrics as gemini does, reports a breakdown and a comparison as gemini gives them (ranks and both values, never a difference, a share or a sum it worked out), and reports a missing price with its economics path. The analysis lead no longer chooses a time zone alone, and gives gemini's values side by side instead of a share.
- Fix (#85): the economist runs uncertainty and sensitivity only when the task asks for them.
- Fix (#86), evals: the `sourced` criterion reads the problem state's `Case:` line. Evals: the `number` criterion reads a thousands separator (`111,667.68 MWh`).

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

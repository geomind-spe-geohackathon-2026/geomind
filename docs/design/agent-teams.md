# geomind agent teams (proposal, 2026-11-03, not built yet)

Status: discussed with Sahand. Nothing is built until he says so.
Every model agent runs on DeepSeek and has its own required model setting (no default).
gemini does every number (calculation, check, unit conversion). Agents never compute.

## Flow

1. The user sends a task from chat or the UI. The **Coordinator** gives it to **ProjectLead**.
2. **ProjectLead** plans which teams work, in what order, and what passes between them.
3. **Case team**: the case (site, demand, requirements, economics) is complete and confirmed by the user.
4. **Design team**: the plant is built step by step, reviewed by DesignLead, then sized, simulated and optimized.
5. **Analysis team**: costs, KPIs, sensitivity and uncertainty, plus improvement proposals back to the Design team.
6. **Reviewer**: an independent check from scratch. A failure goes back through ProjectLead to the team that owns it.
7. **Explainer**: the final report for the user.

Each lead checks its members' work and returns every problem to its owner with the reason.
Only approved results reach ProjectLead.

## 1. Project team (lead: ProjectLead)

| Agent | Kind | Duty | Gets | Gives |
|---|---|---|---|---|
| ProjectLead | model (new; replaces the DesignDriver's decisions) | Plans the work across teams, chooses the next team, sends failures to their owner, decides when to ask the user, stops at a good design or at the budget | the task, team reports, gemini verify_design results, run log | the next team task with a brief, ask_user, finish |
| Coordinator | model (existing) | Reads each user message or UI action, turns it into a task (see the task list), answers short questions directly | the chat or UI event | a task for ProjectLead or a short answer |
| Reviewer | model (Verifier renamed) | Checks the finished design from scratch, independent of the Design team. Past designs and memory don't count as evidence | the final case, plant, results, gemini checks | pass or fail, with failures sorted (subsurface / surface / sizing / coupled / case) |
| Explainer | model (existing) | Writes the final explanation: design, assumptions with sources, costs, checks | the approved design and analysis | the report text |

Guards stay in code, under ProjectLead: budget cap, step limit with continue/stop, max output per call, stopping repeated identical failures, and gemini's failure sorting as a hint.

## 2. Case team (lead: CaseLead, was Formulator)

| Agent | Kind | Duty | Tools |
|---|---|---|---|
| CaseLead | model (Formulator renamed) | Defines the problem: demand, site, utilities, requirements, economics. Loads the project case.json by rule. Builds the rest from the user's words, the files, knowledge memory, then proposals. Asks ONE confirmation for every value not from the user's files, with source/year/price year/link or the reason | read_document, search_documents, read_case, set_case, search_memory, read_memory, ask_user |
| Geoscientist | model (new) | Extracts ground and reservoir data from the reports (temperature, gradient, layers, permeability, fluid/brine and dissolved gas) with page references, and marks uncertain values | read_document, search_documents, search_memory; gives proposed site.ground / site.reservoir / site.fluid values to CaseLead |

## 3. Design team (lead: DesignLead, was Designer)

Plants are built step by step: header and type first, then one module's values per patch (patch_plant). Nobody sends the whole plant in one call.

| Agent | Kind | Duty |
|---|---|---|
| DesignLead | model (Designer renamed) | Gives the work to the subteams, reviews everything before sizing (modules against the case, wiring against modules, every value's source or reason), owns coupled issues (well flow and temperature against surface capacity), runs size / simulate / optimize, asks CaseLead for case changes ("case change needed") |
| ReservoirEngineer | model (new), subsurface | Number of doublets, well spacing, flow rate, pressure and reservoir cooling over the plant's life |
| WellEngineer | model (new), subsurface | Well depth and design, ESP pump, drilling-related parameters |
| ProcessEngineer | model (new), surface | Chooses the modules AND their connections together (the PFD), heat exchangers, brine loop, reinjection, dispatch/control. Uses experience memory as a starting point only |
| EnergySystemsEngineer | model (new), surface | Heat pump, chiller, backup boiler and storage parameters |

Order: ProcessEngineer and ReservoirEngineer set the layout, then the specialists fill their modules' values at the same time (parallel, bounded by an explicit setting). DesignLead reviews, then sizes and simulates.

## 4. Analysis team (lead: AnalysisLead, was Analyst)

| Agent | Kind | Duty |
|---|---|---|
| AnalysisLead | model (Analyst renamed) | Analyses results, sensitivity, uncertainty, compares designs or families, and sends improvement proposals to DesignLead (DesignLead applies them, optimize stays in the Design team) |
| Economist | model (existing) | CAPEX, OPEX, NPV, LCOH with gemini; cost values from knowledge memory with sources |

## 5. Support and shared rules

- Support team (lead: SupportLead, Sahand 16:10): SupportLead (model, new) takes support requests from the other leads, gives them to its members and checks the result before it goes back. Members: Summarizer (shortens long histories).
- Removed (Sahand 16:00): Assistant. The Coordinator answers short general questions itself.
- Removed (Sahand 16:00, "we don't write code"): CodeAssistant and every code-running tool from all agents: run_python, the code sandbox (local and docker), write_module and test_module, their settings and tests. The CHANGELOG lists each removal for the later backend update.
- Also removed: FamilyDesigner (DesignLead with a fixed family does this). Rule agents ComparisonDriver / CompareDriver move under ProjectLead.
- Shared memory for all agents: knowledge (sourced data) and experience (approved designs only, written by code). Anti-overfit rules apply.
- Every value not from the user's files is confirmed by the user, with its source or reason.
- No defaults anywhere; missing means an error or a question.

## Memory per agent (Sahand 15:59)

Memory has two parts. Every entry records where it came from.
- **knowledge**: reference data with sources. It comes from the cost catalogue, from what the USER gives (a fact typed in chat or an uploaded file the user says to keep, origin "user", no extra confirmation needed), and from sources an agent found that the user then confirmed.
- **experience**: what the team learned over time. Approved designs are written by code only after the Reviewer passes them. General lessons are tagged by role: what failed and why, what worked. Project numbers are not stored as rules.

| Agent | knowledge | experience (lessons for its own role + team) | writes |
|---|---|---|---|
| ProjectLead | read | read: which order of work and which handovers worked | lessons on planning (via code at the end of a run) |
| Coordinator | no | read: user preferences (e.g. display units, style) | user preferences the user states |
| Reviewer | read (references only) | NO: must stay independent | none |
| Explainer | read (for citing sources) | no | none |
| CaseLead | read + search | read: similar past cases and which values users changed | user-given facts (origin user); confirmed values |
| Geoscientist | read + search | read: how data was found in similar reports | none (proposes to CaseLead) |
| DesignLead | read | read: approved designs for similar cases (start point only) | review lessons |
| ReservoirEngineer, WellEngineer, ProcessEngineer, EnergySystemsEngineer | read + search (equipment data, costs) | read: lessons for their own role | none directly; their lessons are kept when the design passes |
| AnalysisLead | read | read: past comparisons and sensitivities | analysis lessons |
| Economist | read + search (cost catalogue) | read: past cost results | none |

Rules: experience is a starting point, never an answer (always re-simulate and re-check); only for similar cases, with the similarity shown; at least one different option is tried; the Reviewer never uses experience; final and competition runs use empty memory (GEOMIND_MEMORY=off).

## Open points

- Should brine/fluid chemistry (degassing, scaling, CO2) be its own role, or stay with the Geoscientist (proposal: with the Geoscientist)?
- Should the network engineer be a separate role? gemini has no network modules yet; demand is in the case.
- HSE/permits stay with CaseLead (requirements).

## Folder layout (Sahand 16:05)

`geomind/agents/<team>/<agent>.py`, with the prompts and the tests mirroring it:

```
geomind/agents/
  project/   project_lead.py, coordinator.py, reviewer.py, explainer.py
  case/      case_lead.py, geoscientist.py
  design/    design_lead.py, process_engineer.py, integration_engineer.py,
             reservoir_engineer.py, well_engineer.py, energy_systems_engineer.py
  analysis/  analysis_lead.py, economist.py
  support/   lead (SupportLead), summarizer.py
geomind/prompts/<team>/<agent>.md   (plus skills/)
tests/unit/agents/<team>/
```

Rules: one-word folder names, the same as the team; file name is the class name in snake_case;
one file and one prompt per agent; the public import does not change (gd.agents.CaseLead);
every file keeps its mirrored test.

Note: connecting the modules is its own role, IntegrationEngineer (piping/integration), so the
three plant jobs each have an owner: ProcessEngineer selects, IntegrationEngineer connects, and
the three discipline engineers set parameters in parallel.

Draft role prompts for review: prompts-draft/role-prompts.md


## 2026-11-03 16:11 UTC (GEOMIND II)
Sahand approved: support/curator (Curator, model) writes per-role lessons into experience memory at the end of a run; approved designs still written by code after the Reviewer passes. Sahand said START; implementation runs on the NTNU Dell.

## 2026-11-03 20:40-21:00 UTC (GEOMIND II), built on dev
- Flat layout (Sahand 20:39), d1611e9: geomind/agents/<team>/<name>.py, prompts in geomind/prompts/<team>/<name>.md, tests in tests/unit/agents/<team>/test_<name>.py. project/ also has review.py, drivers.py and comparison.py.
- Superstructure + evolve_structure (Sahand 20:36), 457ce35: ProcessEngineer marks `optional` modules and `choices` groups (plant-file keys from gemini 0.6.1). DesignLead runs gm.study.evolve (GEOMIND_EVOLVE_EVALUATIONS/_POPULATION/_SEED/_POLISH are required). There is no separate design per family.
- gemini 0.6.1 pinned (edc8b6c). No end-to-end runs until Sahand says so (20:39).

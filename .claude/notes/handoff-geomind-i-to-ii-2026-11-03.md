# GEOMIND I -> GEOMIND II handoff (2026-11-03 16:10 UTC)

Work runs on the NTNU Dell through Remote Control, repo `~/geomind-work/geomind`.
Only geomind. No backend, no frontend, no prod. DeepSeek only. gemini is read-only.

## Where the code is

- dev at 0.4.22.dev23 (last commit 6f3650a). main / last release v0.4.21. gemini pinned 0.5.13.
- Live-loop spend about 1.66 of the 5 USD cap. 41 bugs found, 41 fixed, each with a test.
- Bug ledger and run table: `/mnt/project-files/geomind/live-test-bugs.md`.
- Team structure with every agent's duties and memory access: `/mnt/project-files/geomind/agent-teams.md`.
- Draft role prompts (engineering knowledge per role, no project numbers): `/mnt/project-files/geomind/prompts-draft/role-prompts.md`.
- Flow diagram of a design: `/mnt/project-files/geomind/design-flow.png`. Older one: `agent-flow.png`.

## Built on dev (not released)

Formulator (case from chat and files, project case.json loaded by rule, one confirmation of
non-file values with sources, assumptions with citation); Designer reads the case only and hands
over "case change needed"; key trees built from gemini schemas (case+economics, plant, study)
with a coverage test; compact describe_module and compact plant issues; shared memory (knowledge
with the cost catalogue copied into `data/knowledge/`, seeded by `geomind memory seed`;
experience written by code after verification; anti-overfit rules); continue/stop at the step
limit; `geomind resume`; `--replay/--replay-steps`; required settings with no default
(MAX_STEPS, MAX_OUTPUT_TOKENS, MEMORY*, FORMULATOR_MODEL, retries); `patch_plant` for
small-step plant building; build_plant's schema now names gemini's plant keys (#41).

## Decided with Sahand, NOT started (wait for his "start")

Four teams, each with a lead. Folders `geomind/agents/<team>/<one-word>/{agent.py,prompt.md}`,
tests mirrored, class names kept in full, public import stays `gd.agents`.

- `project/`: lead (ProjectLead, model, with the code guards kept), coordinator, reviewer
  (Verifier renamed, independent, knowledge only), explainer (knowledge only)
- `case/`: lead (CaseLead = Formulator renamed, HSE as requirements), geoscientist (new)
- `design/`: lead (DesignLead = Designer renamed, reviews the assembled plant after gemini's
  check, owns coupled issues, size/simulate/optimize/study), process (module choice),
  integration (connections/ports), reservoir (incl. degasser and brine-cooling limit), well,
  energy (incl. network). The last three fill parameters in parallel through `patch_plant`,
  bounded by a required concurrency setting. Each problem goes back to its owner.
- `analysis/`: lead (AnalysisLead = Analyst renamed), economist
- `support/`: lead (SupportLead, new, Sahand 16:10: takes support requests from the other leads, routes them to its members, checks the result), summarizer

Removed: Assistant, CodeAssistant, FamilyDesigner, run_python and the sandbox, write_module,
test_module. Every model agent gets its own required model setting `GEOMIND_<NAME>_MODEL`, no
fallback. Case/Design/Analysis get knowledge + experience (user facts with origin "user",
per-role lessons); Reviewer and Explainer get knowledge only; Coordinator remembers user
preferences.

Order: (1) renames, removals and the folder layout, (2) Geoscientist, (3) Design team agents,
(4) ProjectLead, each with tests and its own commit. Then a live test with replay, numbering
bugs from #42. Then MCP (`GEOMIND_MCP_SERVERS`, server-prefixed tool names, values confirmed
with their origin). Finally one full run with memory off, the full suite, an annotated release
and a version for the backend. The CHANGELOG lists every contract change for the backend.

## Open for Sahand

- A gemini item waiting for his OK: `gm.Plant.from_dict` raises `KeyError('')` instead of a
  ValidationError when a plant file's inlets give a bare value
  (`gemini/plants/_utils/ports.py`, `_check_reach`). Listed in
  `/mnt/project-files/notes/geomind-gemini-needs.md`, not sent.
- He has not said "start" yet. The Dell is idle and waiting.


## 2026-11-03 16:11 UTC (GEOMIND II)
Sahand approved: support/curator (Curator, model) writes per-role lessons into experience memory at the end of a run; approved designs still written by code after the Reviewer passes. Sahand said START; implementation runs on the NTNU Dell.

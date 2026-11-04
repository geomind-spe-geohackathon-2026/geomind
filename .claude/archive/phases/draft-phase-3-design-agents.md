# geomind S3: Design agents and verified loops (Challenge 2)

## Goal

Given a design brief (site, heating and cooling demand, constraints), geomind designs an integrated deep-geothermal heating and cooling system and proves it with physics before showing it.

## Context

- Follow the shared rules in `../docs/phases.md` (section "Rules for every phase") and the contracts in `../docs/contracts.md`.
- Needs S2. Read `../docs/agent-engineering-layers.md` (loop engineering), gemini's `equipment.md`.
- The competition inputs (released 2026-10-29) go in `evals/tasks/challenge2/`.

## Steps

### 1. Check gemini's modules

A heating and cooling plant needs: doublet (reservoir, wells, ESP), heat exchanger, heat pump, absorption chiller, compression chiller, hot and cold storage, peak boiler, network, heating and cooling demand, and economics (capex, opex, LCOH, CO2). For each one gemini lacks, stop and report it with a short spec. No physics is written in geomind.

### 2. Verifiers

`core/verify/`, one file per check, each returning pass or fail with a message that tells the agent how to fix it:

- `balance.py`: mass and energy balances close at every time step.
- `demand.py`: heating and cooling demand covered every hour, or the shortfall is reported.
- `bounds.py`: every value inside its module's bounds.
- `units.py`: no unit mismatch between connected modules.

Verifiers read gemini results only and never call an LLM.

### 3. Agents

`core/agents/<category>/<name>.py`, each with its prompt in `core/prompts/`:

| Folder | Agent | Job |
|---|---|---|
| `coordination/` | `Coordinator` | already exists; now also picks the design loops |
| `design/` | `Designer` | proposes configurations and sizes |
| `analysis/` | `Analyst` | runs simulations and reads results |
| `verification/` | `Verifier` | runs the verifiers, reviews the design |
| `economics/` | `Economist` | capex, opex, LCOH, CO2 through gemini |
| `reporting/` | `Explainer` | writes the explanation for the user |

### 4. Loops

`loops/`:

- `design.py`: `DesignLoop`. Goal = the brief with testable criteria; step = propose or change a design; observe = simulate and verify; stop = all criteria met, budget, step limit, the same check failing repeatedly, or a question for the user.
- `makerchecker.py`: `MakerCheckerLoop`. The designer proposes, the verifier checks, until it passes or a limit is reached.

Every stop reason is explicit and logged. No design reaches the user without passing all verifiers.

## Done when

- `geomind run --loop design <brief>` returns a verified design with capacities, a schematic description, numbers and an explanation.
- The challenge brief passes all verifiers.
- Docs describe verifiers, agents and loops.

## Report back

The design and its numbers, missing gemini modules, verifier failures seen during runs, and token cost.

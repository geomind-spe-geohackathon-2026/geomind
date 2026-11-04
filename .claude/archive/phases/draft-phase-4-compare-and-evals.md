# geomind S4: Compare alternatives and the eval report

## Goal

geomind compares design alternatives, ranks them, and the eval report shows with numbers which loop works best. This is the evidence for the competition report and video.

## Context

- Follow the shared rules in `../docs/phases.md` (section "Rules for every phase") and the contracts in `../docs/contracts.md`.
- Needs S3.

## Steps

1. **`loops/compare.py`:** `CompareLoop` runs `DesignLoop` for several alternatives (for example cooling by heat pump, absorption chiller or compression chiller; with or without storage) in parallel, and ranks them on the brief's criteria (cost, CO2, demand coverage).
2. **Uncertainty (bonus):** run the chosen design over a few reservoir and demand cases and report the spread.
3. **Eval tasks:** `evals/tasks/challenge2/`: the official brief plus three variants (more cooling, lower reservoir temperature, tighter budget).
4. **Eval report:** compare `ToolLoop`, `DesignLoop`, `MakerCheckerLoop` and `CompareLoop` on all challenge tasks: criteria met, verifier failures, steps, tokens, cost, time. Write `evals/reports/summary.md` with the table.
5. **Run export:** `geomind show <run> --format md` writes the agent log in the form the competition asks for: prompts, answers, token usage.

## Done when

- `geomind run --loop compare <brief>` gives two or more verified designs, a ranking and an explanation.
- `evals/reports/summary.md` holds the comparison table.
- One full challenge run is exported as Markdown.

## Report back

The ranking, the eval table, total token cost, and anything worth showing in the video.

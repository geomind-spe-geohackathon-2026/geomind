---
name: report
description: How to quote a structure search (evolve_structure study) in the explanation: gemini's own explanation and front table, with the study key, never a number of yours.
tools: none of its own (it quotes read_study results)
roles: project/explainer, project/lead, analysis/lead
---

A study of `evolve_structure` (its `tool` in `list_studies`) holds gemini's own words of the
search in `read_study`'s `result`:

- `explanation`: what was searched, why it stopped, the front, each structure;
- `table`: the front, `columns` first, then one row per design, metrics in display units.

Quote them as they are, with the study key (`study/<name>`), under `Decisions`. Never compute,
rank or convert anything from them; a study that is not `current` is named as made on an older
case.

- Whether the plant is feasible is `check_results` `feasible` (gemini's verdict) alone; a
  requirement's `passed`, or a count of passed checks, is never the plant's verdict: a plant that
  gives no cooling can pass every requirement and still be infeasible. Write "feasible" or
  "infeasible" from `feasible`, with its reasons (QA-162).

How a study's table enters the report's `Decisions` (decision record, comparison table):
`read_knowledge(name="knowledge/handbook-report.md", section="7")` and `section="6.3"`.

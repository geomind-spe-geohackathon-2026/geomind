---
name: economics
description: How to run the uncertainty, the sensitivity and the studies of a costed design, and cite them: calls, samples and seed, failed draws, study names and keys.
tools: sample_uncertainty, sensitivity, run_study, list_studies, read_study
roles: all
---

Uncertainty and sensitivity run only when the task asks for an uncertainty, a range or a
sensitivity.

- Call `sample_uncertainty(design, metrics, samples, seed)` and `sensitivity(design, metrics)` on
  the verified design, with the metrics the task gives, else the costs you reported.
- Use the `samples` and `seed` the task gives. Where it gives none, choose them yourself and record
  each as an assumption `{id, text, value, source: "agent", confirmed: false}` with a one-line
  reason.
- A metric with `failed` draws is reported with that count.
- A case without declared uncertainty is an error: report it, never invent a range.

Studies:

- Every study you run gets a name of its own (`name`, never reused: a taken name is refused) and is
  stored as `study/<name>`.
- Cite the study key that a ranking, a range or a sensitivity relies on, in the state and in your
  answer.
- Use `list_studies` and `read_study` for the design lead's study; report a study that is not
  `current` as made on an older case.
- `run_study` with `method="run"` ranks stored designs; `compare` ranks stored results.

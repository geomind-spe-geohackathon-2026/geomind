---
name: comparing-designs
description: How to compare designs: a superstructure (union_designs, evolve_structure) and its front, or several families in one run_study; how to pick the design and cite the study.
tools: union_designs, evolve_structure, run_study, read_study, list_studies
roles: all
---

Superstructure (more than one sensible way to meet a service, in one design):

- Read the union's `structures` and `notes` before `evolve_structure`: a note is a value the
  alternatives state differently, where gemini kept the first and widened its range.
- After your review, call `evolve_structure` on the merged design with the objectives the case or
  your brief names, never ones you choose.
- Read the front and `rejected` (a structure gemini refused, with its reasons, such as a port left
  open). Take the best feasible design on the first objective, or the trade-off the brief asks
  for, and say why, quoting `stopped` and `why`; for more, `read_study`'s `explanation` and
  `table`, as gemini gives them, never computed.

Several families:

- Size each and compare them in one `run_study`: `designs`, `method="minimize"`, `objective`,
  `evaluations`, `seed`, `prepare=["size"]`.
- Keep the feasible design it ranks first (`best`), `simulate` it for the whole year, take it as
  final.
- Record the study in `design.study` as returned, and cite its `study/<name>` in
  `design.study.key` and in your answer. Every study has a new name.

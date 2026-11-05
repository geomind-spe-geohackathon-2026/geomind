---
name: memory
description: How to read and keep lessons across runs: search_memory, read_memory and write_lesson.
tools: search_memory, read_memory, write_lesson
roles: all
---

## The tools

### `read_memory`

Return one experience entry by the id `search_memory` gave.

### `search_memory`

Return what the team learned before: designs that passed on alike cases, and lessons.

`experience` holds past designs whose case is at least the `memory_similarity` setting
alike to the state's case, each with its `similarity`: a starting point only, never a
result. `lessons` holds the general lessons of your role and the facts the user gave; the
curator's holds every role's, so it writes no lesson twice.
Cited values are not here: search the knowledge base (`search_rag`).

### `write_lesson`

Keep the run's lessons for roles, and the facts the user gave, in the memory's experience:
one call with the list `lessons` of every entry, so the user approves them on one card. At
most three entries a run; an entry the user denied earlier, under any id or role, is refused.

Each entry is `{id, kind, role, text, source}`.

A `lesson` is method for `role` (an agent's snake name such as `design_lead`, or
`all`) in words, with no number: a project's values never become a rule. A `user_fact`
is what the user said (`source` `user`), such as the units they read. `source` says
where it came from: `user`, `reviewer`, `gemini` or the agent that learned it. Past
designs are written by code alone, after the reviewer passed them.

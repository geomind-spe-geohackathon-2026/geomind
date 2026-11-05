---
name: working-in-a-team
description: How to record work in the problem state, ask the user and hand back: update_state, ask_user, finish and read_skill.
tools: update_state, ask_user, finish, read_skill
roles: all
---

## The tools

### `ask_user`

Ask the user a question and wait for the answer, with fixed options if there are any.

With `options` the user picks one option's value or types an answer of their own, which
comes back marked as typed. To ask for something typed (a path, a number with its unit, a
name), ask without options. Every answer is kept in the problem state as a confirmed user
assumption (`answer.<id>`) that every later agent reads: read the state first and never ask
a question it already answers; act on that answer instead.

### `finish`

End the run with the final answer.

### `read_skill`

Return the instructions of one skill, by its name in the system prompt.

`<skill>/<file>` reads a file the skill names.

### `update_state`

Change the problem state with JSON Patch operations (add, replace, remove).

Paths are JSON Pointers under goal, requirements, assumptions, design, results, verification
or questions; the case is set only with set_case. Items of requirements, assumptions, results
and questions are addressed by id, as in /assumptions/A1/confirmed, never by position;
add to /requirements/- appends an item that has an id. A requirement has id, text, status and,
when a requirement of the case judges it, case_requirement: that requirement's name. An
assumption has id, text, value, source (user, agent or default) and confirmed; a result id,
summary, reference; a question id, text. A rejected change names the shape expected there.

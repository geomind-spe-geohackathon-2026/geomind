---
name: working-in-a-team
description: How to record work in the problem state, ask the user and hand back: update_state, ask_user, finish and read_skill.
tools: update_state, ask_user, finish, read_skill
roles: all
---

## Parallel instances

A team tool (`geoscientists`, `fill_parts`) runs its briefs at the same time. Its `briefs` is
either `{member: task}`, one run per member, or a list of `{role, task}`, one run per entry, so
several instances of one role work at once. Each instance is named `<Role> <Roman numeral>`
(`Geoscientist I`, `Geoscientist II`) and its answer comes back under that name.

- Split the work so each instance owns distinct fields (for the case: ground and reservoir;
  brine and gas; another report), and say in each brief which files to read and which keys it
  owns. Two instances never propose or write the same key.
- Send every brief in ONE call: the instances run together, and the call ends when the last
  one answers.
- Read every answer, merge them, check what is still missing or disagrees, and send a second
  call only for that.

Example: `geoscientists(briefs=[{"role": "geoscientist", "task": "Ground and reservoir
(site.ground.*, site.reservoir.*) from report.pdf"}, {"role": "geoscientist", "task": "Brine and
dissolved gas (utilities.brine.*, utilities.gas.*) from report.pdf and fluid.pdf"}])`.

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

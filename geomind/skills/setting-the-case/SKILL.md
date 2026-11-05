---
name: setting-the-case
description: How to set and read the case with its tools: set_case, read_case, describe_case, profiles, accept_case, case_changes and ask_economics; arguments, forms, common mistakes.
tools: set_case, read_case, describe_case, save_profile, list_profiles, read_profile, accept_case, case_changes, ask_economics
roles: all
---

## The tools

### `accept_case`

Make the state's case the one the user gave, after the user approved its changes.

Only the design loop's driver holds this tool, after the user answered its question.

### `ask_economics`

Ask the user the ONE economics question from the rows you chose, and set what they approve.

Send only the exceptions: every economics key of the cost catalogue you do not name goes in
with its recommended row (sourced, verified, no upper bound or proxy, the latest year; a
real discount rate) and its other rows in `others`; a key with only placeholder rows is
open. Name a key to recommend another row (one of the site's country), to put it in `open`,
or with a value from a server or the user.
`values` holds each economics key with the row you recommend: `key` its path under
`economics` (`capex.heat_pump`, `energy.electricity`), `row` the catalogue row `id`
and, for a key whose rows differ, `others`, the ids of the rows you did not recommend
(`["drilling-nl-2013-2300m"]`). Send only ids: this tool reads each row's value, unit,
source, year, url and status from the knowledge base itself, so never copy them (copying
every row ran past the output limit). `value` with `source` (and `unit`, no `row`) is
for a value a knowledge document or a project file states (an assumptions document of the
case: `source` `knowledge/<name>` with its section), an MCP result or the user. `discount_rate` is a key too, in `values` or in
`open`. A value from a catalogue row is its `value_2015` in
`unit_2015`, EUR at 2015 prices, so this tool sets `currency` EUR and `price_year` 2015
itself: leave both out (without any row, name each in `values` or `open`). A row's unit
goes as the row writes it (`EUR/W electric`); a unit its key does not take is refused,
every one at once, before the user is asked. `open` names the keys no usable row gives, each
key once in `values` or `open`; `note` one line for the user. A field with
nothing to say is null or left out; a key whose value is null is open. The question's
options are approve all, change some and stop, and the user may type an answer instead. On
approve all, every value is set in the case's economics (`set_case`) with its row in
`about.sources`, and each becomes a confirmed assumption with its citation; the result says
what was set. On change some, ask which values change and to what, without options.

### `case_changes`

List how the state's case differs from the case the user or the project gave.

Each item has `path` (a section, `section.key`, `requirements.<name>` or `file <name>`),
`change` (`changed`, `removed` or `added`) and the `given` and `now` values. An
empty list means the case is the one the user gave. A design is verified only on that case:
any difference waits for the user's approval.

### `describe_case`

Say what each key of the case or its economics under `path` means, with its units.

`path` is a dotted key or a part of one, such as `site.air`, `demand.cooling`,
`requirements` (also what each option means) or `economics.capex`. Returns `keys`, one
line each: the key, its form and units, its meaning and where its value comes from.

### `list_profiles`

List the demand of the case: its heating and cooling services, with unit, window and peak.

### `read_case`

Return the case of the problem state, one of its sections, its economics or the schema.

`section` is a key of the case (`time`, `site`, `demand`, `utilities`,
`requirements`, `initial_state`), `economics` for the content of the economics file, or
`schema` for the JSON Schema of a case (and of the economics under `economics_schema`).
A section the case does not set yet returns `{section, unset: true, note}`.

### `read_profile`

Return the demand of a service (heating or cooling) of the case as a series in MW.

`start` and `end` are ISO 8601 times, both inclusive. `summary` gives the `peak` and
`minimum` with their time, the `mean` and the `energy` of the window, computed by
gemini's units: take a size from it, never from adding the series by hand.

### `save_profile`

Add a demand profile the user gave as values to the case's demand, and return the demand.

`values` are the demand of the `service` (heating or cooling), one per step in the power
unit `unit` (such as `MW`), from the ISO 8601 time `start` at a constant `step`, given
as `{"value": 1, "unit": "d"}`. gemini checks them (finite, not negative). They are written
to the run's case files as `data/<name>.csv` with a `time` column and the column `name`,
in `unit`, and the `power` of the service points at it; the rest of the demand is kept. A
profile that does not cover the case's `time` sets the time to the profile's own span and
step, in the same call. The service's temperatures and the other series must fit the result:
gemini rejects the case otherwise and nothing is stored.

### `set_case`

Set the case of the problem state: the project's case, changes to it, or both.

`source` is `project` to load the project's `case.json` (beside its data or among its
files, `list_files`) and the files it names, `origin` to go
back to the case the user or the project gave, or omitted to start from the state's case (an
empty one when it has none). `changes` is a JSON merge patch (RFC 7386) on the case: an
object merges into the case, a value replaces, null removes a key; it never holds
`requirements` or `economics` of a case that has them (on a new case, they and `files`
and `columns` in `changes` are taken as those arguments). `requirements` is
`{name: requirement or null}`: a requirement object adds or replaces the one of that name,
null removes it, and the others stay.
`economics` is a merge patch on the content of the case's economics file. `files` names
project files (`list_files`): their bytes go to gemini, under the same name, so a data file
is given to the case and never retyped: name it in `changes`, as the `file` of a series.
A project file the changes name is loaded even when `files` leaves it out. `columns`
renames header names of those files, such as `{"demand.csv": {"date": "time"}}`:
gemini reads a series' times from a column named `time`. Once a case is stored, send only
the keys that change: `changes` merges into it, and a rejected call stores nothing. The
sections are
in `read_case(section="schema")`, the exact schema. gemini validates the result: a rejected
case comes back with the path and message to fix, and nothing is stored; a case with values
missing is `case_incomplete`, every missing path in `suggestions`. The project's case, or
the first case of a chat, is the case the user gave; a design is verified only on it, so any
later change of it, economics included, waits for the user's approval. Write units as the
source gives them (gemini takes °C/km): a gas fraction in % is mol% (gemini converts
mol%), and a unit name as sources print it becomes gemini's name of it (`kg/m³` is
`kg/m3`, `mPa·s` is `mPa.s`, `MWth` is `MW`). With only the site's elevation, give
`site.air.pressure` as `{"elevation": {"value", "unit"}}`: set_case sets the ISA pressure
in Pa (ISO 2533:1975), never a value of yours. Returns the case, the state version
and `converted`, each value set_case mapped or converted (`{path, from, to, reason}`), to
list in the user's confirmation question.

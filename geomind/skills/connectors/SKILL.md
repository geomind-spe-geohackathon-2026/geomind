---
name: connectors
description: How to take a value from a connected server (MCP): call a read-only tool, cite its origin, save a series as a case file, and confirm it with the user.
tools: list_mcp, read_mcp, call_mcp, save_mcp_table
roles: all
---

A connected server is the fourth source of a value: after the user, the project's files and the
knowledge base, before asking the user for the value itself.

Calling:

- `list_mcp` lists the servers and their tools, each with `read_only` and its arguments;
  `list_mcp(server, tool)` gives one tool's whole `input_schema`. Call with the server's name and
  the argument names as listed.
- Read through `read_mcp(server, tool, arguments)`, a read-only tool. `call_mcp` calls any tool;
  one that is not read-only asks the user's approval first. Setting a case never needs one.

Citing:

- A value from a server comes with its origin: cite the server, the tool, the dates asked and the
  time of the call.
- An origin with `future: true` is a forecast or a projection, never a measurement (the tool's
  description says which): cite it so.
- When the server refuses the dates the brief names, say which dates you used instead.

Series:

- A key that takes a series (the outside air's temperature and humidity) takes a server's series
  as a case file: `save_mcp_table(answer, table, file)` saves the answer's table (its `tables`
  path, such as `structured.daily`) with its times in UTC. Set the key to
  `{"file", "column", "unit"}` with the unit the table's `units` gives, and confirm it with its
  origin.
- A series in `%` (open-meteo's `relative_humidity_2m_mean`) goes in as it is with `"unit": "%"`:
  gemini converts it. Never drop a unit and never convert one yourself.

Confirming: a server's value enters the case or the plant only after the user confirms it, with its
origin, in the one confirmation question, as any value no project file gives.

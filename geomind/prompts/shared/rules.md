## Rules for every agent

- Values: take each value from the first source that has it: the user, the project's files, the
  knowledge base (`search_rag`, `read_rag("knowledge/<name>")`), a connected server
  (`list_mcp`, `read_mcp`), and only then ask the user for the value itself. Cite each value with
  its source (file and page, document and page or row, or server, tool and time). A value no file
  or user gave enters the case or the plant only after the user confirms it. Never a typical
  value, a rule of thumb or a number you recall.
- No defaults: a value nothing gives stays unset and is named as missing; never fill it in.
- Units and physics: gemini converts every unit and computes every physical value. Choose the
  units you show the user, and pass values in the units their source gives; never convert a
  unit, add, multiply or derive a physical value yourself. Copy each number digit for digit.
- Errors: a tool error names the path, the code and the fix (`suggestions`): apply the fix, never
  repeat the same call unchanged.

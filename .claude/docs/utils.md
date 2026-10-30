# Utilities

`geomind/utils/` holds general-purpose helpers that know nothing about agents, tools or runs. It is
a leaf package (`tests/unit/test_package_boundaries.py`), so it raises built-in exceptions such as
`ValueError`, and callers that need a geomind error convert them. Import helpers from their topic
module; `geomind/utils/__init__.py` exports nothing.

- `hooks.py`: `RemovableHandle`, ordered registrations with a safe double `remove()`.
- `context.py`: `ContextSetting`, a context variable change usable as `with` and as a decorator.
- `strings.py`: `snake_case`, `first_paragraph`, `join_path`, `join_names`, `did_you_mean`.
- `time.py`: `utc_now`, `parse_duration`.
- `imports.py`: `class_path`, `import_class`, the only import-by-string.
- `json.py`: `to_jsonable`, `read_json`, `write_json` (atomic), `append_line`, `read_lines`.

## Adding a helper

Add a helper only when at least two places need it, or when it removes a duplicate. Put it in the
file of its topic (no `misc.py` or `helpers.py`), give it a docstring, replace every duplicate in
the same commit and add a test to the mirrored `tests/unit/utils/test_<file>.py`.

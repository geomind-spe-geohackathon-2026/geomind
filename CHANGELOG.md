# Changelog

`gd.__version__` follows semver below 1.0, the same rule as gemini: a breaking change to a frozen
interface raises the minor version, and an addition or a fix raises the patch version. The rule and
the list of frozen interfaces are in [.claude/docs/api.md](.claude/docs/api.md#frozen-interfaces).

## 0.1.1 (unreleased)

Additive changes only: a new key of the problem state. Nothing the backend uses
changes shape, and an existing caller sees the same behaviour.

- `ProblemState.brief`: a `Brief` (or `null`), the brief as data, and `brief` among the keys a
  patch may change. The backend stores it with the state; an older state without it loads as
  `null`. `geomind.context` exports `Brief`, `PRESETS`, `preset` and `with_changes`; the one preset
  is `hackathon_2027`.
- `RunResult.usage` includes the routing call's tokens, as the run's log always did.

## 0.1.0 (2026-10-31)

The first frozen state.

- Every interface the backend and the agent developer depend on is pinned by snapshots in
  `tests/unit/snapshots/`, and the exchanged documents have JSON schemas and samples in
  `geomind/schemas/`.
- The full tool catalogue up to S4 exists; tools not built yet raise `gd.errors.NotImplementedYet`
  and give an error result with `code: "not_implemented"`.
- Tool error results take gemini's Problem shape, `{"error": {path, code, message, suggestions}}`.
  The former `{"error": {class, message}}` is gone.
- `read_result` returns gemini's Value shape, and a summary without `path` or `field`.
- `LOOPS` holds `tool`, `design`, `makerchecker` and `compare`; a route to a loop not built yet ends
  the run with `stop_reason="not_implemented"`.
- `gd.verify.verify` and `gd.hooks.Verified` have their final signatures.
- `FileWorkspace.plant` loads through `gm.plants.from_dict`, and `FileRunStore` accepts the artifact
  keys `design/<name>` and `result/<id>`. `gd.testing.check_run_store` now checks them.

# Changelog

`gd.__version__` follows semver below 1.0, the same rule as gemini: a breaking change to a frozen
interface raises the minor version, and an addition or a fix raises the patch version. The rule and
the list of frozen interfaces are in [.claude/docs/api.md](.claude/docs/api.md#frozen-interfaces).

## Unreleased, additive at 0.1.0

Additive changes only; nothing the backend uses changes shape, so the version stays.

- `geomind run` takes `--loop`, `--project`, `--recording` and `--record`: `--loop` chooses the loop
  and skips the routing, `--recording` runs from recorded completions and `--record` writes them.
- `gd.Run.start` asks the `Coordinator` first when no agent or loop is given; the routing call is a
  nested run of the run, logged before it starts. The backend still names no loop and no agent.
- `read_plant` reads `example/<Name>` and `template/<name>` and returns the plant's spec beside its
  description; `check_results` returns `failures` and `not_assessed` beside `passed` and `checks`;
  `estimate_costs` returns `lcts`.

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

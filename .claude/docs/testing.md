# Testing

Test what changed and everything that imports it while working; run the full fast suite before
each commit, since it is small here. Never call the network in a test: use `FakeLLM` and the
recorded completions in `tests/fixtures/`. `OpenRouter` is tested against a fake HTTP transport.

Every test belongs to one automatically marked folder tier:

- `tests/unit/` mirrors source files and receives `unit`.
- `tests/integration/` combines runtime components and receives `integration`.
- `tests/e2e/` runs complete public workflows and receives `e2e`.
- `tests/fixtures/` contains recorded completions as JSON.

The registered markers are `unit`, `integration`, `e2e`, `slow` and `docker`, with strict marker
checking. Default options run in parallel with `-n auto --dist loadgroup` and select
`not e2e and not slow and not docker`. Async tests need no marker: `asyncio_mode = "auto"`.

## Test profiles

**Development** is the default for local work and every commit:

```bash
make test                                 # same as: python scripts/test_changed.py
python scripts/test_changed.py --dry-run  # print the selection and the reasons
python scripts/test_changed.py --base origin/main -- -x
make test-all                             # the full fast suite, before each commit
```

`scripts/test_changed.py` takes the files changed against `HEAD` (plus uncommitted and untracked
files, plus commits since `--base <ref>`), builds the `ast` import graph of `geomind/`, `examples/`,
`tests/` and `scripts/` (cached in `.tmp/test_changed/`), and selects the tests of the changed files
and of every module that imports a changed module, directly or transitively:

1. a changed test file runs itself; a changed `conftest.py` runs every test below it;
2. `pyproject.toml` and the root `conftest.py` select every test;
3. every affected `geomind/<path>/<name>.py` runs `tests/unit/<path>/test_<name>.py`, and every
   affected test file runs; imports made by `conftest.py` files are not followed;
4. a changed numbered example selects `tests/e2e/test_examples.py`;
5. any other changed file selects the tests (or `conftest.py` scopes) whose source names its path.

It prints what it chose and why, then runs `pytest -n auto -m "not slow and not docker"
--profile=development` on the selection. The budget is **300 s** wall time: a session-end guard in
the root `conftest.py` fails a development-profile run over 300 s and prints the 10 slowest test
phases.

**Release** runs in CI only, on `main`: `pytest -n auto -m "not docker" --profile=release
--durations=20`, every tier with no time budget.

## Speed budget

An individual fast-tier test call may take at most about one second. In the development profile
the root `conftest.py` fails a slower unit or integration test with instructions to optimize it or
mark it `slow`. E2E tests are exempt. Marking is allowed only when the property inherently needs
long elapsed work; add a one-line reason to its docstring. Do not delete, skip or weaken a test to
meet the budget.

## Parallel-test rules

The suite must remain safe under `pytest -n auto`:

- write only below `tmp_path` locations; temporary files and reports go to `.tmp/`, CLI runs to
  `.runs/` (both git-ignored);
- restore monkeypatches, context variables and runtime settings;
- do not rely on test order or process-global state.

## Structure and quality tests

- `tests/unit/test_mirror.py`: every `geomind/<path>/<name>.py` except `__init__.py` and
  `__main__.py` has a mirrored `tests/unit/<path>/test_<name>.py` that defines a test.
- `tests/unit/test_package_boundaries.py`: the dependency order of
  [conventions.md](conventions.md#dependencies), and that no `core` package or import returns.
- `tests/unit/test_code_quality.py`: comments, nesting, function length with `LONG_FUNCTIONS`,
  `else` after an early exit, builtin raises, framework names and the former package name.
- `tests/unit/test_public_api.py`: the curated `gd` names, documented, and the version.
- `tests/unit/test_docs_links.py`: every link in `AGENTS.md` and `.claude/docs/` resolves.

## Contract tests

`tests/unit/types/test_events.py` pins `event.data()` to the table of
`../docs/contracts.md` section 2. `gd.testing.check_run_store` and `gd.testing.check_workspace`
run against the memory and file implementations in `tests/unit/testing/`; the backend runs the
same functions against its own.

## Evals

`python -m evals.run --agent <name>` tests an agent by tasks, offline from recordings; see
[evals.md](evals.md). `tests/integration/test_evals.py` tests the runner itself.

## Docker

The one `DockerSandbox` integration test has the `docker` marker and skips without a Docker
daemon. Run it with `pytest -m docker -n 0`. It may pull the Python image, so it never runs by
default.

## CI

`.github/workflows/python_lint.yaml` runs Flake8, Black and isort. `python_test.yaml` runs the
development profile on pull requests and the full suite on pushes to `main`, on Python 3.11 to
3.14. It checks gemini out into `gemini-checkout/`, because geomind needs it as an
editable path dependency.

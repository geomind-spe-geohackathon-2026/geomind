# Testing

Test what changed and everything that imports it while working; run the full fast suite before
each commit, since it is small here. Never call the network in a test: use `FakeLLM` and the
recorded completions in `tests/fixtures/`. `OpenRouter` is tested against a fake HTTP transport.

Every test belongs to one automatically marked folder tier:

- `tests/unit/` mirrors source files and receives `unit`.
- `tests/integration/` combines runtime components and receives `integration`.
- `tests/e2e/` runs complete public workflows and receives `e2e`.
- `tests/fixtures/` contains recorded completions as JSON.
- `tests/fixtures/gemini_examples/` is a copy of gemini's two example projects from tag v0.5.5: the
  published wheel ships no examples, and tests never read a sibling gemini folder. Refresh the copy
  when the gemini pin moves and the examples change.

The registered markers are `unit`, `integration`, `e2e`, `slow` and `docker`, with strict marker
checking. Default options run in parallel with `-n 8 --dist loadgroup` and select
`not e2e and not slow and not docker`. Eight workers, not `-n auto`: on a 32-thread laptop the suite
is faster with eight, and with all 32 tests that take 0.3 s alone cross the one-second budget. Async
tests need no marker: `asyncio_mode = "auto"`.

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
2. `pyproject.toml` and `tests/conftest.py` select every test;
3. every affected `geomind/<path>/<name>.py` runs `tests/unit/<path>/test_<name>.py`, and every
   affected test file runs; imports made by `conftest.py` files are not followed;
4. a changed numbered example selects `tests/e2e/test_examples.py`;
5. any other changed file selects the tests (or `conftest.py` scopes) whose source names its path.

It prints what it chose and why, then runs `pytest -n 8 -m "not slow and not docker"
--profile=development` on the selection. The budget is **300 s** wall time: a session-end guard in
`tests/conftest.py` fails a development-profile run over 300 s and prints the 10 slowest test
phases.

**Release** runs in CI only, on `main`: `pytest -n auto -m "not docker" --profile=release
--durations=20`, every tier with no time budget.

## Speed budget

An individual fast-tier test call may take at most about one second. In the development profile
`tests/conftest.py` fails a slower unit or integration test with instructions to optimize it or
mark it `slow`. E2E tests are exempt. Marking is allowed only when the property inherently needs
long elapsed work; add a one-line reason to its docstring. Do not delete, skip or weaken a test to
meet the budget.

## Parallel-test rules

The suite must remain safe under parallel workers:

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
- `tests/unit/test_gemini_names.py`: no private or removed gemini name and no hackathon figure in
  the package, prompts or docs, and the installed gemini is inside the pinned range.
- `tests/unit/test_public_api.py`: the curated `gd` names, documented, and the version.
- `tests/unit/test_docs_links.py`: every link in `AGENTS.md` and `.claude/docs/` resolves.
- `tests/unit/test_frozen_api.py`: the snapshots and schemas of
  [the frozen interfaces](api.md#frozen-interfaces), and that the samples load.

## Contract tests

`tests/unit/types/test_events.py` pins `event.data()` to the table in
[events.md](events.md#public-events), which is section 2 of the shared contract. `gd.testing.check_run_store` and `gd.testing.check_workspace`
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

`.github/workflows/python_lint.yaml` runs Flake8, Black and isort. `python_test.yaml` runs on pushes
to `dev` and `main` and on pull requests: the full suite on `main`, the development profile
otherwise, on Python 3.11 to 3.14. It installs gemini from `requirements/gemini.txt`, geomind's
runtime dependencies and the `test` group, and no project with `-e`; tests import geomind from the
source folder. `tests/unit/test_install.py` keeps these files free of path and editable installs.
CI turns NumPy's AVX-512 off as gemini's CI does: a few winter days split heat between heat pump and
boiler non-uniquely, a known gemini bug. Releases are in [releasing.md](releasing.md).

## Case fixtures

`tests/fixtures/cases.py` loads gemini's two example cases (`hackathon_2026`, `shallow_district`)
and their plants: `example_names` parametrizes a test over both, `example_case(name)` returns the
case dict and `{file name: bytes}` of the files it names (its series and `economics.json`),
`example_plant(name, plant=None)` a new passing plant, and `case_context(name)` a tool context holding the case and its files. `tests/fixtures/stored_runs.py`
simulates the passing design on a case variant (`base`, `colder` 25 K/km, `cooling_peak` 15 MW) and
stores design and run, for tests of assessment and verification; `variant_run` caches one per
process and `warm_runs()` fills the cache from a synchronous fixture. `simulated(name)` caches one
whole-year run of the `simulate` tool per example. No fixture builds a brief or a preset: a case
is data.

A gemini call on a whole year takes a large part of the one-second budget, mostly in gemini's
evaluation, which copies the plant and applies the case for each metric. So a test of a gemini
tool never runs a year in its body: a module-scoped, synchronous `warmed` fixture fills a
`functools.cache` (`asyncio.run` of the tool call) and the test, a plain function, reads the
cached output. Setup time does not count against the budget. A cached context or output is read,
never changed.

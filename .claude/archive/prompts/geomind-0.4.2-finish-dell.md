# geomind: finish and release 0.4.2 (on the NTNU Dell)

Repository: geomind (GitHub `geomind-spe-geohackathon-2026/geomind`). Clone or pull it fresh on this machine; start from `origin/main` at `782b69f`.
The earlier run on the Mac pushed every section of 0.4.2 (M, T, D, C, B and addendum 7b-7e) as `b2cbdf6..782b69f` and stopped before the release. This prompt finishes that job. It is self-contained.

## 0. Rules

- **NO LIVE RUNS.** Spend no LLM tokens. No call to OpenRouter or any real provider, no `check-live` against the network, no live evals or recordings. Run `unset OPENROUTER_API_KEY` first. If a step needs a live call, skip it and list it in the report.
- **No `-e` installs.** Do not run `make install` or `pip install -e`. Make a fresh venv and install gemini from its release wheel:
  `pip install https://github.com/geomind-spe-geohackathon-2026/gemini/releases/download/v0.5.5/gemini_geothermal_suite_open-0.5.5-py3-none-any.whl`
  then geomind's runtime and dev dependencies from `pyproject.toml` without installing geomind itself (tests import from the source tree through `pythonpath = "."`). Do not edit `pyproject.toml`'s `[tool.uv.sources]` here; the migration prompt does that next.
- **gemini is read-only.** Change nothing in gemini. Write gemini requests to `.tmp/live/gemini-requests.md`.
- **No model defaults, DeepSeek only.** Never add an Anthropic model id anywhere.
- **No defaults, general code, no comments in code, docs and CHANGELOG in the same commit, failing test before each fix.** Never shrink or delete recordings or goldens.
- **Branch:** this is the last push straight to `main`. After it, all work goes to `dev` (the migration prompt creates it).
- The job is small: work in the main session, no worktrees needed. Temporary files go in `.tmp/live/`.

## 1. Setup

1. Clone or `git pull --ff-only origin main`; confirm `HEAD` is `782b69f` or a descendant.
2. Set up the venv as in section 0. Print `gemini.__version__` (must be `0.5.5`) and confirm `pip show gemini-geothermal-suite-open` is not editable.
3. Run the fast tier once as a baseline and record the failures with durations.

## 2. The real failure

`tests/.../test_gemini_names.py` fails because `geomind/prompts/design/designer.md` (around line 66) names a gemini name that no longer exists. Replace it with gemini 0.5.5's public name (check gemini's public API, never a private name). Search all prompts, skills and docs for the same name and fix each.

## 3. Flaky tests under parallel load

On the Mac three tests failed only under load (two replays, one more; the project-plant replay takes ~0.75 s against a 1 s budget). Run the fast tier under xdist three times. For each test that fails under load and passes alone, find why it is slow and make it fast (smaller fixture, shared setup, or move it to the slow tier if it is truly an integration test). Do not raise the 1 s budget and do not skip tests.

## 4. Full checks

Run `make test-all`, `make lint`, every recording's replay (`tests/integration/test_eval_replay.py`, slow tier included) and the docker tests (pull `ghcr.io/geomind-spe-geohackathon-2026/gemini-sandbox:0.5.5` and tag it `gemini-sandbox:0.5.5` if missing). Everything passes.

## 5. Release 0.4.2

1. Version `0.4.2` (or `0.5.0` if a public input broke; say why). Update `geomind/__init__.py`, `pyproject.toml`, `CHANGELOG.md`, snapshots, schemas, the contract map and `plan.md`.
2. Collect the gemini requests left in the Mac worktrees' notes (units `day`, `h` and others) into `plan.md` and `.tmp/live/gemini-requests.md`. They are not on this machine; list what the CHANGELOG and commits mention.
3. Re-measure the scripted design run's context after D's prompt cut (characters / 4) and add the number to the CHANGELOG.
4. Push `origin main` and tag `v0.4.2` (push the tag).

## 6. Report (at most 30 lines)

- Commits, one line each; the tag.
- Tests: fast (count, time), slow, e2e, docker, replays.
- The design run's context: before, after C, after D.
- For the app/hosting threads: the deploy needs `GEOMIND_MODEL` and `GEOMIND_CHEAP_MODEL` (both `deepseek/deepseek-v4.1-flash-1017`) and `GEOMIND_CONTEXT_WINDOW=128000`; what changed for the backend (budget codes, answer after a stop, `answer_reserve` with no default, `TimeLimit`, `read_stored`, worker threads).
- The three live tests to rerun later, only when Sahand allows live runs.
- gemini requests and anything still open.

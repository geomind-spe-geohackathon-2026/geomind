# geomind: install gemini from its release, publish geomind releases, work on dev

Repository: geomind (GitHub `geomind-spe-geohackathon-2026/geomind`). Start from `main` after geomind 0.4.2 is pushed.
gemini is at `../gemini`, but from now on geomind does not use that folder to install anything.
This prompt is self-contained.

## 0. Why

Sahand's project-wide rule, given on 2026-11-02:
- Nobody installs a package with `-e` (editable) or from a local path.
- Each package's owner builds it and publishes a release. Every consumer installs a released version.
- For geomind, branch `main` holds releases only. Branch `dev` collects the changes headed to main.
- For gemini, the branch is always `dev`, but you install its releases, not the branch.

gemini publishes wheels as GitHub Release assets, and installing them needs no auth. Today's release:

```
https://github.com/geomind-spe-geohackathon-2026/gemini/releases/download/v0.5.5/gemini_geothermal_suite_open-0.5.5-py3-none-any.whl
```

The import name is still `gemini`. The pyproject range stays `gemini-geothermal-suite-open>=0.5,<0.6`. gemini 0.5.5 requires `pydantic>=2.10`.

What breaks the rule today (at `b2cbdf6`; re-check):
- `pyproject.toml`: `[tool.uv.sources] gemini-geothermal-suite-open = { path = "../gemini", editable = true }`.
- `Makefile` `install`: `python -m pip install -e ../gemini -e . --group dev`.
- `.github/workflows/python_test.yaml`: checks out `GEMINI-Digital-Twin/gemini-geothermal-suite-open` at `ref: refactor`, which is the old upstream and the wrong branch. Then it runs `uv pip install -e ./gemini-checkout -e .`. So CI does not even test against our gemini.
- The docs (`AGENTS.md`, `.claude/docs/`) describe the editable setup.

## 0b. Rules

- **NO LIVE RUNS.** Spend no LLM tokens and make no call to OpenRouter or any real model provider. Run `unset OPENROUTER_API_KEY` first.
- **Branches.** Create `dev` from `main` at the start (`git switch -c dev`, then `git push -u origin dev`). Do all the work on `dev`. The release at the end merges `dev` into `main`; see section 5.
- **No `-e` and no path installs anywhere:** pyproject, uv sources, the Makefile, CI, scripts, Dockerfiles or docs. This includes geomind itself. Tests already import from the source tree through `pythonpath = "."`, so the repo does not need to be installed. Run the CLI as `python -m geomind`, or install a built wheel.
- **gemini is read-only.** Change nothing in `../gemini`. If gemini needs something, add it to `.tmp/release/gemini-requests.md`.
- **Keep everything else unchanged:** code behaviour, tests, recordings and the public API. Only the install, build, release and CI change, plus one small code item (section 4).
- **Quality, docs and tests rules as before:** no comments in code; docs and the changelog in the same commit; the fast tier stays fast; `make test-all` and `make lint` before every push. Temporary files go in `.tmp/release/`.
- This job is small, so the main session may do it alone or with one sonnet worker. Use haiku for the read-only search.

## 1. Inventory (haiku)

List every place that installs, builds or names gemini or geomind by path, with `-e`, by `refactor`, or by the old upstream `GEMINI-Digital-Twin`. Search pyproject, `uv.lock` if any, the Makefile, `.github/`, `scripts/`, any Dockerfiles, `AGENTS.md`, `.claude/docs/`, `README`, `evals/`, and test fixtures that build environments. Also find how the Docker sandbox gets gemini today (the `gemini-sandbox:<version>` image built by `make sandbox-image` in gemini). Write the list to `.tmp/release/inventory.md`.

## 2. Install gemini from its release

1. pyproject:
   - keep `gemini-geothermal-suite-open>=0.5,<0.6`;
   - raise to `pydantic>=2.10` (keep the 3.14 line);
   - replace the uv path source with the release wheel URL above (`[tool.uv.sources] gemini-geothermal-suite-open = { url = "<wheel URL>" }`).

   The exact gemini release then lives in one place. Updating gemini means changing that URL and nothing else.
2. A pip-only install path: add `requirements/gemini.txt` with `gemini-geothermal-suite-open @ <wheel URL>`. The Makefile and the docs use it, so pip and uv users install the same file.
3. Makefile:
   - `install` installs the gemini wheel and geomind's dependency groups, with no `-e` and no `../gemini`. Show the exact commands in the docs.
   - Add `make gemini-version`, which prints `gm.__version__` and the URL in use.
4. Check it in a fresh venv (`.tmp/release/venv`):
   - install from scratch the way the docs say;
   - run `python -c "import gemini, geomind; print(gemini.__version__)"`, which must print 0.5.5;
   - run the fast tier, `make lint` and every recording's replay.

   Report any test that behaves differently on 0.5.5 than on the old checkout, and fix it in geomind. gemini is the source of truth.

## 3. CI

1. `.github/workflows/python_test.yaml`: remove the gemini checkout step. Install the gemini wheel from `requirements/gemini.txt` and the test group with no `-e`. Keep the matrix and the profiles, and run on `dev` and `main` pushes and on pull requests.
2. Add `.github/workflows/release.yaml`, triggered by pushing a tag `v*` on `main`. It must:
   - check that the tag equals `pyproject` `version` and `geomind.__version__`;
   - build the wheel and sdist (`uv build`, or the existing poetry-core backend through `python -m build`);
   - install the built wheel in a clean venv with the gemini wheel, and run `python -m geomind --help` plus a short import test;
   - create a GitHub Release for the tag and attach both files, using `GITHUB_TOKEN` with `contents: write` and no other secret.
3. Validate both workflows locally (`actionlint` if installed, or at least a YAML parse plus a careful read). Do not push tags only to test them.

## 4. One small code item from the app

When a tool refuses because the chat has no complete case, such as `save_profile` saying "the problem state has no case", it returns a stable error code: `no_case` when there is no case, and `case_incomplete` with the missing paths from gemini's check when there is a case but it is incomplete. Keep today's message text, because the app still matches it until it moves to the code. Put the codes in the contract map and test both.

## 5. Release geomind 0.4.3

1. On `dev`: bump to `0.4.3`. Update the CHANGELOG (install from releases, CI on our gemini, the release workflow, the `no_case` and `case_incomplete` codes), the snapshots, and the docs:
   - `AGENTS.md` "Start here": how to install, how to update the gemini version, and the branch rule;
   - `.claude/docs/` for testing, releasing and the contract map.
2. Run `make test-all`, `make lint` and every replay in the fresh venv from section 2.4. Then push `dev`.
3. Merge `dev` into `main` with `--no-ff`, push `main`, then tag `v0.4.3` on main and push the tag. The release workflow publishes the wheel.
4. If the workflow result is visible, report it, with the release asset URL. It should look like `https://github.com/geomind-spe-geohackathon-2026/geomind/releases/download/v0.4.3/geomind-0.4.3-py3-none-any.whl`. If the run cannot be seen from here, say so; do not guess.
5. Switch back to `dev` for all later work.

## 6. Done when

- No `-e`, no path install, no `../gemini` install and no old upstream remain anywhere (the inventory grep is empty, apart from history in the CHANGELOG).
- A fresh venv installs from the docs, imports gemini 0.5.5, and passes the fast tier, lint and every replay.
- CI installs gemini from its release. The release workflow exists, and `v0.4.3` is tagged on main.
- `dev` exists on origin, and `main` holds the release.
- `no_case` and `case_incomplete` are returned and documented.

## 7. Final report (at most 30 lines)

- The commits, plus the branch and tag state.
- The test results in the fresh venv.
- What changed for the people who use geomind:
  - for the backend: install geomind from `<release wheel URL>` and gemini from its release, both pinned; geomind needs `pydantic>=2.10`;
  - the new error codes.
- How a developer works now: clone, install, test, update gemini, and release.
- Anything still depending on a gemini checkout, such as the sandbox image build, with a proposal for it. Add a gemini request if gemini should publish the sandbox image.

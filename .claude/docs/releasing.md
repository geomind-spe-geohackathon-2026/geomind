# Installs and releases

## Installs

gemini comes only from its release wheel. `requirements/gemini.txt` pins the wheel URL with its
sha256; `[tool.uv.sources]` names the same URL for uv. `pyproject.toml` keeps the range
`>=0.5,<0.6`, since geomind is a library and a user may pin any release in it.

`make install` installs the pinned gemini, the runtime dependencies from
`scripts/project_dependencies.py` and the `dev` group, and not geomind itself: tests and scripts
import it from the source folder (`pythonpath = "."`; a script needs `PYTHONPATH=.`). `make install`
needs pip 25.1 or newer for `--group`, and raises it.

The module sandbox image is `gemini-sandbox:<version>`. `make sandbox-image` pulls it from
`ghcr.io/geomind-spe-geohackathon-2026/gemini-sandbox:<version>` and tags it with that local name.

## Updating gemini

Change the URL in both places and the sha256, install in a new venv, run `make sandbox-image`, then
all tests. When the examples changed, copy them again to `tests/fixtures/gemini_examples/`.

## Publishing a release

`.github/workflows/release.yaml` runs on a `v*` tag. It refuses a tag not on `main` and a tag that
differs from the version in `pyproject.toml` or `geomind/__init__.py`, builds the wheel and sdist,
installs the wheel with the pinned gemini in a clean venv, runs `python -m geomind --help`, and
creates the GitHub Release with `GITHUB_TOKEN`.

The order: raise the version on `dev`, run `PYTHONPATH=. python scripts/snapshot_api.py`, run every
test tier, merge `dev` into `main` with `--no-ff`, push `main`, tag `main`, push the tag. Never push a
test tag: it would publish a release.

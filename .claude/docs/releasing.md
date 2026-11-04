# Installs and releases

## Installs

gemini comes only from its release wheel. `requirements/gemini.txt` pins the wheel URL with its
sha256; `[tool.uv.sources]` names the same URL for uv. `pyproject.toml` keeps the range
`>=0.6,<0.7`, since geomind is a library and a user may pin any release in it.

`make install` installs the pinned gemini, the runtime dependencies from
`scripts/project_dependencies.py` and the `dev` group, and not geomind itself: tests and scripts
import it from the source folder (`pythonpath = "."`; a script needs `PYTHONPATH=.`). `make install`
needs pip 25.1 or newer for `--group`, and raises it.

## Updating gemini

Change the URL in both places and the sha256, install in a new venv, then
all tests. When the examples changed, copy them again to `tests/fixtures/gemini_examples/`.

## Publishing a release

`.github/workflows/release.yaml` runs on a `v*` tag. It refuses a tag not on `main` and a tag that
differs from the version in `pyproject.toml` or `geomind/__init__.py`, builds the wheel and sdist,
installs the wheel with the pinned gemini in a clean venv, runs `python -m geomind --help`, and
creates the GitHub Release with `GITHUB_TOKEN`.

The order: raise the version on `dev`, run `PYTHONPATH=. python scripts/snapshot_api.py`, run every
test tier, push `dev`, then `git checkout main && git merge --ff-only dev` (no merge commit, so
`dev` and `main` never diverge), push `main`, tag `main`, push the tag. Never push a test tag: it
would publish a release.

## Memory on a long-running host

geomind runs gemini in worker threads (`asyncio.to_thread`), and glibc gives each thread its own
malloc arena, so freed memory stays fragmented across arenas and the process grows. It is no
Python leak: repeated eval runs in one process plateau at about 380 MB, with nothing kept. Over the
heavy slow tests one process grew to about 3.5 GB (peak 3.5 GB); with `MALLOC_ARENA_MAX=2` the same
tests left it at 1.0 to 1.7 GB (peak 2.4 GB), and they ran faster. CI sets it for every job, and a
long-running host (the backend's workers) should set `MALLOC_ARENA_MAX=2` in its environment too.
The setting `gemini_threads` (`GEOMIND_GEMINI_THREADS`) runs gemini work (sync tools, gemini's
studies and simulations, the verification) in a pool of that many threads instead of asyncio's
default executor; unset, nothing changes. On the same load (five heavy slow tests in one Python
3.14 process), the process ended at, and peaked at:

| Setting | After the last test | Peak |
|---|---|---|
| none | 3.5 GB | 3.9 GB |
| `GEOMIND_GEMINI_THREADS=2` | 2.3 GB | 2.5 GB |
| `MALLOC_ARENA_MAX=2` | 2.0 GB | 2.1 GB |
| both | 2.3 GB | 2.5 GB |

`MALLOC_ARENA_MAX=2` is the stronger of the two and the pool adds nothing on top of it here, so a
host sets the arenas first; the pool helps where the environment of the process cannot be set.


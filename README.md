# geomind

geomind is an agent harness over an event log, with
[gemini](https://github.com/geomind-spe-geohackathon-2026/gemini) as its physics library. It holds
the agents, the engine that drives them, their tools, permissions, and the `Run` facade a backend uses. Every run is a log that can be resumed and replayed.

```python
import geomind as gd
```

Read [the project rules](docs/rules.md) before you change anything. Changes by version are in
[the changelog](docs/CHANGELOG.md).

## Agents and loops

Agents:

- `Coordinator` routes a request.
- `DesignLead` builds and sizes a plant.
- `AnalysisLead` answers questions by running tools.
- `Economist` works on the costs of a design.
- `Reviewer` checks a design.
- `Explainer` reports a result.
- `Assistant`, `CodeAssistant` and `Summarizer` are general helpers.

Loops:

- `ToolLoop` runs one agent over its tools.
- `DesignLoop` drives a design to a verified result.
- `CompareLoop` designs each alternative on its own, verifies each, then compares them.

## Requirements

- Python 3.11 or newer.
- gemini, installed from its release wheel by `requirements/gemini.txt`.

## Install for development

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
make gemini-version
```

`make install` takes gemini from `requirements/gemini.txt`, then geomind's dependencies. It does not
install geomind itself: the tests import it from the source folder.

## Run the tests

The tests are offline. Keep the key out of the shell so nothing can reach a provider:

```bash
unset OPENROUTER_API_KEY
make test       # the tests of what changed
make test-all   # the whole fast tier and the end-to-end tests
make lint
python -m pytest -m slow --profile=release   # tests that run gemini for real
```

## Update gemini

1. In `requirements/gemini.txt` and in `[tool.uv.sources]` of `pyproject.toml`, set the URL of the new
   release; `requirements/gemini.txt` also takes the wheel's sha256.
2. Run `make install` in a new venv.
3. Run `make test-all`, `make lint` and `python -m pytest -m slow --profile=release`.

## Release

1. On `dev`, raise the version in `pyproject.toml` and `geomind/__init__.py`, run
   `PYTHONPATH=. python scripts/snapshot_api.py` and date the changelog.
2. Run all tests locally, then merge `dev` into `main` and push.
3. Tag `main` with `vX.Y.Z` and push the tag. The release workflow publishes the wheel and the sdist
   on GitHub Releases.

Install a release with the two wheels together:

```bash
pip install -r requirements/gemini.txt \
  "https://github.com/geomind-spe-geohackathon-2026/geomind/releases/download/vX.Y.Z/geomind-X.Y.Z-py3-none-any.whl"
```

## Run the command line

```bash
python -m geomind run "your message" --mode auto
python -m geomind chat
python -m geomind show <run>
python -m geomind replay <run>
python -m geomind check-live
```

`python -m geomind <command> --help` lists the options of each command. `run --concurrency N` lets a
comparison design N families side by side, and `run --retries N` designs a family gemini
rejects again, up to N times.

## Configure the models

`geomind run`, `chat` and `check-live` read a `.env` file in the repository they run in, then
`~/.config/geomind/live.env`; a variable already set in the environment wins. Copy `.env.example`
to `.env`, set the values and keep it to yourself (`chmod 600 .env`): `.env` is ignored by git, and
a test fails if one is ever tracked. No command prints the key.

geomind has no built-in model: a run on a real provider stops at the start until its models are set.

| Variable | Meaning |
|---|---|
| `OPENROUTER_API_KEY` | The key for OpenRouter |
| `GEOMIND_<ROLE>_MODEL` | Each agent's own model, required, no fallback: `GEOMIND_ANALYSISLEAD_MODEL`, `GEOMIND_CASELEAD_MODEL`, `GEOMIND_COORDINATOR_MODEL`, `GEOMIND_DESIGNLEAD_MODEL`, `GEOMIND_ECONOMIST_MODEL`, `GEOMIND_EXPLAINER_MODEL`, `GEOMIND_GEOSCIENTIST_MODEL`, `GEOMIND_REVIEWER_MODEL`, `GEOMIND_SUMMARIZER_MODEL`, `GEOMIND_PROCESSENGINEER_MODEL`, `GEOMIND_INTEGRATIONENGINEER_MODEL`, `GEOMIND_RESERVOIRENGINEER_MODEL`, `GEOMIND_WELLENGINEER_MODEL`, `GEOMIND_ENERGYSYSTEMSENGINEER_MODEL`, `GEOMIND_PROJECTLEAD_MODEL`, `GEOMIND_SUPPORTLEAD_MODEL`, `GEOMIND_CURATOR_MODEL` |
| `GEOMIND_DESIGN_CONCURRENCY` | Required: how many engineers of the design team fill their parts side by side |
| `GEOMIND_KNOWLEDGE_DIR` | Required for a run with a project: the folder of the knowledge base's documents, such as `data/knowledge` |
| `GEOMIND_EVOLVE_EVALUATIONS`, `GEOMIND_EVOLVE_POPULATION`, `GEOMIND_EVOLVE_SEED`, `GEOMIND_EVOLVE_POLISH` | Required: the settings of gemini's structure search (`evolve_structure`) |
| `GEOMIND_ENGINEER_MAX_STEPS` | Required: the steps of one engineer's run, at which it hands back what it has instead of asking to go on |
| `GEOMIND_PROVIDER` | The OpenRouter providers to try |
| `GEOMIND_CONTEXT_WINDOW` | The context window in tokens; unset, it is read from the provider |
| `GEOMIND_CACHE_MARKED_MODELS` | The model id prefixes that get cache breakpoints |
| `GEOMIND_COMPARE_CONCURRENCY` | How many families a comparison designs side by side; unset, one at a time |
| `GEOMIND_COMPARE_RETRIES` | How often a comparison designs a rejected family again; unset, never |
| `GEOMIND_GEMINI_THREADS` | The threads gemini work runs in; unset, asyncio's default executor |
| `GEOMIND_MEMORY`, `GEOMIND_MEMORY_DIR`, `GEOMIND_MEMORY_SIMILARITY` | Required: the agents' memory `on` or `off`; with `on`, its folder and the least similarity (0 to 1) of a past design that is recalled; no default |
| `GEOMIND_MAX_OUTPUT_TOKENS` | Required: the most output tokens of one model call; no default |
| `GEOMIND_MAX_STEPS` | Required: the steps an agent takes before the run asks the user to continue; no default |
| `GEOMIND_RETRY_COUNT`, `GEOMIND_RETRY_DELAY` | Required for a live run: retries of a failed provider call and the first delay in seconds, doubled each time; no default |

A long-running host, such as a backend worker, should also set `MALLOC_ARENA_MAX=2`: gemini runs
in worker threads, and without it each process grows about twice as large.

The team uses DeepSeek models. `python -m geomind check-live` shows what a live run would use.

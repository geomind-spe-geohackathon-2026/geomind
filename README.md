# geomind

geomind is an agent harness over an event log, with
[gemini](https://github.com/geomind-spe-geohackathon-2026/gemini) as its physics library. It holds
the agents, the engine that drives them, their tools, permissions, a sandbox for code written by a
model, and the `Run` facade a backend uses. Every run is a log that can be resumed and replayed.

```python
import geomind as gd
```

Read [the project rules](docs/rules.md) before you change anything. Changes by version are in
[the changelog](docs/CHANGELOG.md).

## Agents and loops

Agents:

- `Coordinator` routes a request.
- `Designer` builds and sizes a plant.
- `Analyst` answers questions by running tools.
- `Economist` works on the costs of a design.
- `Verifier` checks a design.
- `Explainer` reports a result.
- `Assistant`, `CodeAssistant` and `Summarizer` are general helpers.

Loops:

- `ToolLoop` runs one agent over its tools.
- `DesignLoop` drives a design to a verified result.
- `CompareLoop` compares designs.

## Requirements

- Python 3.11 or newer.
- gemini, installed from its release wheel.
- Docker, only for the docker sandbox and its tests. They need the image `gemini-sandbox:<version>`
  of the installed gemini.

## Install for development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "https://github.com/geomind-spe-geohackathon-2026/gemini/releases/download/v0.5.5/gemini_geothermal_suite_open-0.5.5-py3-none-any.whl"
pip install . --group dev
```

The tests import geomind from the source folder, not from the installed copy.

## Run the tests

The tests are offline. Keep the key out of the shell so nothing can reach a provider:

```bash
unset OPENROUTER_API_KEY
make test       # the tests of what changed
make test-all   # the whole fast tier and the end-to-end tests
make lint
python -m pytest -m slow --profile=release   # tests that run gemini for real
```

## Run the command line

```bash
python -m geomind run "your message" --mode auto
python -m geomind chat
python -m geomind show <run>
python -m geomind replay <run>
python -m geomind check-live
```

`python -m geomind <command> --help` lists the options of each command.

## Configure the models

geomind has no built-in model: a run on a real provider stops at the start until its models are set.

| Variable | Meaning |
|---|---|
| `OPENROUTER_API_KEY` | The key for OpenRouter |
| `GEOMIND_MODEL` | The model of every agent that has no model of its own |
| `GEOMIND_CHEAP_MODEL` | The model of the coordinator and the summarizer |
| `GEOMIND_PROVIDER` | The OpenRouter providers to try |
| `GEOMIND_CONTEXT_WINDOW` | The context window in tokens; unset, it is read from the provider |
| `GEOMIND_CACHE_MARKED_MODELS` | The model id prefixes that get cache breakpoints |

The team uses DeepSeek models. `python -m geomind check-live` shows what a live run would use.

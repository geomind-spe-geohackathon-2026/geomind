# Sandbox

The hands for code the model writes, in `geomind/sandbox/`. `test_module` uses it to test the modules the agent writes. gemini tools are trusted library calls and stay in-process; model-written code only
ever runs here and is never imported into the harness process.

## Protocols

```python
class Sandbox(Protocol):
    async def execute(self, command, *, timeout) -> ExecutionResult: ...
    async def write(self, path, data): ...
    async def read(self, path) -> bytes: ...
    async def close(self): ...

class SandboxProvider(Protocol):
    async def provision(self, manifest) -> Sandbox: ...
```

`ExecutionResult` holds `exit_code`, `stdout`, `stderr` and `duration`. A command over its time
limit has exit code 124 and a missing command 127. `command` is a list or text. `gd.sandbox.LocalSandbox`
and `DockerSandbox` are providers, as the contract passes them to `gd.Run`.

`Manifest(files={}, packages=("gemini",), python="3.11", cpu=1, memory="1g", disk="1g",
timeout="10min", network=False)` says what goes in and the limits.
`Manifest.from_runtime()` takes the limits from `gd.runtime`.

## LocalSandbox

A subprocess in a temporary folder under `.tmp/sandbox/`, with a time limit, a memory limit and an
environment that holds only `PYTHONPATH` for the manifest's packages.

**It is for development only and is not a security boundary.** The code runs as the current user
and can read what that user can read. The empty environment keeps keys out of the process, nothing
more. The memory limit uses `RLIMIT_AS`, which macOS refuses, so on macOS memory is not limited.
`network`, `cpu` and `disk` are not enforced; use `DockerSandbox` for those.

## DockerSandbox

`DockerSandbox(image=None)` starts one container per run: a read-only root, a size-limited
in-memory workspace, CPU and memory limits, no network unless the manifest opens it, and each
manifest package mounted read-only. The container receives no environment from this process.
gemini's dependencies must be in the image; the default `python:<version>-slim` does not have them.

The image of module tests is `gemini-sandbox:<gm.__version__>`. `make sandbox-image` pulls gemini's
published image `ghcr.io/geomind-spe-geohackathon-2026/gemini-sandbox:<version>` (gemini installed,
non-root user) and tags it with that local name. Without it `docker run` fails and `test_module`
says so.

The docker tests (`tests/integration/test_docker_sandbox.py`, `test_module_sandbox.py`) have the
`docker` marker and skip without a daemon or the image.

## Testing agent-written modules

`write_module(name, code)` stores `module/<name>.py` as an artifact. `test_module(name, example=None)`
(`geomind/tools/gemini/modules.py`) provisions its own `DockerSandbox` on the image above, with
`Manifest.from_runtime()` limits, no network and `packages=()` (the image's gemini is the version
that is checked), copies in the code, `example.json` and `geomind/sandbox/module_runner.py`, runs the
runner and closes the container. The runner imports the file with its output sent to standard error,
calls `gm.modules.check` on every `Module` subclass the file defines and prints JSON; geomind turns
it into `{passed, modules, problems, undecided}`. The code never runs in the harness process.
**`LocalSandbox` is refused for agent code** (`not_allowed`), whatever else is configured.

## Lifecycle

The engine provisions lazily, on the first tool that needs a sandbox, once per run; a delegated
run gets its own. It closes the sandbox at run end and when a run pauses, because the process may
exit; files inside do not survive a pause. A lost sandbox is a tool error the model can recover
from, and the next code tool provisions a new one. Output over `tool_result_limit` is cut, with
the full text saved as an artifact. No credential ever enters a sandbox.

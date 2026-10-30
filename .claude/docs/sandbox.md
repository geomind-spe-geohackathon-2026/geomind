# Sandbox

The hands for code the model writes, in `swarmax/sandbox/`. S3 uses it to write and test missing
gemini modules. gemini tools are trusted library calls and stay in-process; model-written code only
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
limit has exit code 124 and a missing command 127. `command` is a list or text. `sx.sandbox.LocalSandbox`
and `DockerSandbox` are providers, as the contract passes them to `sx.Run`.

`Manifest(files={}, packages=("gemini",), python="3.11", cpu=1, memory="1g", disk="1g",
timeout="10min", network=False)` says what goes in and the limits.
`Manifest.from_runtime()` takes the limits from `sx.runtime`.

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
gemini's dependencies must be in the image; the default `python:<version>-slim` does not have them,
so S3 needs an image with them.

The integration test has the `docker` marker and skips without a daemon.

## Lifecycle

The engine provisions lazily, on the first tool that needs a sandbox, once per run; a delegated
run gets its own. It closes the sandbox at run end and when a run pauses, because the process may
exit; files inside do not survive a pause. A lost sandbox is a tool error the model can recover
from, and the next code tool provisions a new one. Output over `tool_result_limit` is cut, with
the full text saved as an artifact. No credential ever enters a sandbox.

"""A container with no network, a read-only root, a small in-memory workspace and limits."""

import asyncio
from time import perf_counter
from uuid import uuid4

from geomind.errors import SandboxError
from geomind.sandbox.base import TIMED_OUT, ExecutionResult, Manifest, checked_path
from geomind.utils.time import parse_duration

WORKSPACE = "/workspace"
_WRITE = 'mkdir -p "$(dirname "$1")" && cat > "$1"'
_LIST = 'cd "$1" 2>/dev/null && find . -type f -size -2M | head -50'


async def run_docker(*arguments, stdin=None):
    """Run the docker command and return ``(exit code, stdout, stderr)``."""
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            *arguments,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise SandboxError(f"DockerSandbox: docker is not installed: {error}") from error
    stdout, stderr = await process.communicate(stdin)
    return process.returncode, stdout, stderr


def start_arguments(name, manifest):
    """Return the ``docker run`` arguments of one sandbox.

    The container holds no environment from this process, so no key can reach it. The workspace is
    a size-limited in-memory file system; the rest of the container is read-only. It lives for the
    time limit at most.
    """
    arguments = ["run", "-d", "--rm", "--name", name, "--read-only", "--pids-limit", "128"]
    arguments += ["--cpus", str(manifest.cpu), "--memory", manifest.memory]
    arguments += ["--security-opt", "no-new-privileges", "--cap-drop", "ALL"]
    arguments += ["--tmpfs", f"{WORKSPACE}:size={manifest.disk},mode=1777", "-w", WORKSPACE]
    arguments += ["--tmpfs", "/tmp:size=64m,mode=1777"]
    if not manifest.network:
        arguments += ["--network", "none"]
    seconds = int(parse_duration(manifest.timeout)) + 30
    return [*arguments, "--entrypoint", "sleep", manifest.image, str(seconds)]


class DockerSandbox:
    """Start one container per ``provision``; the image and limits are the runtime settings."""

    async def provision(self, manifest=None):
        """Start a container for ``manifest`` (the settings' when none) and return its session."""
        manifest = manifest or Manifest.from_runtime()
        name = f"geomind-sandbox-{uuid4().hex[:12]}"
        code, _, stderr = await run_docker(*start_arguments(name, manifest))
        if code != 0:
            raise SandboxError(f"DockerSandbox: docker run failed: {stderr.decode()[:500]}")
        return DockerSession(name, parse_duration(manifest.timeout))


class DockerSession:
    """One running container."""

    def __init__(self, name, timeout):
        """Keep the container name and its time limit in seconds."""
        self.name = name
        self.timeout = timeout

    def _check_alive(self, stderr):
        """Raise when the docker command says the container is gone."""
        if b"No such container" in stderr or b"is not running" in stderr:
            raise SandboxError(f"DockerSandbox: container = {self.name}; the sandbox is lost")

    async def execute(self, arguments):
        """Run a command in the workspace, killed at the time limit."""
        wrapped = ["timeout", "--signal=KILL", str(int(self.timeout)), *arguments]
        started = perf_counter()
        code, stdout, stderr = await run_docker("exec", "-w", WORKSPACE, self.name, *wrapped)
        self._check_alive(stderr)
        return ExecutionResult(
            exit_code=TIMED_OUT if code in (124, 137) else code,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            duration=perf_counter() - started,
        )

    async def write(self, path, data):
        """Write bytes inside the workspace through the standard input of a shell."""
        target = f"{WORKSPACE}/{checked_path(path)}"
        arguments = ["exec", "-i", self.name, "sh", "-c", _WRITE, "sh", target]
        code, _, stderr = await run_docker(*arguments, stdin=data)
        self._check_alive(stderr)
        if code != 0:
            raise SandboxError(f"DockerSandbox: path = {path!r}; {stderr.decode()[:500]}")

    async def read(self, path):
        """Return the bytes of a file inside the workspace."""
        target = f"{WORKSPACE}/{checked_path(path)}"
        code, stdout, stderr = await run_docker("exec", self.name, "cat", target)
        self._check_alive(stderr)
        if code != 0:
            raise SandboxError(f"DockerSandbox: path = {path!r}; no such file")
        return stdout

    async def files(self, folder):
        """Return the paths of the files under a workspace folder, relative to it (at most 50)."""
        target = f"{WORKSPACE}/{checked_path(folder)}"
        code, stdout, _ = await run_docker("exec", self.name, "sh", "-c", _LIST, "sh", target)
        if code != 0:
            return []
        return [line.removeprefix("./") for line in stdout.decode().splitlines() if line.strip()]

    async def close(self):
        """Remove the container."""
        await run_docker("rm", "-f", self.name)

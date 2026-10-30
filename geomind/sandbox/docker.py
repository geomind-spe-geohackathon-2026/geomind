"""A container with no network, read-only packages and resource limits."""

import asyncio
import shlex
from time import perf_counter
from uuid import uuid4

from geomind.errors import SandboxError
from geomind.sandbox.base import TIMED_OUT, ExecutionResult, checked_path, package_root
from geomind.utils.time import parse_duration

PACKAGES = "/opt/packages"
WORKSPACE = "/workspace"
_WRITE = 'mkdir -p "$(dirname "$1")" && cat > "$1"'


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


def start_arguments(name, image, manifest):
    """Return the ``docker run`` arguments of one sandbox.

    The container holds no environment from this process, so no key can reach it. The workspace is
    a size-limited in-memory file system; the rest of the container is read-only.
    """
    arguments = ["run", "-d", "--rm", "--name", name, "--read-only"]
    arguments += ["--cpus", str(manifest.cpu), "--memory", manifest.memory]
    arguments += ["--tmpfs", f"{WORKSPACE}:size={manifest.disk},mode=1777", "-w", WORKSPACE]
    arguments += ["-e", f"PYTHONPATH={PACKAGES}"]
    if not manifest.network:
        arguments += ["--network", "none"]
    for package in manifest.packages:
        source = package_root(package) / package
        arguments += ["-v", f"{source}:{PACKAGES}/{package}:ro"]
    return [*arguments, image, "sleep", str(int(parse_duration(manifest.timeout)))]


class DockerSandbox:
    """Provision one container per run; ``image`` defaults to the manifest's Python.

    NOTE: gemini is mounted read-only, but its dependencies must be in the image.
    """

    def __init__(self, image=None):
        """Remember the image."""
        self.image = image

    async def provision(self, manifest):
        """Start a container and copy the manifest's files in."""
        name = f"geomind-{uuid4().hex[:12]}"
        image = self.image or f"python:{manifest.python}-slim"
        code, _, stderr = await run_docker(*start_arguments(name, image, manifest))
        if code != 0:
            raise SandboxError(f"DockerSandbox: docker run failed: {stderr.decode()[:500]}")
        session = DockerSession(name)
        for path, text in manifest.files.items():
            await session.write(path, text.encode())
        return session


class DockerSession:
    """One running container."""

    def __init__(self, name):
        """Keep the container name."""
        self.name = name

    def _check_alive(self, stderr):
        """Raise when the docker command says the container is gone."""
        if b"No such container" in stderr or b"is not running" in stderr:
            raise SandboxError(f"DockerSandbox: container = {self.name}; the sandbox is lost")

    async def execute(self, command, *, timeout):
        """Run a command in the container, stopped at the time limit."""
        arguments = shlex.split(command) if isinstance(command, str) else list(command)
        wrapped = ["timeout", "--signal=KILL", str(int(timeout)), *arguments]
        started = perf_counter()
        code, stdout, stderr = await run_docker("exec", self.name, *wrapped)
        self._check_alive(stderr)
        return ExecutionResult(
            exit_code=TIMED_OUT if code == 137 else code,
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

    async def close(self):
        """Remove the container."""
        await run_docker("rm", "-f", self.name)

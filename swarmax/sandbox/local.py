"""A subprocess in a temporary folder, for development only."""

import asyncio
import os
import resource
import shlex
import shutil
import signal
import sys
import tempfile
from pathlib import Path
from time import perf_counter

from swarmax.errors import SandboxError
from swarmax.sandbox.base import (
    NOT_FOUND,
    TIMED_OUT,
    ExecutionResult,
    checked_path,
    package_root,
)

_SIZES = {"k": 2**10, "m": 2**20, "g": 2**30}


def parse_size(text):
    """Return the bytes of a size such as ``"1g"``."""
    return int(float(text[:-1]) * _SIZES[text[-1].lower()])


def _limit_memory(limit):
    """Return the function that limits the memory of a child process.

    NOTE: macOS refuses this limit, so there memory is not limited; the sandbox is no security
    boundary anyway, and ``sandbox.md`` says so.
    """

    def apply():
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ValueError, OSError):
            return

    return apply


class LocalSandbox:
    """Provision a subprocess sandbox under ``.tmp/sandbox/``.

    NOTE: this is not a security boundary. The empty environment keeps keys out of the process, but
    the code runs as the current user. Use ``DockerSandbox`` for anything untrusted.
    """

    def __init__(self, root=".tmp/sandbox"):
        """Remember the folder that holds the temporary folders."""
        self.root = Path(root).resolve()

    async def provision(self, manifest):
        """Return a new sandbox with the manifest's files."""
        self.root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(dir=self.root))
        session = LocalSession(folder, manifest)
        for path, text in manifest.files.items():
            await session.write(path, text.encode())
        return session


class LocalSession:
    """One provisioned local sandbox."""

    def __init__(self, folder, manifest):
        """Keep the folder and the limits; the environment holds only the package path."""
        self.folder = folder
        self.memory = parse_size(manifest.memory)
        roots = dict.fromkeys(str(package_root(name)) for name in manifest.packages)
        self.environment = {"PYTHONPATH": os.pathsep.join(roots)}

    def _path(self, path):
        """Return a path inside the folder; a removed folder means the sandbox is lost."""
        if not self.folder.is_dir():
            raise SandboxError(f"LocalSandbox: folder = {self.folder}; the sandbox is lost")
        return self.folder / checked_path(path)

    async def write(self, path, data):
        """Write bytes inside the sandbox."""
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    async def read(self, path):
        """Return the bytes at a path inside the sandbox."""
        target = self._path(path)
        if not target.is_file():
            raise SandboxError(f"LocalSandbox: path = {path!r}; no such file")
        return target.read_bytes()

    async def execute(self, command, *, timeout):
        """Run a command, with ``python`` meaning this interpreter."""
        self._path(".probe")
        arguments = shlex.split(command) if isinstance(command, str) else list(command)
        arguments[0] = sys.executable if arguments[0] == "python" else arguments[0]
        started = perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                *arguments,
                cwd=self.folder,
                env=self.environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                preexec_fn=_limit_memory(self.memory),
            )
        except FileNotFoundError as error:
            return ExecutionResult(exit_code=NOT_FOUND, stderr=str(error))
        return await self._wait(process, timeout, started)

    async def _wait(self, process, timeout, started):
        """Collect the output, or stop the whole process group at the time limit."""
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except TimeoutError:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            return ExecutionResult(
                exit_code=TIMED_OUT,
                stderr=f"timed out after {timeout} s",
                duration=perf_counter() - started,
            )
        return ExecutionResult(
            exit_code=process.returncode,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            duration=perf_counter() - started,
        )

    async def close(self):
        """Remove the folder."""
        shutil.rmtree(self.folder, ignore_errors=True)

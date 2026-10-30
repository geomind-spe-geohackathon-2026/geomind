"""One real container; it may pull an image, so it runs only with ``-m docker``."""

import shutil
import subprocess

import pytest

from swarmax.sandbox import DockerSandbox, Manifest

pytestmark = pytest.mark.docker


def has_docker():
    """Tell whether a Docker daemon answers."""
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.mark.skipif(not has_docker(), reason="needs a Docker daemon")
async def test_container_runs_code_without_network():
    """Code runs, files round-trip and the network is closed."""
    session = await DockerSandbox().provision(Manifest(files={"a.txt": "hi"}, packages=()))
    try:
        assert await session.read("a.txt") == b"hi"
        code = "import socket; socket.create_connection(('1.1.1.1', 53), 2)"
        result = await session.execute(["python", "-c", code], timeout=10)
        assert result.exit_code != 0
    finally:
        await session.close()

"""The docker sandbox, against a fake docker command."""

import pytest

from swarmax.errors import SandboxError
from swarmax.sandbox import DockerSandbox, Manifest, docker
from swarmax.sandbox.base import TIMED_OUT


@pytest.fixture
def commands(monkeypatch):
    """Record every docker command and answer it with success."""
    seen = []

    async def run_docker(*arguments, stdin=None):
        seen.append((arguments, stdin))
        return 0, b"out", b""

    monkeypatch.setattr(docker, "run_docker", run_docker)
    return seen


def test_start_arguments_hold_the_limits():
    """No network, read-only gemini, limits, and nothing from the environment."""
    arguments = docker.start_arguments("n", "img", Manifest(cpu=2, memory="512m", disk="2g"))
    text = " ".join(arguments)
    assert "--network none" in text and "--read-only" in text
    assert "--cpus 2" in text and "--memory 512m" in text and "size=2g" in text
    assert ":/opt/packages/gemini:ro" in text
    assert "API_KEY" not in text


def test_network_can_be_opened():
    """The manifest decides."""
    assert "--network" not in docker.start_arguments("n", "i", Manifest(network=True))


async def test_provision_copies_the_files(commands):
    """The run's files go in through a shell's standard input."""
    await DockerSandbox().provision(Manifest(files={"a.txt": "hi"}))
    assert commands[0][0][0] == "run" and "python:3.11-slim" in commands[0][0]
    assert commands[1][1] == b"hi" and commands[1][0][0] == "exec"


async def test_failed_start_raises(monkeypatch):
    """A failed ``docker run`` is a sandbox error."""

    async def failing(*arguments, stdin=None):
        return 1, b"", b"no image"

    monkeypatch.setattr(docker, "run_docker", failing)
    with pytest.raises(SandboxError, match="no image"):
        await DockerSandbox().provision(Manifest())


async def test_execute_applies_the_time_limit(commands):
    """The command runs under ``timeout`` in the container."""
    session = docker.DockerSession("n")
    result = await session.execute(["python", "m.py"], timeout=5)
    assert commands[0][0][:5] == ("exec", "n", "timeout", "--signal=KILL", "5")
    assert result.stdout == "out"


async def test_killed_command_reports_the_timeout(monkeypatch):
    """A killed command has the shared exit code."""

    async def killed(*arguments, stdin=None):
        return 137, b"", b""

    monkeypatch.setattr(docker, "run_docker", killed)
    result = await docker.DockerSession("n").execute("sleep 9", timeout=1)
    assert result.exit_code == TIMED_OUT


async def test_lost_container_raises(monkeypatch):
    """A gone container is a sandbox error."""

    async def gone(*arguments, stdin=None):
        return 1, b"", b"Error: No such container: n"

    monkeypatch.setattr(docker, "run_docker", gone)
    with pytest.raises(SandboxError, match="lost"):
        await docker.DockerSession("n").read("a.txt")


async def test_close_removes_the_container(commands):
    """Closing force-removes it."""
    await docker.DockerSession("n").close()
    assert commands == [(("rm", "-f", "n"), None)]

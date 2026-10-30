"""The local subprocess sandbox."""

import json
import shutil

import pytest

from geomind.errors import SandboxError
from geomind.sandbox import LocalSandbox, Manifest
from geomind.sandbox.base import NOT_FOUND, TIMED_OUT
from geomind.sandbox.local import parse_size


@pytest.fixture
async def sandbox(tmp_path):
    """Provision one sandbox and remove it afterwards."""
    session = await LocalSandbox(tmp_path).provision(Manifest(files={"data/in.txt": "seed"}))
    yield session
    await session.close()


async def test_runs_python_and_reads_files(sandbox):
    """Code runs in the working folder and sees the manifest's files."""
    await sandbox.write("main.py", b"print(open('data/in.txt').read())")
    result = await sandbox.execute(["python", "main.py"], timeout=10)
    assert (result.exit_code, result.stdout.strip()) == (0, "seed")
    assert result.duration > 0


async def test_environment_holds_no_keys(sandbox, monkeypatch):
    """A key of the harness process is not visible inside."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    code = b"import json, os; print(json.dumps(dict(os.environ)))"
    await sandbox.write("env.py", code)
    result = await sandbox.execute("python env.py", timeout=10)
    environment = json.loads(result.stdout)
    assert "OPENROUTER_API_KEY" not in environment and "sk-secret" not in result.stdout


async def test_gemini_is_importable_inside(sandbox):
    """The manifest's package is on the path."""
    result = await sandbox.execute(
        ["python", "-c", "import importlib.util as u; print(u.find_spec('gemini') is not None)"],
        timeout=10,
    )
    assert result.stdout.strip() == "True"


async def test_time_limit_stops_the_command(sandbox):
    """A command over its limit is killed and reported."""
    result = await sandbox.execute(["python", "-c", "import time; time.sleep(30)"], timeout=0.2)
    assert result.exit_code == TIMED_OUT and "timed out" in result.stderr


async def test_missing_command_is_a_result(sandbox):
    """A command that does not exist is an exit code, not a crash."""
    result = await sandbox.execute(["no-such-command"], timeout=5)
    assert result.exit_code == NOT_FOUND


async def test_read_and_write_stay_inside(sandbox):
    """Bytes round-trip, and paths cannot escape or be missing."""
    await sandbox.write("a/b.bin", b"\x00\x01")
    assert await sandbox.read("a/b.bin") == b"\x00\x01"
    with pytest.raises(SandboxError, match="inside the sandbox"):
        await sandbox.write("../out", b"x")
    with pytest.raises(SandboxError, match="no such file"):
        await sandbox.read("missing")


async def test_lost_folder_raises(sandbox):
    """A removed sandbox is a sandbox error the model can recover from."""
    shutil.rmtree(sandbox.folder)
    with pytest.raises(SandboxError, match="lost"):
        await sandbox.execute(["python", "-V"], timeout=5)


async def test_close_removes_the_folder(tmp_path):
    """Nothing stays behind."""
    session = await LocalSandbox(tmp_path).provision(Manifest())
    await session.close()
    assert not session.folder.exists()


def test_parse_size():
    """Sizes have a binary unit."""
    assert parse_size("1g") == 2**30
    assert parse_size("512m") == 512 * 2**20

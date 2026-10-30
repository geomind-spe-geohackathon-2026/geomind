"""The manifest and path rules."""

import pytest

from swarmax import runtime
from swarmax.errors import SandboxError
from swarmax.sandbox import LocalSandbox, Manifest, Sandbox, SandboxProvider
from swarmax.sandbox.base import checked_path, package_root
from swarmax.sandbox.local import LocalSession


def test_manifest_defaults_are_closed():
    """By default gemini goes in, and the network stays out."""
    manifest = Manifest()
    assert manifest.packages == ("gemini",) and manifest.network is False


def test_manifest_reads_the_runtime():
    """The runtime holds the sandbox defaults."""
    with runtime.settings(sandbox_memory="2g", sandbox_timeout="1min"):
        manifest = Manifest.from_runtime()
    assert (manifest.memory, manifest.timeout) == ("2g", "1min")


@pytest.mark.parametrize("path", ["/etc/passwd", "../up", "a/../../b", ""])
def test_paths_cannot_leave_the_sandbox(path):
    """Absolute paths and parents are refused."""
    with pytest.raises(SandboxError, match="inside the sandbox"):
        checked_path(path)


def test_package_root_finds_gemini_without_importing_it():
    """The folder holds the package."""
    assert (package_root("gemini") / "gemini").is_dir()


def test_unknown_package_raises():
    """A missing package is a sandbox error."""
    with pytest.raises(SandboxError, match="installed package"):
        package_root("no_such_package_here")


def test_local_classes_fit_the_protocols():
    """The shipped classes have the protocol methods."""
    assert hasattr(LocalSandbox, "provision") and hasattr(SandboxProvider, "provision")
    for name in ("execute", "write", "read", "close"):
        assert hasattr(LocalSession, name) and hasattr(Sandbox, name)

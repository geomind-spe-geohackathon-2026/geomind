"""The ``docker run`` arguments of a sandbox: no network, read-only, limited, no environment."""

from geomind.sandbox.base import Manifest
from geomind.sandbox.docker import WORKSPACE, start_arguments


def manifest(network=False):
    """Return a manifest of small limits."""
    return Manifest(
        image="img", cpu=1.0, memory="512m", disk="64m", timeout="60s", network=network
    )


def test_a_sandbox_is_read_only_limited_and_offline():
    """The container drops every capability, has no network and sleeps for its time limit."""
    arguments = start_arguments("box", manifest())
    assert {"--read-only", "--cap-drop", "ALL"} <= set(arguments)
    assert arguments[arguments.index("--network") + 1] == "none"
    assert f"{WORKSPACE}:size=64m,mode=1777" in arguments
    assert arguments[-3:-1] == ["sleep", "img"] and int(arguments[-1]) > 60


def test_a_sandbox_with_the_network_has_no_network_flag():
    """``network`` on leaves docker's default network."""
    assert "--network" not in start_arguments("box", manifest(network=True))

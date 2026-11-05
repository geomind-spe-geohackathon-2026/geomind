"""The sandbox's manifest comes from the settings, and a path cannot leave its folder."""

import pytest

from geomind import runtime
from geomind.errors import SandboxError
from geomind.sandbox.base import Manifest, checked_path

LIMITS = {
    "sandbox_image": "geomind-sandbox",
    "sandbox_cpu": 1,
    "sandbox_memory": "512m",
    "sandbox_disk": "64m",
    "sandbox_timeout": "60s",
}


def test_the_manifest_takes_every_limit_from_the_settings_and_has_no_network():
    """Each field is a setting; the network is off."""
    with runtime.settings(**LIMITS):
        manifest = Manifest.from_runtime()
    assert (manifest.image, manifest.cpu, manifest.memory) == ("geomind-sandbox", 1.0, "512m")
    assert manifest.network is False


def test_an_unset_limit_raises_and_names_its_variable():
    """No default: the missing setting is named."""
    with runtime.settings(**{**LIMITS, "sandbox_image": None}):
        with pytest.raises(SandboxError, match="SANDBOX_IMAGE"):
            Manifest.from_runtime()


@pytest.mark.parametrize("path", ["/etc/passwd", "../out", "a/../../b", ""])
def test_a_path_outside_the_working_folder_is_refused(path):
    """Absolute paths, parent steps and an empty path never reach the container."""
    with pytest.raises(SandboxError):
        checked_path(path)
    assert str(checked_path("out/a.txt")) == "out/a.txt"

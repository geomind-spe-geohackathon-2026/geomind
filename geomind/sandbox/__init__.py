"""The hands for code the model writes: protocols, ``Manifest``, local and docker.

gemini tools are trusted library calls and stay in-process; model-written code only ever runs
here. Imports ``providers`` and everything to its left.
"""

from geomind.sandbox.base import ExecutionResult, Manifest, Sandbox, SandboxProvider
from geomind.sandbox.docker import DockerSandbox
from geomind.sandbox.local import LocalSandbox

__all__ = [
    "DockerSandbox",
    "ExecutionResult",
    "LocalSandbox",
    "Manifest",
    "Sandbox",
    "SandboxProvider",
]

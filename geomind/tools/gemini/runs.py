"""The tools that read profiles and run a plant."""

from typing import Any

from geomind.errors import NotImplementedYet
from geomind.tools.base import tool


@tool(effect="read")
def list_profiles():
    """List the demand profiles, with their name, quantity, unit, start and end."""
    raise NotImplementedYet("list_profiles comes in S2b")


@tool(effect="read")
def read_profile(name: str, start: str | None = None, end: str | None = None):
    """Return a demand profile as a series; ``start`` and ``end`` are ISO 8601 times."""
    raise NotImplementedYet("read_profile comes in S2b")


@tool(effect="compute")
def simulate(
    context,
    design: str | None = None,
    changes: dict[str, dict[str, Any]] | None = None,
    profile: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Simulate a plant and store the full results; return their reference and a summary.

    ``design`` is a stored design, or the project's plant without one. ``changes`` holds parameters
    by module path, for this run only. ``profile`` names a demand profile.
    """
    raise NotImplementedYet("simulate comes in S2b")

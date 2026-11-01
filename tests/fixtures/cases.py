"""gemini's example cases: where they are and what they hold, for tests that read a case."""

import json
from pathlib import Path

import pytest

EXAMPLES = ("hackathon_2026", "shallow_district")
SHALLOW_PEAK_HEATING = 3.034e6
"""The heating peak of ``shallow_district``, in W: its CSV is in kW."""


def example_folder(name):
    """Return the folder of one of gemini's example cases."""
    import gemini as gm

    return Path(gm.__file__).resolve().parents[1] / "inputs/examples" / name


def example_case(name):
    """Return ``(case dict, folder)`` of an example, the dict as its ``case.json`` holds it."""
    folder = example_folder(name)
    return json.loads((folder / "case.json").read_text()), folder


example_names = pytest.mark.parametrize("name", EXAMPLES)

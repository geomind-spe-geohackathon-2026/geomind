"""Shared paths and recorded LLM completions."""

import json
from pathlib import Path

from swarmax.types import Completion

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests/fixtures"


def load_completions(name):
    """Return the recorded completions of ``tests/fixtures/completions/<name>.json``."""
    items = json.loads((FIXTURES / "completions" / f"{name}.json").read_text())
    return [Completion.model_validate(item) for item in items]

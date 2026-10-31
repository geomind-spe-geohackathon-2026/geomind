"""What a model needs beyond the messages: the problem state, the brief, compaction and skills.

Imports ``prompts`` and everything to its left. An LLM call or an event stays in the engine, so
everything here is deterministic.
"""

from geomind.context.brief import PRESETS, Brief, preset, with_changes
from geomind.context.history import restore
from geomind.context.state import Compaction, ProblemState, apply_changes, render

__all__ = [
    "PRESETS",
    "Brief",
    "Compaction",
    "ProblemState",
    "apply_changes",
    "preset",
    "render",
    "restore",
    "with_changes",
]

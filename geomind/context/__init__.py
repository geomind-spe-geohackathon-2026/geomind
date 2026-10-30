"""What a model needs beyond the messages: the problem state, compaction and skills.

Imports ``prompts`` and everything to its left. An LLM call or an event stays in the engine, so
everything here is deterministic.
"""

from geomind.context.state import ProblemState, apply_changes, render

__all__ = ["ProblemState", "apply_changes", "render"]

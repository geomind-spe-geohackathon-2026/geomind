"""Verify a design against its requirements and limits."""

from geomind.errors import NotImplementedYet


def verify(plant, results, *, requirements=(), limits=None):
    """Return ``{passed, checks}`` for a plant and its results.

    ``checks`` holds one gemini Check per balance, limit and requirement. ``requirements`` are items
    of the problem state, and ``limits`` is what ``gm.checks.Limits.to_dict`` returns.
    """
    raise NotImplementedYet("verify comes in S3")

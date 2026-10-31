"""Automatic verification of a design, built on gemini's checks; never an LLM.

Imports ``errors`` only so far; S3 adds gemini through ``import gemini as gm``.
"""

from geomind.verify.verify import verify

__all__ = ["verify"]

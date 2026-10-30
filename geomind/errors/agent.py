"""Errors of defining agents and their answers."""

from geomind.errors.base import GeomindError


class DeclarationError(GeomindError, TypeError, ValueError):
    """An agent, tool or permission rule is defined wrongly."""


class UnknownNameError(GeomindError, ValueError):
    """An unknown prompt role, runtime setting, permission mode or effect."""


class OutputError(GeomindError, ValueError):
    """A final answer does not validate against the agent's ``Output``."""

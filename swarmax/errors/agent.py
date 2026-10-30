"""Errors of defining agents and their answers."""

from swarmax.errors.base import SwarmaxError


class DeclarationError(SwarmaxError, TypeError, ValueError):
    """An agent, tool or permission rule is defined wrongly."""


class UnknownNameError(SwarmaxError, ValueError):
    """An unknown prompt role, runtime setting, permission mode or effect."""


class OutputError(SwarmaxError, ValueError):
    """A final answer does not validate against the agent's ``Output``."""

"""Errors of running, pausing, resuming and replaying."""

from swarmax.errors.base import SwarmaxError


class RunError(SwarmaxError, RuntimeError):
    """An operation needs an active or a known run and has none."""


class RequestError(SwarmaxError, ValueError):
    """An unknown or already answered request id, or an answer of the wrong shape."""


class CheckpointError(SwarmaxError, RuntimeError, ValueError):
    """A checkpoint has a wrong version or shape."""


class ReplayError(SwarmaxError, RuntimeError):
    """A replay differs from its recording; the message names the first differing step."""


class LoopError(SwarmaxError, RuntimeError):
    """A loop state does not fit the loop."""

"""Errors of running, pausing, resuming and replaying."""

from geomind.errors.base import GeomindError


class RunError(GeomindError, RuntimeError):
    """An operation needs an active or a known run and has none."""


class RequestError(GeomindError, ValueError):
    """An unknown or already answered request id, or an answer of the wrong shape."""


class StateError(GeomindError, ValueError):
    """A change of the problem state is invalid; the message tells the model how to fix it."""


class ReplayError(GeomindError, RuntimeError):
    """A replay differs from its recording; the message names the first differing step."""


class LoopError(GeomindError, RuntimeError):
    """A loop state does not fit the loop."""


class BudgetError(GeomindError, ValueError):
    """A budget is set up wrongly, for example a project budget with no cap."""

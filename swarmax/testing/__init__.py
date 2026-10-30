"""Conformance checks a ``RunStore`` or ``Workspace`` implementation can run.

Imports ``run`` and everything to its left.
"""

from swarmax.testing.conformance import check_run_store, check_workspace

__all__ = ["check_run_store", "check_workspace"]

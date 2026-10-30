"""Ordered registrations that callers can remove again."""


class RemovableHandle:
    """Registration of one hook in an insertion-ordered dict; ``remove()`` may be called twice."""

    def __init__(self, hooks, hook):
        """Store ``hook`` in ``hooks`` under a fresh private key."""
        self._hooks = hooks
        self._key = object()
        hooks[self._key] = hook

    def remove(self):
        """Stop calling this hook; removing an already removed hook does nothing."""
        self._hooks.pop(self._key, None)

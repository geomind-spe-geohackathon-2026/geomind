"""The namespace of the implementations."""

import geomind as gd


def test_stores_expose_the_four_implementations():
    """The public names resolve."""
    for name in ("MemoryRunStore", "FileRunStore", "MemoryWorkspace", "FileWorkspace"):
        assert hasattr(gd.stores, name)

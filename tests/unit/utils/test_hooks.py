"""Removable hook registrations."""

from swarmax.utils.hooks import RemovableHandle


def test_handle_removes_only_its_hook_and_twice_is_safe():
    """Registration order survives and a second ``remove`` does nothing."""
    hooks = {}
    first = RemovableHandle(hooks, "first")
    RemovableHandle(hooks, "second")
    first.remove()
    first.remove()
    assert list(hooks.values()) == ["second"]

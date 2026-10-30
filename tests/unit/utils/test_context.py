"""Context settings."""

from contextvars import ContextVar

from swarmax.utils.context import ContextSetting

VALUE = ContextVar("value", default=0)


def test_with_block_nests_and_restores():
    """Leaving a block restores the value on entry."""
    setting = ContextSetting(VALUE, lambda value: value + 1)
    with setting:
        with setting:
            assert VALUE.get() == 2
        assert VALUE.get() == 1
    assert VALUE.get() == 0


def test_decorator_applies_on_every_call():
    """A decorated function sees the setting, and the caller does not."""
    function = ContextSetting(VALUE, lambda value: 5)(VALUE.get)
    assert function() == 5
    assert VALUE.get() == 0

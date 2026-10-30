"""Permission basics; the order is tested rule by rule with the requests."""

import pytest

from swarmax.core.engine import Permissions
from swarmax.errors import UnknownNameError


def test_unknown_mode_suggests_a_name():
    """A mode is one of four."""
    with pytest.raises(UnknownNameError, match="did you mean 'readonly'"):
        Permissions(mode="read only")


def test_unknown_effect_rule_raises():
    """An effect rule names a real effect."""
    with pytest.raises(UnknownNameError, match="did you mean 'effect|'execute'"):
        Permissions(ask=("effect:excute",))

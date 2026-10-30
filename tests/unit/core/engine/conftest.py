"""Shared fixtures of the engine tests."""

import pytest

from swarmax.core import runtime
from tests.fixtures.runs import EXECUTED


@pytest.fixture(autouse=True)
def clean_run():
    """Forget executed tools and retry without delay."""
    EXECUTED.clear()
    with runtime.settings(retry_delay=0):
        yield

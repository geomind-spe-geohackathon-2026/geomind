"""Verification of a design: its final signature."""

import inspect

import pytest

import geomind as gd


def test_it_comes_in_s3():
    """A call says so."""
    with pytest.raises(gd.errors.NotImplementedYet, match="verify comes in S3"):
        gd.verify.verify("plant", "results")


def test_requirements_and_limits_are_keywords():
    """The signature of the plan."""
    parameters = inspect.signature(gd.verify.verify).parameters
    assert parameters["requirements"].kind is inspect.Parameter.KEYWORD_ONLY
    assert (parameters["requirements"].default, parameters["limits"].default) == ((), None)

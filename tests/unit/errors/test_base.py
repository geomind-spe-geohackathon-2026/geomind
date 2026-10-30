"""The root of the error tree."""

import geomind.errors as errors


def test_every_class_derives_from_the_root():
    """Catching ``GeomindError`` catches every class."""
    for name in errors.__all__:
        assert issubclass(getattr(errors, name), errors.GeomindError)

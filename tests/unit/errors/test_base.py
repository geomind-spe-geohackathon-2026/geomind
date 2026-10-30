"""The root of the error tree."""

import swarmax.errors as errors


def test_every_class_derives_from_the_root():
    """Catching ``SwarmaxError`` catches every class."""
    for name in errors.__all__:
        assert issubclass(getattr(errors, name), errors.SwarmaxError)

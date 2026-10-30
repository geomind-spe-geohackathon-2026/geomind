"""Name a class by a string and import it again."""

import importlib


def class_path(kind):
    """Return the ``module:qualname`` path that events store for a class.

    Together with ``import_class`` this is the only import-by-string in geomind.
    """
    return f"{kind.__module__}:{kind.__qualname__}"


def import_class(path):
    """Import the class named by a ``class_path`` string; a path that fits nothing raises."""
    module_name, _, qualname = path.partition(":")
    try:
        value = importlib.import_module(module_name)
        for part in qualname.split("."):
            value = getattr(value, part)
    except (ImportError, AttributeError, ValueError) as error:
        raise ImportError(f"path = {path!r}; expected an importable class") from error
    return value

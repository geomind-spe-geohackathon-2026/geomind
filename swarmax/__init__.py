"""swarmax: agents, an engine over an event log, tools and the Run facade the backend uses."""

__version__ = "0.1.0"
__all__ = ["__version__"]


def __dir__():
    """Expose only the documented API in interactive completion."""
    return sorted(__all__)

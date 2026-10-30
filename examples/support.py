"""What the examples share: the provider, offline by default."""

import argparse

import swarmax as sx


def provider(script, argv=None):
    """Return ``FakeLLM(script)``, or OpenRouter with ``--live``."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="use OpenRouter")
    if parser.parse_args(argv).live:
        return sx.providers.OpenRouter()
    return sx.providers.FakeLLM(script)

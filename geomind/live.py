"""Readiness for a first live run: the key, the model ids and the spending cap."""

import os

import httpx

from geomind import runtime
from geomind.utils.models import BASE_URL, LIST_TIMEOUT

KEY_NAME = "OPENROUTER_API_KEY"
ROLES = runtime.ROLES
FORBIDDEN_PREFIX = "anthropic/"


def fetch_model_ids():
    """Return the model ids of OpenRouter's public list, one free GET without a key."""
    response = httpx.get(f"{BASE_URL}/models", timeout=LIST_TIMEOUT)
    response.raise_for_status()
    return {item["id"] for item in response.json()["data"]}


def role_models():
    """Return the model id of each role from the runtime settings; ``None`` where none is set."""
    return runtime.role_models()


def _role_lines():
    """Return one line per role with the model it would use."""
    lines = []
    for role, model in role_models().items():
        lines.append(f"role {role}: {model or 'NOT SET'}")
    return lines


def role_problems():
    """Return the roles without a model, the live settings unset, and the Anthropic models."""
    problems = []
    for name in runtime.missing_model_settings():
        kind = "model" if name.endswith("MODEL") else "setting"
        problems.append(f"{kind} not set: {name}")
    for role, model in role_models().items():
        if model and model.startswith(FORBIDDEN_PREFIX):
            problems.append(f"model not allowed: {model} (role {role})")
    return problems


def _model_lines(fetcher):
    """Return the lines about the model ids: missing ones, or why the list was not checked."""
    try:
        known = (fetcher or fetch_model_ids)()
    except (httpx.HTTPError, OSError, KeyError, ValueError) as error:
        return [f"models: not checked, the list could not be fetched ({type(error).__name__})"]
    return [
        f"model not in the OpenRouter list: {model} (role {role})"
        for role, model in role_models().items()
        if model and model not in known
    ]


def missing(max_cost=None, max_tokens=None, fetcher=None):
    """Return one line per missing item; an empty list means ready.

    The model list comes from ``fetcher`` (OpenRouter's list when None). A failed fetch is
    reported as a skipped check that does not count as missing.
    """
    lines = role_problems()
    if not os.environ.get(KEY_NAME):
        lines.append(f"{KEY_NAME}: not set")
    if max_cost is None and max_tokens is None:
        lines.append("cap: not given; pass --max-cost or --max-tokens")
    return lines + _model_lines(fetcher)


def is_skipped(line):
    """Return whether a line only reports a check that could not run."""
    return line.startswith("models: not checked")


def report(max_cost=None, max_tokens=None, fetcher=None):
    """Return ``(lines, ready)``: the printed lines, and whether nothing is missing."""
    lines = missing(max_cost, max_tokens, fetcher)
    ready = all(is_skipped(line) for line in lines)
    if os.environ.get(KEY_NAME):
        lines = [f"{KEY_NAME}: set", *lines]
    lines = [*_role_lines(), *lines]
    return lines, ready

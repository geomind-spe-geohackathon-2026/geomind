"""OpenRouter's public model list, read once per process for context windows and prices."""

import asyncio

import httpx

BASE_URL = "https://openrouter.ai/api/v1"
LIST_TIMEOUT = 15.0
_lists = {}


def forget_models():
    """Drop the cached lists, so the next read fetches again."""
    _lists.clear()


def fetch_models(base_url=BASE_URL, transport=None, timeout=LIST_TIMEOUT):
    """Return the ``data`` items of OpenRouter's public model list, one free GET per process.

    A list read through a ``transport`` (tests) is not cached.
    """
    if transport is None and base_url in _lists:
        return _lists[base_url]
    with httpx.Client(transport=transport, timeout=timeout) as client:
        response = client.get(f"{base_url}/models")
    response.raise_for_status()
    items = response.json()["data"]
    if transport is None:
        _lists[base_url] = items
    return items


def fetch_context_windows(base_url=BASE_URL, transport=None, timeout=LIST_TIMEOUT):
    """Return ``{model id: context_length}`` of OpenRouter's public model list."""
    return {
        item["id"]: item["context_length"] for item in fetch_models(base_url, transport, timeout)
    }


def fetch_prices(base_url=BASE_URL, transport=None, timeout=LIST_TIMEOUT):
    """Return ``{model id: (input, output)}`` price per token for the models that list prices."""
    return {
        item["id"]: (float(item["pricing"]["prompt"]), float(item["pricing"]["completion"]))
        for item in fetch_models(base_url, transport, timeout)
        if {"prompt", "completion"} <= set(item.get("pricing") or {})
    }


async def load_prices(models, fetcher=fetch_prices):
    """Return ``{model id: (input, output)}`` for ``models``, read off the event loop.

    This fills the ``prices`` of ``CostBudget`` and ``ProjectBudget`` for a caller that builds
    ``gd.Run`` itself. There are no default prices: a model the list does not price raises
    ``ValueError`` naming it. ``fetcher`` replaces the network, for tests.
    """
    found = await asyncio.to_thread(fetcher)
    absent = sorted({model for model in models if model not in found})
    if absent:
        raise ValueError(f"prices: models = {absent}; expected a price in OpenRouter's list")
    return {model: found[model] for model in models}

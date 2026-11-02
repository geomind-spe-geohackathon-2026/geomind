"""OpenRouter's public model list, read for the context window of a model."""

import httpx

BASE_URL = "https://openrouter.ai/api/v1"
LIST_TIMEOUT = 15.0


def fetch_context_windows(base_url=BASE_URL, transport=None, timeout=LIST_TIMEOUT):
    """Return ``{model id: context_length}`` of OpenRouter's public model list, one free GET."""
    with httpx.Client(transport=transport, timeout=timeout) as client:
        response = client.get(f"{base_url}/models")
    response.raise_for_status()
    return {item["id"]: item["context_length"] for item in response.json()["data"]}

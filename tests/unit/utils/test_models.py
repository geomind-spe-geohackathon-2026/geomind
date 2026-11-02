"""The model list read for context windows."""

import httpx

from geomind.utils.models import fetch_context_windows


def test_context_windows_come_from_the_model_list():
    """The model list gives ``context_length`` per id."""
    body = {"data": [{"id": "a/b", "context_length": 5}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    found = fetch_context_windows(transport=transport)
    assert found == {"a/b": 5}

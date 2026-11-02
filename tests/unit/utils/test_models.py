"""The model list read for context windows."""

import httpx
import pytest

from geomind.engine.hooks import CostBudget
from geomind.utils import models
from geomind.utils.models import (
    fetch_context_windows,
    fetch_prices,
    forget_models,
    load_prices,
)


def test_context_windows_come_from_the_model_list():
    """The model list gives ``context_length`` per id."""
    body = {"data": [{"id": "a/b", "context_length": 5}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    found = fetch_context_windows(transport=transport)
    assert found == {"a/b": 5}


def listing(requests):
    """Return a transport that serves one list with prices and counts its requests."""
    body = {
        "data": [
            {
                "id": "a/b",
                "context_length": 5,
                "pricing": {"prompt": "0.000001", "completion": "0.000004"},
            },
            {"id": "free/m", "context_length": 9, "pricing": {}},
        ]
    }

    def serve(request):
        requests.append(request)
        return httpx.Response(200, json=body)

    return httpx.MockTransport(serve)


def test_prices_come_from_the_same_list_as_the_windows():
    """A model without prices is left out."""
    transport = listing([])
    assert fetch_prices(transport=transport) == {"a/b": (1e-6, 4e-6)}
    assert fetch_context_windows(transport=transport) == {"a/b": 5, "free/m": 9}


def test_the_list_is_fetched_once_per_process(monkeypatch):
    """Windows and prices share one GET; forgetting it fetches again."""
    requests = []
    forget_models()
    monkeypatch.setattr(models, "BASE_URL", "https://cache.test")
    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **options: real(**{**options, "transport": listing(requests)})
    )
    fetch_prices(base_url="https://cache.test", transport=None)
    fetch_context_windows(base_url="https://cache.test")
    assert len(requests) == 1
    forget_models()
    fetch_prices(base_url="https://cache.test")
    assert len(requests) == 2
    forget_models()


async def test_load_prices_fills_the_prices_of_a_budget_off_the_loop():
    """A caller that builds gd.Run gets exactly the models it names."""
    found = await load_prices(["a/b"], lambda: fetch_prices(transport=listing([])))
    assert found == {"a/b": (1e-6, 4e-6)}
    assert CostBudget(1.0, prices=found).prices == found


async def test_load_prices_names_a_model_without_a_price():
    """No default price: the error names the model."""
    with pytest.raises(ValueError, match="free/m"):
        await load_prices(["free/m"], lambda: fetch_prices(transport=listing([])))

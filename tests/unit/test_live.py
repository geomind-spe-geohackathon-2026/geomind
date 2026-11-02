"""Live run readiness: key, model ids and cap, with an injected model list."""

import httpx
import pytest

from geomind import live, runtime


def known_models():
    """Return a model list holding every role model."""
    return set(live.role_models().values())


@pytest.fixture
def key(monkeypatch):
    """Key."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-value")


def test_everything_present_is_ready(key):
    """Test everything present is ready."""
    lines, ready = live.report(max_cost=1, fetcher=known_models)
    assert ready
    assert lines[-1] == "OPENROUTER_API_KEY: set"
    assert len(lines) == len(live.ROLES) + 1


def test_a_missing_key_is_reported_without_a_value(monkeypatch):
    """Test a missing key is reported without a value."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    lines, ready = live.report(max_cost=1, fetcher=known_models)
    assert not ready
    assert lines[-1] == "OPENROUTER_API_KEY: not set"


def test_a_set_key_is_never_printed(key):
    """Test a set key is never printed."""
    lines, _ = live.report(max_cost=1, fetcher=known_models)
    assert "fake-value" not in "\n".join(lines)


def test_a_model_missing_from_the_list_is_named_with_its_role(key):
    """Test a model missing from the list is named with its role."""
    with runtime.settings(designer_model="vendor/unknown"):
        lines, ready = live.report(max_cost=1, fetcher=lambda: {runtime.get("default_model")})
    assert not ready
    assert "model not in the OpenRouter list: vendor/unknown (role designer)" in lines


def test_no_network_skips_the_model_check(key):
    """Test no network skips the model check."""

    def offline():
        raise httpx.ConnectError("no network")

    lines, ready = live.report(max_cost=1, fetcher=offline)
    assert ready
    assert any(line.startswith("models: not checked") for line in lines)


def test_no_cap_is_missing(key):
    """Test no cap is missing."""
    lines, ready = live.report(fetcher=known_models)
    assert not ready
    assert any("--max-cost or --max-tokens" in line for line in lines)


def test_a_token_cap_is_enough(key):
    """Test a token cap is enough."""
    assert live.report(max_tokens=1000, fetcher=known_models)[1]


def test_every_role_is_listed_with_its_model(key):
    """Test every role is listed with its model."""
    lines, _ = live.report(max_cost=1, fetcher=known_models)
    assert f"role coordinator: {runtime.get('coordinator_model')}" in lines
    assert f"role analyst: {runtime.get('default_model')}" in lines


def test_a_role_without_a_model_is_not_ready_and_names_the_setting(key, monkeypatch):
    """Test a role without a model is not ready and names the setting."""
    monkeypatch.delenv("GEOMIND_MODEL")
    monkeypatch.delenv("GEOMIND_CHEAP_MODEL")
    lines, ready = live.report(max_cost=1, fetcher=lambda: set())
    assert not ready
    assert "model not set: GEOMIND_MODEL" in lines
    assert "model not set: GEOMIND_CHEAP_MODEL" in lines
    assert "role analyst: NOT SET" in lines


def test_an_anthropic_model_is_not_ready(key):
    """Test an anthropic model is not ready."""
    model = live.FORBIDDEN_PREFIX + "x"
    with runtime.settings(designer_model=model):
        lines, ready = live.report(max_cost=1, fetcher=lambda: {model, *known_models()})
    assert not ready
    assert f"model not allowed: {model} (role designer)" in lines

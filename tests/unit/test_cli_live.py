"""The check-live command and the cap refusal of run."""

import pytest

from geomind import cli, live


@pytest.fixture
def listed(monkeypatch):
    """Serve a model list holding every role model."""
    monkeypatch.setattr(live, "fetch_model_ids", lambda: set(live.role_models().values()))


def test_check_live_is_ready(monkeypatch, capsys, listed):
    """Test check live is ready."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-value")
    assert cli.main(["check-live", "--max-cost", "1"]) == 0
    output = capsys.readouterr().out
    assert "OPENROUTER_API_KEY: set" in output
    assert "fake-value" not in output


def test_check_live_without_a_cap_fails(monkeypatch, capsys, listed):
    """Test check live without a cap fails."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-value")
    assert cli.main(["check-live"]) == 1
    assert "--max-cost or --max-tokens" in capsys.readouterr().out


def test_check_live_without_a_key_fails(monkeypatch, capsys, listed):
    """Test check live without a key fails."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert cli.main(["check-live", "--max-tokens", "10"]) == 1
    assert "OPENROUTER_API_KEY: not set" in capsys.readouterr().out


def test_auto_run_without_a_cap_is_refused(monkeypatch, tmp_path, capsys):
    """Test auto run without a cap is refused."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "OpenRouter", lambda: pytest.fail("provider was built"))
    assert cli.main(["run", "x", "--mode", "auto"]) == 1
    assert "--max-cost or --max-tokens" in capsys.readouterr().err

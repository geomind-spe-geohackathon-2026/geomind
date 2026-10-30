"""Retries, backoff and fallback models."""

import pytest

from geomind import runtime
from geomind.errors import ProviderError
from geomind.providers import FakeLLM, RetryLLM, with_retries
from geomind.types import Completion

BUSY = ProviderError("busy", status=429, is_retryable=True)
GOOD = Completion(text="ok")


@pytest.fixture(autouse=True)
def no_delay():
    """Retry without sleeping."""
    with runtime.settings(retry_delay=0, retry_count=2):
        yield


async def complete(llm, **options):
    """Make one call."""
    return await RetryLLM(llm).complete([], [], model="m", settings={}, **options)


async def test_retries_until_success_and_reports_each():
    """Two failures, two reports, one answer."""
    reports = []

    async def on_retry(**fields):
        reports.append(fields)

    assert await complete(FakeLLM([BUSY, BUSY, GOOD]), on_retry=on_retry) == GOOD
    assert [report["attempt"] for report in reports] == [1, 2]
    assert reports[0]["error"] == "busy"


async def test_gives_up_after_the_count():
    """The last failure is raised."""
    with pytest.raises(ProviderError, match="busy"):
        await complete(FakeLLM([BUSY, BUSY, BUSY]))


async def test_not_retryable_is_not_repeated():
    """A failure that cannot help is raised on the first try."""
    llm = FakeLLM([ProviderError("bad"), GOOD])
    with pytest.raises(ProviderError, match="bad"):
        await complete(llm)
    assert len(llm.calls) == 1


async def test_timeout_is_retried():
    """A plain timeout from any provider counts as retryable."""
    assert await complete(FakeLLM([TimeoutError("slow"), GOOD])) == GOOD


async def test_fallback_model_after_failures():
    """The next model is tried once the first keeps failing, and that is reported."""
    llm = FakeLLM([BUSY, BUSY, BUSY, GOOD])
    reports = []
    result = await complete(llm, fallbacks=("backup",), on_retry=lambda **f: reports.append(f))
    assert result == GOOD
    assert llm.calls[-1]["model"] == "backup"
    assert reports[-1]["model"] == "backup"


def test_with_retries_wraps_once_and_passes_secrets():
    """Wrapping twice changes nothing, and known secrets stay reachable."""
    llm = with_retries(FakeLLM([]))
    assert with_retries(llm) is llm
    assert llm.secrets == ()

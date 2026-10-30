"""Retries with backoff, then fallback models, around any provider."""

import asyncio
import inspect

from swarmax import runtime
from swarmax.errors import ProviderError


async def _report(on_retry, attempt, model, error, delay):
    """Tell the run about one retry; ``on_retry`` is plain or async."""
    if on_retry is None:
        return
    result = on_retry(attempt=attempt, model=model, error=str(error), delay=delay)
    if inspect.isawaitable(result):
        await result


class RetryLLM:
    """Wrap any ``LLM`` so a backend-made provider gets the same reliability.

    A failure with ``is_retryable`` set, or a timeout, is tried again with exponential backoff, up
    to the ``retry_count`` runtime setting. Then the fallback models are tried in order. A failure
    that is not retryable goes straight to the next model. NOTE: text streamed before a failure
    stays streamed, so a client can see it twice; the logged completion holds only the final text.
    """

    def __init__(self, llm):
        """Keep the wrapped provider."""
        self.llm = llm

    @property
    def secrets(self):
        """Return the known secret values of the wrapped provider."""
        return getattr(self.llm, "secrets", ())

    async def complete(
        self, messages, tools, *, model, settings, on_text=None, fallbacks=(), on_retry=None
    ):
        """Return the first completion any attempt gets; raise the last failure otherwise."""
        failure = None
        for candidate in (model, *fallbacks):
            if failure is not None:
                await _report(on_retry, 0, candidate, failure, 0.0)
            try:
                arguments = dict(model=candidate, settings=settings, on_text=on_text)
                return await self._attempts(messages, tools, arguments, on_retry)
            except ProviderError as error:
                failure = error
        raise failure

    async def _attempts(self, messages, tools, arguments, on_retry):
        """Call one model, backing off between retryable failures."""
        retries = runtime.get("retry_count")
        for attempt in range(retries + 1):
            try:
                return await self.llm.complete(messages, tools, **arguments)
            except TimeoutError as error:
                failure = ProviderError(f"timed out: {error}", is_retryable=True)
            except ProviderError as error:
                failure = error
            if not failure.is_retryable or attempt == retries:
                raise failure
            delay = runtime.get("retry_delay") * 2**attempt
            await _report(on_retry, attempt + 1, arguments["model"], failure, delay)
            await asyncio.sleep(delay)


def with_retries(llm):
    """Return ``llm`` wrapped in the retry layer, once."""
    return llm if isinstance(llm, RetryLLM) else RetryLLM(llm)

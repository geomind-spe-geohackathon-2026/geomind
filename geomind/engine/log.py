"""The order of writes: save first, then act, then tell the callbacks."""

import asyncio

from geomind.engine.callbacks import CALLBACK_METHODS, call_maybe_async
from geomind.types.events import ErrorRaised
from geomind.types.redaction import redact_event
from geomind.utils.time import utc_now


class RunLog:
    """The one log of a root run and its nested runs, with one sequence.

    Nested runs save under the root run id, so one log holds the whole tree. Writes keep their
    order through a first-in, first-out lock, because stores are called in worker threads.
    """

    def __init__(self, engine, root, sequence=0):
        """Start after ``sequence``; a resumed run continues the numbering."""
        self.engine = engine
        self.root = root
        self.sequence = sequence
        self.secrets = tuple(getattr(engine.llm, "secrets", ()))
        self._lock = asyncio.Lock()
        self._writes = []

    def build(self, kind, **fields):
        """Return the next event, without secrets."""
        self.sequence += 1
        event = kind(sequence=self.sequence, time=utc_now(), **fields)
        return redact_event(event, self.secrets)

    async def save(self, event):
        """Save one event in order."""
        async with self._lock:
            await asyncio.to_thread(self.engine.store.save_event, self.root, event)

    def save_soon(self, write):
        """Start a write without waiting; ``flush`` waits for it."""
        self._writes.append(asyncio.ensure_future(write))

    async def flush(self):
        """Wait for the writes started with ``save_soon``."""
        writes, self._writes = self._writes, []
        await asyncio.gather(*writes)

    async def notify(self, event):
        """Tell every callback; a failing callback never changes the run."""
        for callback in self.engine.callbacks:
            try:
                await self._tell(callback, event)
            except Exception as error:
                await self._report_failure(error, event)

    async def _tell(self, callback, event):
        """Call the general method and the method of the event's type."""
        await call_maybe_async(callback.on_event, self.engine, event)
        name = CALLBACK_METHODS.get(event.type)
        if name is not None:
            await call_maybe_async(getattr(callback, name), self.engine, event)

    async def _report_failure(self, error, event):
        """Log a callback failure and report it; a failing ``on_error`` is only logged."""
        failure = self.build(
            ErrorRaised,
            run_id=event.run_id,
            agent=event.agent,
            parent=event.parent,
            error_class=type(error).__name__,
            message=str(error),
            where=f"callback on {event.type}",
        )
        await self.save(failure)
        if event.type != "error":
            await self.notify(failure)

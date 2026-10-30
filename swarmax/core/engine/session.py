"""One run in progress: what agents and tools reach as the active run.

NOTE: this file is beyond the layout of the S1 prompt. ``core.runtime`` holds the active run and
sits below the tools, so the object behind it must be defined here, and ``step.py`` stays free of
the bookkeeping.
"""

import asyncio
from dataclasses import dataclass
from time import perf_counter

from swarmax.core import runtime
from swarmax.core.engine.checkpoint import class_path
from swarmax.core.engine.context import Context
from swarmax.core.engine.hooks import ask_hooks
from swarmax.core.engine.recovery import apply
from swarmax.core.types import Allow, Cancel, Deny, Request
from swarmax.core.types.events import (
    CheckpointSaved,
    ErrorRaised,
    LLMCompleted,
    PermissionDecided,
    RequestMade,
    Retried,
    RunStarted,
    SandboxClosed,
    SandboxProvisioned,
    TextDelta,
)
from swarmax.core.types.redaction import redact
from swarmax.errors import RunError, SandboxError
from swarmax.sandbox import Manifest


@dataclass
class Stop:
    """Why a run stops now: exactly one reason."""

    reason: str
    message: str | None = None
    answer: object = None
    request: Request | None = None


class RunSession:
    """The state of one run with its log, and the only way to change that state."""

    def __init__(self, engine, log, state, agent, loop=None):
        """Join a run: ``state`` is empty for a new run and recovered for a resumed one."""
        self.engine = engine
        self.log = log
        self.state = state
        self.agent = agent
        self.loop = loop
        self.waiting_child = None
        self.child_usage = None
        self._sandbox = None
        self._held_text = ""

    @property
    def store(self):
        """Return the store of the run."""
        return self.engine.store

    @property
    def workspace(self):
        """Return the workspace of the run, for the tools of S2."""
        return self.engine.workspace

    @property
    def fields(self):
        """Return what every event of this run carries."""
        return dict(run_id=self.state.run_id, agent=self.state.agent, parent=self.state.parent)

    async def record(self, kind, **fields):
        """Save one event, then apply it. Nothing acts on an event before it is saved."""
        event = self.log.build(kind, **self.fields, **fields)
        await self.log.save(event)
        apply(self.state, event)
        return event

    async def emit(self, kind, **fields):
        """Record one event and tell the callbacks."""
        event = await self.record(kind, **fields)
        await self.log.notify(event)
        return event

    async def start(self, context, *, max_steps, parent=None, parent_step=None, root=None):
        """Log the start of a new run."""
        self.state.run_id = context.run_id
        self.state.agent = self.agent.path
        self.state.parent = parent
        await self.emit(
            RunStarted,
            run=context.run_id,
            loop=self.loop.name if self.loop else None,
            root=root or context.run_id,
            agent_class=class_path(type(self.agent)),
            max_steps=max_steps,
            chat=context.chat,
            project=context.project,
            parent_step=parent_step,
            messages=tuple(context.messages),
            settings=runtime.state(),
            loop_state=self.loop_state(),
        )

    def loop_state(self):
        """Return the state of the loop driving this run."""
        return self.loop.state_dict() if self.loop else {}

    def context(self):
        """Return the context of this moment, over the messages of the state."""
        state = self.state
        return Context(
            state.run_id,
            state.messages,
            chat=state.chat,
            project=state.project,
            steps_left=state.max_steps - state.step,
        )

    def on_text(self, delta):
        """Stream one piece of text; providers call this as a plain function.

        Text is redacted as one stream and the last characters wait for the next piece, as many as
        a known secret could still need, so a secret split across pieces is never sent.
        """
        secrets = self.log.secrets
        waiting = max(map(len, secrets), default=1) - 1
        text = redact(self._held_text + delta, secrets)
        cut = max(len(text) - waiting, 0)
        self._held_text = text[cut:]
        self._stream(text[:cut])

    def _stream(self, text):
        """Log one piece of text, in order, without waiting."""
        if text:
            self.log.save_soon(self.emit(TextDelta, index=self.state.step, text=text))

    async def _on_retry(self, **fields):
        """Log one provider retry."""
        await self.emit(Retried, **fields)

    async def complete(self, agent, messages):
        """Call the provider and log the completion before anything acts on it."""
        if self.engine.llm is None:
            raise RunError("engine: llm = None; expected a provider")
        started = perf_counter()
        completion = await self.engine.llm.complete(
            list(messages),
            agent.tool_schemas(),
            model=agent.model.resolved_name(),
            settings=agent.model.settings(),
            on_text=self.on_text,
            fallbacks=agent.model.fallbacks,
            on_retry=self._on_retry,
        )
        held, self._held_text = self._held_text, ""
        self._stream(held)
        await self.log.flush()
        event = await self.emit(
            LLMCompleted,
            index=self.state.step,
            completion=completion,
            messages=tuple(messages),
            duration=perf_counter() - started,
        )
        return event.completion

    def _hooks_for(self, point):
        """Return the hooks to ask; a point the user approved asks only the ``always_asked``."""
        hooks = self.engine.hooks()
        if point in self.state.allowed:
            return [hook for hook in hooks if hook.always_asked]
        return hooks

    async def before_llm_call(self, agent, messages):
        """Return the hook decision of an LLM call, unless the user approved it."""
        hooks = self._hooks_for("llm")
        decision, _ = await ask_hooks(hooks, "before_llm_call", agent, tuple(messages))
        return decision

    async def before_finish(self, agent, action):
        """Return the hook decision of the answer, unless the user approved it."""
        decision, _ = await ask_hooks(self._hooks_for("finish"), "before_finish", agent, action)
        return decision

    async def decide(self, agent, tool, call):
        """Decide one call, log the decision and the rule, and return the decision.

        A call the user approved is not asked again: an approval applies to that call id only.
        """
        decision, rule = await ask_hooks(self._hooks_for(call.id), "before_tool_call", agent, call)
        if call.id in self.state.allowed and not isinstance(decision, Deny):
            return Allow()
        changed = decision.input if isinstance(decision, Allow) else None
        if decision is None or isinstance(decision, Allow):
            ask_rules = [rule for hook in self.engine.hooks() for rule in hook.ask_rules]
            decision, rule = self.engine.permissions.decide(tool, ask=ask_rules)
        else:
            rule = f"hook:{rule}"
        await self.emit(
            PermissionDecided,
            index=self.state.step,
            decision=_decision_name(decision),
            rule=rule,
            call_id=call.id,
            tool=tool.name,
            reason=getattr(decision, "reason", None),
            input=changed,
        )
        return decision

    async def pause(self, request, point, call=None):
        """Save the pending action, then tell the callbacks, so an answer finds the checkpoint."""
        updates = {"id": request.id or f"request-{self.log.sequence + 1}"}
        updates["call_id"] = call.id if call else None
        request = request.model_copy(update=updates)
        event = await self.record(RequestMade, request=request, point=point, call=call)
        checkpoint = await self._checkpoint()
        await self.log.notify(event)
        await self.log.notify(checkpoint)
        return Stop("request", request=request)

    async def wait_for_child(self, request, call):
        """Pause on the request of a nested run, which already told the callbacks."""
        child, self.waiting_child = self.waiting_child, None
        await self.emit(
            PermissionDecided,
            index=self.state.step,
            decision="wait",
            rule="delegate",
            point="tool",
            call_id=call.id,
            tool=call.name,
            request=request,
            child=child,
            call=call,
        )
        await self.snapshot()
        return Stop("request", request=request)

    async def _checkpoint(self):
        """Log a checkpoint and save the state up to it; return the event."""
        event = await self.record(
            CheckpointSaved, index=self.state.step, loop_state=self.loop_state()
        )
        await self.save_checkpoint()
        return event

    async def snapshot(self):
        """Save a checkpoint and tell the callbacks."""
        await self.log.notify(await self._checkpoint())

    async def save_checkpoint(self):
        """Save the state as it is."""
        self.state.sequence = self.log.sequence
        data = self.state.dump()
        await asyncio.to_thread(self.store.save_checkpoint, self.state.run_id, data)

    async def save_artifact(self, key, data):
        """Save a large result, under the same rule for secrets as an event."""
        clean = redact(data, self.log.secrets)
        await asyncio.to_thread(self.store.save_artifact, self.state.root, key, clean)

    async def report_error(self, error, where):
        """Log an error and call ``on_error``."""
        await self.emit(
            ErrorRaised,
            error_class=type(error).__name__,
            message=str(error),
            where=where,
        )

    async def sandbox(self):
        """Return the sandbox of this run, provisioned on first use."""
        if self._sandbox is not None:
            return self._sandbox
        provider = self.engine.sandbox
        if provider is None:
            raise SandboxError("sandbox: no sandbox is configured for this run")
        self._sandbox = await provider.provision(Manifest.from_runtime())
        await self.emit(SandboxProvisioned, provider=type(provider).__name__)
        return self._sandbox

    async def lose_sandbox(self):
        """Forget a lost sandbox; the next code tool provisions a new one."""
        self._sandbox = None
        await self.emit(SandboxClosed, is_lost=True)

    async def close_sandbox(self):
        """Close the sandbox, at the end of a run and at a pause, as the process may exit."""
        if self._sandbox is None:
            return
        sandbox, self._sandbox = self._sandbox, None
        await sandbox.close()
        await self.emit(SandboxClosed)

    async def delegate(self, agent, task):
        """Run a nested agent; the engine owns how."""
        result = await self.engine.run_child(self, agent, task)
        self.child_usage = result.usage
        if result.request is not None:
            self.waiting_child = result.run_id
        return result

    def take_child_usage(self):
        """Return the usage of the nested run that just ended, once."""
        usage, self.child_usage = self.child_usage, None
        return usage


def _decision_name(decision):
    """Return the name a ``permission`` event gives a decision."""
    if isinstance(decision, Request):
        return "ask"
    return "deny" if isinstance(decision, Deny) else "allow"


def is_cancel(decision):
    """Tell whether a decision ends the run as cancelled."""
    return isinstance(decision, Cancel)

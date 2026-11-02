"""One run in progress: what agents, tools and hooks reach as ``context.session``."""

import asyncio
import json
import platform
from time import perf_counter

from geomind import runtime
from geomind.context import apply_changes
from geomind.context.compaction import load_windows
from geomind.engine.context import Context
from geomind.engine.delegation import run_child
from geomind.engine.hooks import ask_hooks
from geomind.engine.recovery import apply
from geomind.engine.state import Stop
from geomind.errors import RunError, SandboxError, ToolError
from geomind.providers import needs_models
from geomind.sandbox import Manifest
from geomind.types import Allow, Deny, Request, Usage
from geomind.types.events import (
    Compacted,
    ErrorRaised,
    LLMCompleted,
    PermissionDecided,
    RequestMade,
    Retried,
    RunStarted,
    SandboxClosed,
    SandboxProvisioned,
    StateChanged,
    TextDelta,
)
from geomind.types.redaction import redact
from geomind.utils.imports import class_path

FROZEN = ("design/", "study/")


def current_versions():
    """Return the versions a run begins with; ``gemini`` is left out when it cannot be imported.

    NOTE: gemini is imported here, not at the top, so ``import geomind`` stays fast.
    """
    import geomind

    versions = {"geomind": geomind.__version__}
    try:
        import gemini as gm
    except ImportError:
        pass
    else:
        versions["gemini"] = gm.__version__
    return {**versions, "python": platform.python_version()}


class RunSession:
    """The state of one run with its log, and the only way to change that state."""

    def __init__(self, engine, log, state, agent, loop=None, parent=None):
        """Join a run: ``state`` is empty for a new run and recovered for a resumed one."""
        self.engine = engine
        self.log = log
        self.state = state
        self.agent = agent
        self.loop = loop
        self.parent = parent
        self.waiting_child = None
        self.child_usage = None
        self._sandbox = None
        self._held_text = ""

    def versions(self):
        """Return the versions of this process, for what a tool stores beside its result."""
        return current_versions()

    @property
    def store(self):
        """Return the store of the run."""
        return self.engine.store

    @property
    def workspace(self):
        """Return the workspace of the run; tools reach a project's plant and documents here."""
        return self.engine.workspace

    @property
    def fields(self):
        """Return what every event of this run carries."""
        return dict(run_id=self.state.run_id, agent=self.state.agent, parent=self.state.parent)

    async def emit(self, kind, **fields):
        """Save one event, apply it, then tell the callbacks.

        Nothing acts on an event before it is saved.
        """
        event = self.log.build(kind, **self.fields, **fields)
        await self.log.save(event)
        apply(self.state, event)
        await self.log.notify(event)
        return event

    async def start(self, context, *, max_steps, parent=None, parent_step=None, root=None):
        """Log the start of a new run; a real provider needs every role's model first."""
        if parent is None:
            await self._require_models()
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
            problem=context.problem.model_dump(mode="json"),
            settings=runtime.state(),
            loop_state=self.loop_state(),
            versions=current_versions(),
            models=runtime.role_models(),
        )

    async def _require_models(self):
        """Refuse a run on a real provider that lacks a model, and read the context windows."""
        if not needs_models(self.engine.llm):
            return
        problems = runtime.model_problems()
        if problems:
            raise RunError("run: models = unset; expected one per role: " + "; ".join(problems))
        await load_windows(set(runtime.role_models().values()))

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
            problem=state.problem,
            session=self,
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
        """Tell the callbacks one piece of text, in order, without waiting.

        NOTE: ``text.delta`` is stream-only and never reaches the store: ``llm.completed`` and
        ``step.finished`` hold the full text, so recovery and replay never need the pieces.
        """
        if text:
            event = self.log.build(TextDelta, **self.fields, index=self.state.step, text=text)
            self.log.save_soon(self.log.publish(event))

    async def _on_retry(self, **fields):
        """Log one provider retry."""
        await self.emit(Retried, **fields)

    async def _call_provider(self, agent, messages, on_text):
        """Call the provider for an agent."""
        if self.engine.llm is None:
            raise RunError("engine: llm = None; expected a provider")
        if needs_models(self.engine.llm):
            await load_windows({agent.model.resolved_name()})
        llm = self.engine.recorded_llms.get(self.state.run_id, self.engine.llm)
        return await llm.complete(
            list(messages),
            agent.tool_schemas(),
            model=agent.model.resolved_name(),
            settings=agent.model.settings(),
            on_text=on_text,
            fallbacks=agent.model.fallbacks,
            on_retry=self._on_retry,
        )

    async def summarize(self, agent, messages, turns):
        """Call the provider for a summary of ``turns`` turns and log it, without streaming."""
        started = perf_counter()
        completion = await self._call_provider(agent, messages, None)
        await self.emit(
            Compacted,
            index=self.state.step,
            completion=completion,
            messages=tuple(messages),
            duration=perf_counter() - started,
            turns=turns,
        )

    async def complete(self, agent, messages):
        """Call the provider and log the completion before anything acts on it."""
        started = perf_counter()
        completion = await self._call_provider(agent, messages, self.on_text)
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
        decision, _ = await ask_hooks(
            hooks, "before_llm_call", self.context(), agent, tuple(messages)
        )
        return decision

    async def before_finish(self, agent, action):
        """Return the hook decision of the answer, unless the user approved it."""
        decision, _ = await ask_hooks(
            self._hooks_for("finish"), "before_finish", self.context(), agent, action
        )
        return decision

    async def decide(self, agent, tool, call):
        """Decide one call, log the decision and the rule, and return the decision.

        A call the user approved is not asked again: an approval applies to that call id only.
        """
        decision, rule = await ask_hooks(
            self._hooks_for(call.id), "before_tool_call", self.context(), agent, call
        )
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
        """Log the pending action, so an answer finds it, and stop."""
        updates = {"id": request.id or f"request-{self.log.sequence + 1}"}
        updates["call_id"] = call.id if call else None
        request = request.model_copy(update=updates)
        await self.emit(RequestMade, request=request, point=point, call=call)
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
        return Stop("request", request=request)

    async def change_state(self, changes):
        """Log a change of the problem state and return its version.

        An invalid change raises before anything is logged. NOTE: the whole tree of runs shares one
        problem state, so a change in a nested run also reaches the runs above it.
        """
        version = apply_changes(self.state.problem, changes).version
        event = await self.emit(StateChanged, version=version, changes=tuple(changes))
        session = self.parent
        while session is not None:
            apply(session.state, event)
            session = session.parent
        return version

    async def save_problem(self):
        """Keep the problem state for the next message of the chat, when a root run ends."""
        state = self.state
        if state.parent is None and state.chat is not None:
            data = state.problem.model_dump(mode="json")
            await asyncio.to_thread(self.store.save_state, state.chat, data)

    @property
    def chat_id(self):
        """Return the chat of the run; a run without a chat is the chat of its root run."""
        return self.state.chat or self.state.root

    async def save_artifact(self, key, data):
        """Save an artifact in the space of the chat, under the same rule for secrets as an event.

        The problem state can name every artifact a tool saves, so the next run of the chat must
        read it; the run's own space (``store.save_artifact``) is for what no state names. A
        ``design/<name>`` and a ``study/<name>`` are written once: the same content again is fine,
        other content raises ``ToolError``, so a result never points at a design that changed.
        """
        clean = redact(data, self.log.secrets)
        if key.startswith(FROZEN):
            self.check_frozen(key, clean)
        await asyncio.to_thread(self.store.save_chat_artifact, self.chat_id, key, clean)

    def check_frozen(self, key, data):
        """Raise ``ToolError`` when ``key`` already holds other content."""
        kept = self.load_artifact(key)
        if kept is not None and json.loads(json.dumps(kept)) != json.loads(json.dumps(data)):
            kind, _, name = key.partition("/")
            raise ToolError(
                f"{kind}: name = {name!r}; a {kind} with this name is stored with other content;"
                " use a new name",
                path="name",
            )

    def load_artifact(self, key):
        """Return a stored artifact of this chat; called by sync tools, in a worker thread."""
        return self.store.load_chat_artifact(self.chat_id, key)

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

    @property
    def total_usage(self):
        """Return the usage of the whole run so far: this run's and that of every run above it.

        A nested run's usage joins its parent's when it ends, so nothing is counted twice; a
        sibling still running is not counted yet.
        """
        above = self.parent.total_usage if self.parent is not None else Usage()
        return above + self.state.usage

    def spawn(self, state, agent):
        """Return the session of a nested run on the same log."""
        return RunSession(self.engine, self.log, state, agent, parent=self)

    async def delegate(self, agent, task):
        """Run a nested agent and keep what the parent needs of its result."""
        result = await run_child(self, agent, task)
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

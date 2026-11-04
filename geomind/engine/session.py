"""One run in progress: what agents, tools and hooks reach as ``context.session``."""

import asyncio
import json
import platform
from time import perf_counter

from geomind import runtime
from geomind.context import apply_changes
from geomind.context.compaction import context_window, load_windows
from geomind.engine.context import Context
from geomind.engine.delegation import run_child
from geomind.engine.hooks import ask_hooks, input_bound
from geomind.engine.recovery import apply
from geomind.engine.state import Stop
from geomind.errors import RunError, TimeLimitReached, ToolError
from geomind.providers import needs_models
from geomind.stores.memory import FileMemory
from geomind.tools.base import with_old_names
from geomind.tools.knowledge import has_knowledge
from geomind.tools.mcp import MCP_TOOLS, RecordedMcpTool, load_servers, server_of
from geomind.tools.memory import MEMORY_TOOLS
from geomind.types import Allow, Deny, Request, Usage
from geomind.types.events import (
    Compacted,
    ErrorRaised,
    LLMCompleted,
    PermissionDecided,
    RequestMade,
    Retried,
    RunStarted,
    StateChanged,
    TextDelta,
)
from geomind.types.redaction import redact
from geomind.utils.imports import class_path

FROZEN = ("design/", "study/")


def keys_of(servers):
    """Return the header values of the servers: secrets, never logged, stored or shown."""
    return tuple(value for server in servers for value in server.headers.values() if value)


def mcp_timeout():
    """Return ``mcp_timeout`` in seconds, or refuse a run with servers and no timeout."""
    timeout = runtime.get("mcp_timeout")
    if timeout is None:
        raise RunError("run: mcp_timeout = None; expected GEOMIND_MCP_TIMEOUT, seconds")
    return timeout


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
        self.running = set()
        self.reserved = {}
        self._index_lock = asyncio.Lock()
        self.child_limit = None
        self.limits = {}
        self.ends_at_limit = False
        self._held_text = ""
        self._output_limit = None
        self.limit_reached = None
        self.time_left = None
        self.documents_read = {}

    def limit_output(self, tokens):
        """Lower the output limit of the next provider call to ``tokens``, never raise it."""
        self._output_limit = min(self._output_limit or tokens, tokens)

    def limit_time(self, seconds):
        """Bound the next call to ``seconds``: a time limit cancels it when they have passed."""
        self.time_left = seconds

    def note_limit(self, reason):
        """Remember that a budget or time limit denied a call, so the run answers from its state."""
        self.limit_reached = reason

    def versions(self):
        """Return the versions of this process, for what a tool stores beside its result."""
        return current_versions()

    @property
    def memory(self):
        """Return the agents' memory: the engine's or the workspace's, else the settings' folder.

        ``None`` when ``memory`` is ``off`` or unset; a memory tool then says it is off.
        """
        held = getattr(self.engine, "memory", None)
        if held is None:
            held = getattr(self.engine.workspace, "memory", None)
        if held is not None:
            return held
        if runtime.get("memory") != "on":
            return None
        return FileMemory(runtime.get("memory_dir"))

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
        if max_steps is None:
            raise RunError(
                "run: max_steps = None; expected GEOMIND_MAX_STEPS or --max-steps: the steps an "
                "agent takes before the run asks to continue"
            )
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
            steps_left=state.max_steps + state.questions - state.step,
            problem=state.problem,
            session=self,
            stored=state.stored,
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

    async def stream_answer(self, text):
        """Stream an answer that no model wrote, as the events of one that did."""
        self._stream(text)
        await self.log.flush()

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

    def _call_settings(self, agent, messages):
        """Return the agent's settings with the output limit of this call, used once.

        The limit is the least of what a hook set, the agent's ``max_tokens``, the
        ``max_output_tokens`` setting and what the model's window leaves after the input bound,
        so no call asks for more than fits and no single completion can run away.
        """
        settings = agent.model.settings()
        limit, self._output_limit = self._output_limit, None
        bound = runtime.get("max_output_tokens")
        limits = [item for item in (limit, settings.get("max_tokens"), bound) if item is not None]
        window = context_window(agent.model.resolved_name())
        if window is not None and limits:
            limits.append(max(1, window - input_bound(agent, messages)))
        if limits:
            settings = {**settings, "max_tokens": min(limits)}
        return settings

    async def _call_provider(self, agent, messages, on_text):
        """Call the provider for an agent."""
        await self.ensure_mcp()
        if self.engine.llm is None:
            raise RunError("engine: llm = None; expected a provider")
        if needs_models(self.engine.llm):
            await load_windows({agent.model.resolved_name()})
        llm = self.engine.recorded_llms.get(self.state.run_id, self.engine.llm)
        settings = self._call_settings(agent, messages)
        return await llm.complete(
            list(messages),
            self.offered_schemas(agent),
            model=agent.model.resolved_name(),
            settings=settings,
            on_text=on_text,
            fallbacks=agent.model.fallbacks,
            on_retry=self._on_retry,
        )

    def offered_schemas(self, agent):
        """Return the schemas of the tools offered: without those of a memory or a base not here.

        The tools of the run's MCP servers come last, for every agent that has tools.
        """
        hidden = self.hidden_tools(agent)
        own = [item for item in agent.tool_schemas() if item["name"] not in hidden]
        return own + [tool.schema() for tool in self.mcp_of(agent).values()]

    def hidden_tools(self, agent):
        """Return the names of an agent's tools a run with the memory off does not offer (#127).

        They are the memory tools and a member whose whole work is the memory (``needs_memory``,
        the curator).
        """
        if self.memory is not None:
            return set()
        return {
            name
            for name, item in agent.tools().items()
            if name in MEMORY_TOOLS or getattr(getattr(item, "agent", None), "needs_memory", False)
        }

    def mcp_of(self, agent):
        """Return the MCP tools an agent is offered: ``list_mcp``, ``read_mcp`` and ``call_mcp``.

        None for a run without a server that answered, a rule, or an agent with no tools.
        """
        servers = self.engine.mcp_servers
        if not servers or not servers.servers or agent.model.name == "rule" or not agent.tools():
            return {}
        return dict(MCP_TOOLS)

    def tools_of(self, agent, names):
        """Return the tools a step looks calls up in: the agent's, its MCP tools, old names.

        A replay finds a recorded MCP call by a stand-in that never runs; its result is reused.
        """
        tools = with_old_names({**self.mcp_of(agent), **agent.tools()})
        for name in names:
            if name in tools or not self.engine.recorded:
                continue
            if name in MCP_TOOLS:
                tools[name] = MCP_TOOLS[name]
            elif server_of(name):
                tools[name] = RecordedMcpTool(name)
        return tools

    async def ensure_mcp(self):
        """Load the tools of the run's MCP servers once per engine, never in a replay.

        The servers come from ``Workspace.mcp(project_id)``; each header value becomes a secret
        of the log. A server that fails is left out, with an ``error`` event naming it, never its
        headers.
        """
        engine = self.engine
        if engine.mcp_servers is not None:
            return
        engine.mcp_servers = False
        workspace = engine.workspace
        if engine.recorded or not callable(getattr(workspace, "mcp", None)):
            return
        servers = list(workspace.mcp(self.state.project) or [])
        if not servers:
            return
        self.log.secrets = (*self.log.secrets, *keys_of(servers))
        engine.mcp_servers, failures = await load_servers(
            servers, mcp_timeout(), engine.mcp_transport
        )
        for server, error in failures:
            await self.report_error(error, f"mcp:{server.name}")

    def knows(self):
        """Tell whether this run's workspace has a knowledge base with documents."""
        workspace = self.engine.workspace
        return has_knowledge(workspace) and bool(workspace.knowledge_files())

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
        time_left, self.time_left = self.time_left, None
        try:
            async with asyncio.timeout(time_left):
                completion = await self._call_provider(agent, messages, self.on_text)
        except TimeoutError as error:
            self.release()
            if time_left is None:
                raise
            reason = f"time limit: the model call passed the {time_left:.0f} s left"
            self.note_limit(reason)
            raise TimeLimitReached(reason) from error
        except BaseException:
            self.release()
            raise
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
        self.release()
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
        self._output_limit = None
        self.time_left = None
        self.release()
        decision, _ = await ask_hooks(
            hooks, "before_llm_call", self.context(), agent, tuple(messages)
        )
        if decision is not None:
            self.release()
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
        self.time_left = None
        decision, rule = await ask_hooks(
            self._hooks_for(call.id), "before_tool_call", self.context(), agent, call
        )
        if call.id in self.state.allowed and not isinstance(decision, Deny):
            return Allow()
        changed = decision.input if isinstance(decision, Allow) else None
        if decision is None or isinstance(decision, Allow):
            ask_rules = [rule for hook in self.engine.hooks() for rule in hook.ask_rules]
            decision, rule = self.engine.permissions.decide(
                tool.for_call(self, call.input), ask=ask_rules
            )
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
            free = self.free_name(kind, name)
            raise ToolError(
                f"{kind}: name = {name!r}; a {kind} with this name is stored with other content;"
                f" use a new name, such as {free!r}, and send the same call with it",
                path="name",
                suggestions=(free,),
            )

    def free_name(self, kind, name):
        """Return ``name`` with the first number after it that names no stored ``kind``."""
        number = 2
        while self.load_artifact(f"{kind}/{name}_{number}") is not None:
            number += 1
        return f"{name}_{number}"

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

    @property
    def total_usage(self):
        """Return the usage of the whole run so far: this run's and that of every run above it.

        A nested run's usage joins its parent's when it ends, so nothing is counted twice. A
        sibling running beside this run counts too, and so does the worst case another run's
        call in flight holds (``reserve``), so runs side by side share a cap.
        """
        total = self.state.usage + (self.child_usage or Usage())
        for session, usage in self.root_session.reserved.items():
            total = total if session is self else total + usage
        if self.parent is None:
            return total
        for sibling in self.parent.running - {self}:
            total = total + sibling.state.usage
        return self.parent.total_usage + total

    def spawn(self, state, agent):
        """Return the session of a nested run on the same log."""
        return RunSession(self.engine, self.log, state, agent, parent=self)

    async def delegate(self, agent, task, max_steps=None):
        """Run a nested agent and keep what the parent needs of its result."""
        result = await run_child(self, agent, task, max_steps)
        self.add_child_usage(result.usage)
        if result.request is not None:
            self.waiting_child = result.run_id
        return result

    @property
    def root_session(self):
        """Return the session of the root run of this tree."""
        return self.parent.root_session if self.parent is not None else self

    def reserve(self, usage):
        """Hold the worst usage of this run's next call until it returns; hooks merge theirs."""
        held = self.root_session.reserved.get(self, Usage())
        self.root_session.reserved[self] = Usage(
            input_tokens=max(held.input_tokens, usage.input_tokens),
            output_tokens=max(held.output_tokens, usage.output_tokens),
            cost=max(held.cost, usage.cost),
        )

    def release(self):
        """Drop what this run's call held: it returned, failed or was not sent."""
        self.root_session.reserved.pop(self, None)

    def add_child_usage(self, usage):
        """Keep the usage of a nested run until a tool result carries it; runs may end together."""
        self.child_usage = (self.child_usage or Usage()) + usage

    @property
    def index_lock(self):
        """Return the lock of the chat's index artifacts, shared by the runs of a tree."""
        return self.parent.index_lock if self.parent is not None else self._index_lock

    def take_child_usage(self):
        """Return the usage of the nested run that just ended, once."""
        usage, self.child_usage = self.child_usage, None
        return usage


def _decision_name(decision):
    """Return the name a ``permission`` event gives a decision."""
    if isinstance(decision, Request):
        return "ask"
    return "deny" if isinstance(decision, Deny) else "allow"

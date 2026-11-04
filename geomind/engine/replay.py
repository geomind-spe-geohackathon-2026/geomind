"""Rerun a stored run offline and check that it behaves the same."""

from math import inf

from geomind import runtime
from geomind.agents import Agent
from geomind.context import ProblemState
from geomind.engine.context import Context
from geomind.engine.hooks import Hook
from geomind.engine.permissions import Permissions
from geomind.engine.recovery import agent_class
from geomind.engine.session import current_versions
from geomind.errors import ReplayError
from geomind.providers import FakeLLM, with_retries
from geomind.stores.run import MemoryRunStore
from geomind.tools.gemini.references import is_index, references_in, without_references
from geomind.types import Allow, Cancel, Deny

END_OF_RECORDING = "end of the recording"
ANSWERED = ("answer", "finish")


class _Script:
    """What one run decided: its completions, tool results and refused answers."""

    def __init__(self, events):
        """Index the decisions of the events of one run."""
        self.llm = FakeLLM.from_events(events)
        self.scripted = len(self.llm.completions)
        self.results = {(e.index, e.call_id): e for e in _results(events)}
        self.refusals = {
            e.index: e.output
            for e in events
            if e.type == "tool.result" and e.call_id is None and e.feedback == "finish"
        }
        self.finished = next((e for e in events if e.type == "run.finished"), None)
        pending = [e for e in events if e.type == "request"]
        self.pending = pending[-1] if pending and self.finished is None else None

    def end(self, point, call=None):
        """Return how the recorded run ended at this point: its request, its stop, or ``None``.

        A run that waited asks the same request again; one that a limit or a hook denied, or that
        was cancelled, stops with the same reason, so the replay ends as the run did.
        """
        pending = self.pending
        if pending is not None and pending.point == point:
            if call is None or pending.call is None or pending.call.id == call.id:
                return pending.request
        finished = self.finished
        if finished is None or point != "llm":
            return None
        if finished.stop_reason == "denied":
            return Deny(reason=finished.message)
        if finished.stop_reason == "cancelled":
            return Cancel(reason=finished.message)
        return None


class _Recording(Hook):
    """Repeat what each run of the tree decided, and stop where its log ends.

    Permissions and hooks of the original run are not repeated: the log holds their outcome. A
    call without a recorded result ends the replay, so a paused run never runs its pending tool.
    NOTE: a run with no script raises, and the engine would end that run as an error, so the
    first such error is kept in ``failure`` for ``replay_run`` to raise. The hook is engine-wide
    but every rule is per run, because call ids are not unique
    across the runs of a tree and each run has its own completions. A call is matched by its
    step and id, since a model may reuse an id in a later step.
    """

    def __init__(self, scripts):
        """Keep the script of each run, by run id."""
        self.scripts = scripts
        self.failure = None

    def _script(self, context):
        """Return the script of the run, or raise when the run has none."""
        script = self.scripts.get(context.run_id)
        if script is None:
            self.failure = ReplayError(
                f"replay: run {context.run_id} ({context.session.state.agent}): "
                "started in the replay without a recorded run to follow"
            )
            raise self.failure
        return script

    def before_llm_call(self, context, agent, messages):
        """End the replay when no recorded completion is left; a rule step calls no model."""
        script = self._script(context)
        if type(agent).forward is not Agent.forward:
            return None
        if len(script.llm.calls) < script.scripted:
            return None
        end = script.end("llm")
        if isinstance(end, Deny) and script.finished.answer is not None:
            context.session.note_limit(end.reason)
        return end or Cancel(reason=END_OF_RECORDING)

    def before_tool_call(self, context, agent, call):
        """Use the recorded input, or end the replay at a call without a result."""
        script = self._script(context)
        recorded = script.results.get((context.session.state.step, call.id))
        if recorded is None:
            return script.end("tool", call) or Cancel(reason=END_OF_RECORDING)
        return Allow(input=recorded.input) if recorded.input != call.input else None

    def before_finish(self, context, agent, action):
        """Refuse the answers the original run refused."""
        reason = self._script(context).refusals.get(context.session.state.step)
        return Deny(reason=reason) if reason is not None else None


class _ReplayStore(MemoryRunStore):
    """A memory store that reads an artifact it lacks from the recorded run.

    NOTE: a replayed nested run saves what its tools write, but an artifact it did not write
    itself, such as one a reused nested run stored, is read from the original store; what the
    replay saves itself comes first. A reference index (``results.index``, ...) grows as the run
    goes, and the recorded one is the one of the end: until the replay writes its own, it reads
    the recorded index without ``remade``, the references the replayed runs make again, so a
    listing at a step is the one the run had there.
    """

    def __init__(self, original, run_id, chat_id, remade=frozenset()):
        """Keep the store, the root run id, the chat id and the references made again."""
        super().__init__()
        self.original = original
        self.run_id = run_id
        self.chat_id = chat_id
        self.remade = remade

    def _recorded(self, key, found):
        """Return a recorded artifact, an index without what the replay makes again."""
        if found is None or not is_index(key):
            return found
        return without_references(key, found, self.remade)

    def load_artifact(self, run_id, key):
        """Return the replay's own artifact, else the recorded run's."""
        found = super().load_artifact(run_id, key)
        if found is not None:
            return found
        return self._recorded(key, self.original.load_artifact(self.run_id, key))

    def load_chat_artifact(self, chat_id, key):
        """Return the replay's own chat artifact, else the recorded chat's."""
        found = super().load_chat_artifact(chat_id, key)
        if found is not None:
            return found
        return self._recorded(key, self.original.load_chat_artifact(self.chat_id, key))


def _remade(tree, plan):
    """Return the references the tool results of the runs of ``plan`` hold: made again."""
    return frozenset().union(
        *(references_in(e.output) for e in _results(tree) if e.run_id in plan and not e.is_error)
    )


class _RecordedLoop:
    """Stand for the loop of the recorded root run, so the replayed log names it.

    NOTE: a replay runs the root's agent, not the loop's rules, so only the loop's name and its
    state at the start of the run are what the log says.
    """

    def __init__(self, started):
        """Keep the name and the starting state of the loop."""
        self.name = started.loop
        self.state = started.loop_state

    def state_dict(self):
        """Return the recorded state of the loop."""
        return self.state


def _results(events):
    """Return the tool results of a log, without feedback."""
    return [e for e in events if e.type == "tool.result" and e.call_id is not None]


def _child_calls(events, run_id):
    """Return, by nested run id, the (step, call id) of ``run_id`` that started it, at any depth.

    A delegate's nested run starts at the call's step with the call's task as its first message;
    a run nested deeper belongs to the call of its parent. Parallel calls of one step overlap in the
    log, so the order of events cannot tell them apart.
    """
    calls = {
        (e.index, e.input.get("task")): (e.index, e.call_id)
        for e in events
        if e.type == "tool.started" and e.run_id == run_id
    }
    owners = {}
    for e in events:
        if e.type != "run.started" or e.parent is None or e.run_id == run_id:
            continue
        task = e.messages[0].content if e.messages else None
        is_direct = e.parent == run_id
        owners[e.run_id] = calls.get((e.parent_step, task)) if is_direct else owners.get(e.parent)
    return owners


def _children(tree, run_id):
    """Return, by (step, call id) of ``run_id``, the nested run that call started directly."""
    parents = {e.run_id: e.parent for e in tree if e.type == "run.started"}
    owners = _child_calls(tree, run_id)
    return {
        key: child for child, key in owners.items() if key is not None and parents[child] == run_id
    }


def _nested_changes(events, run_id):
    """Return, by (step, call id) of the run, the problem-state changes its nested runs logged.

    NOTE: a nested run that did not end with an answer is not run again; its recorded result is
    reused and the replay applies again what it wrote in the shared problem state, in log order.
    A nested run that ended with an answer runs again and writes its own changes.
    """
    owners = _child_calls(events, run_id)
    own = _results(e for e in events if e.run_id == run_id)
    changes = {(result.index, result.call_id): [] for result in own}
    for e in events:
        key = owners.get(e.run_id)
        if e.type == "state.changed" and key in changes:
            changes[key].append(e.changes)
    return changes


def _signature(event):
    """Return what must match: the step, the call and what came back."""
    return event.index, event.tool, event.input, event.output, event.is_error


def _in_step_order(results, events):
    """Return ``results`` by their place in the run: the step, then the call's position in it.

    Calls of one step run in parallel and finish in any order, so the log order of their results
    is not theirs. A result without a logged completion keeps its log order after the others.
    """
    places = {
        (event.index, call.id): (event.index, position)
        for event in events
        if event.type == "llm.completed"
        for position, call in enumerate(event.completion.tool_calls)
    }

    def place(result):
        return places.get((result.index, result.call_id), (result.index, inf))

    return sorted(results, key=place)


def _compare_calls(recorded, replayed, is_complete, label):
    """Raise for the first call that differs, matching calls by their place in the run."""
    for old, new in zip(recorded, replayed):
        if _signature(old) != _signature(new):
            raise ReplayError(
                f"replay: {label}: step {old.index}: tool {old.tool}: recorded {_signature(old)}, "
                f"replayed {_signature(new)}"
            )
    if is_complete and len(recorded) != len(replayed):
        index = recorded[min(len(recorded), len(replayed)) - 1].index if recorded else 0
        raise ReplayError(
            f"replay: {label}: step {index}: recorded {len(recorded)} calls, "
            f"replayed {len(replayed)}"
        )


def _compare_end(finished, replayed, label):
    """Raise when a run that ended with an answer ends differently."""
    if finished.stop_reason not in ANSWERED or replayed is None:
        return
    if (finished.stop_reason, finished.answer) != (replayed.stop_reason, replayed.answer):
        raise ReplayError(
            f"replay: {label}: recorded answer {finished.answer!r}, "
            f"replayed {replayed.answer!r} ({replayed.stop_reason})"
        )


def _of_run(events, run_id, kind=None):
    """Return the events of one run, of one type when ``kind`` is given."""
    return [e for e in events if e.run_id == run_id and (kind is None or e.type == kind)]


def _compare_run(tree, replayed, run_id):
    """Compare one run of the tree with its replay: its calls in step order and its end."""
    started = _of_run(replayed, run_id, "run.started")
    if not started:
        return
    label = f"run {run_id} ({started[0].agent})"
    old, new = _of_run(tree, run_id), _of_run(replayed, run_id)
    finished = next(iter(_of_run(old, run_id, "run.finished")), None)
    _compare_calls(
        _in_step_order(_results(old), old), _in_step_order(_results(new), new), finished, label
    )
    if finished is not None:
        _compare_end(finished, next(iter(_of_run(new, run_id, "run.finished")), None), label)


def _plan(tree, root, can_read_project):
    """Return the ids of the runs that run again, parents first.

    The root runs again, and so does every nested run below it that ended with an answer.
    NOTE: a run with a project reads its plants and case through a workspace, which the log does
    not hold. Without one, as in a replay from the command line with no project folder, its nested
    runs are reused as before: their recorded answer and state changes.
    """
    ended = {e.run_id: e.stop_reason for e in tree if e.type == "run.finished"}
    plan = [root]
    if not can_read_project:
        return plan
    for parent in plan:
        plan.extend(c for c in _children(tree, parent).values() if ended.get(c) in ANSWERED)
    return plan


def _arm(engine, tree, scripts):
    """Give the engine what each run of the plan needs: its results, its model and its nested ids.

    A call that started a nested run of the plan is not reused: the nested run runs again, with a
    run id of the recording and a model of its own completions.
    """
    started = {e.run_id: e for e in tree if e.type == "run.started"}
    for parent in scripts:
        children = {k: r for k, r in _children(tree, parent).items() if r in scripts}
        engine.recorded[parent] = {
            key: event for key, event in scripts[parent].results.items() if key not in children
        }
        engine.recorded_changes[parent] = _nested_changes(tree, parent)
        engine.recorded_steps[parent] = [
            e.decision
            for e in tree
            if e.type == "permission" and e.run_id == parent and e.point == "steps"
        ]
        for child in children.values():
            task = started[child].messages[0].content if started[child].messages else None
            engine.recorded_children[(parent, started[child].parent_step, task)] = child
            engine.recorded_llms[child] = with_retries(scripts[child].llm)


def version_differences(events):
    """Return ``{name: (recorded, current)}`` for each recorded version that is not the current one.

    A log without versions, as 0.3.0 wrote, has none to compare. The replay runs either way.
    """
    started = next(e for e in events if e.type == "run.started" and e.parent is None)
    current = current_versions()
    return {
        name: (recorded, current.get(name))
        for name, recorded in started.versions.items()
        if recorded != current.get(name)
    }


def reuses_tool_results(started):
    """Tell whether a replay keeps the recorded tool results of a log, root ``run.started`` given.

    A log of another geomind version, or of one that recorded none (0.3.0), checks the agents'
    decisions, not the tools' outputs: a tool may have changed its input or its output since, and
    the log cannot tell a change of the tool from a change of the agent. NOTE: a difference in
    gemini alone still runs the tools, as it reports a difference in ``version_differences``.
    """
    return started.versions.get("geomind") != current_versions()["geomind"]


def nested_runs_reused(events, workspace):
    """Tell whether a replay with this ``workspace`` reuses the nested runs of the root run.

    That is the case for a run with a project when no workspace is given: the log holds no project
    files, so its nested runs keep their recorded answer.
    """
    root = next(e for e in events if e.type == "run.started" and e.parent is None)
    return (
        workspace is None and root.project is not None and len(_plan(events, root.run_id, True)) > 1
    )


async def replay_run(engine_class, store, run_id, *, replayed=None, workspace=None):
    """Rerun a stored run and every nested run of its tree with their recorded completions.

    ``read`` and ``compute`` tools run again, in every run; others reuse their recorded results, as
    do calls that were denied or answered by the user. A log of another geomind version (or with
    none recorded) reuses the result of every pure tool (``reuses_tool_results``); tools that
    write the problem state still run. A nested run that ended with an answer runs
    again as a nested run, matched to its call by the step and task, with the completions of its
    own events. A difference in any run raises ``ReplayError`` naming the run, its agent and the
    first differing step. ``replayed``, when a list, receives the events of the replayed tree;
    ``workspace`` is the project's, which nested runs of a run with a project need to run again.
    NOTE: ``replayed`` is the way to read the replay's log, since its store is internal and the
    return value stays a ``RunResult``.
    """
    tree = store.load_events(run_id)
    started = next((e for e in _of_run(tree, run_id) if e.type == "run.started"), None)
    if started is None:
        raise ReplayError(f"replay: run = {run_id!r}; no recorded run.started")
    can_read_project = workspace is not None or started.project is None
    scripts = {id_: _Script(_of_run(tree, id_)) for id_ in _plan(tree, run_id, can_read_project)}
    recording = _Recording(scripts)
    engine = engine_class(
        hooks=[recording],
        permissions=Permissions(mode="auto"),
        llm=scripts[run_id].llm,
        workspace=workspace,
        store=_ReplayStore(store, run_id, started.chat or started.root, _remade(tree, scripts)),
    )
    _arm(engine, tree, scripts)
    engine.reuses_tools = reuses_tool_results(started)
    context = Context(
        messages=list(started.messages),
        run_id=run_id,
        chat=started.chat,
        project=started.project,
        problem=ProblemState.model_validate(started.problem),
    )
    with runtime.settings(**runtime.stored(started.settings)):
        agent = agent_class(started)()
        agent.load_loop_state(started.loop_state)
        loop = _RecordedLoop(started) if started.loop else None
        result = await engine.run(agent, context, max_steps=started.max_steps, loop=loop)
    if recording.failure is not None:
        raise recording.failure
    log = engine.store.load_events(run_id)
    for id_ in reversed(list(scripts)):
        _compare_run(tree, log, id_)
    if replayed is not None:
        replayed.extend(log)
    return result

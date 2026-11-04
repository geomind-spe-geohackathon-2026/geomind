"""The project loop: the project lead, with the ``Verified`` hook on."""

from geomind.agents import ProjectLead
from geomind.engine.hooks import Verified
from geomind.loops import ProjectLoop
from tests.fixtures.runs import context, engine_for, says


async def test_it_runs_the_project_lead_with_the_verified_hook():
    """The hook is registered once, and the run is logged as the ``project`` loop."""
    engine = engine_for([says("done")])
    loop = ProjectLoop(ProjectLead())
    start = context()
    result = await loop.run(engine, start)
    loop.guard(engine)
    assert result.answer == "done"
    assert sum(isinstance(hook, Verified) for hook in engine.hooks()) == 1
    started = [e for e in engine.store.load_events(start.run_id) if e.type == "run.started"][0]
    assert (started.loop, started.agent) == ("project", "project_lead")

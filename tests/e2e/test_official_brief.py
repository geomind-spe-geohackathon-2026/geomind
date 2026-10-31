"""The official brief through ``geomind run --loop design``, offline from a scripted recording.

NOTE: the recording is written by hand, in the order the design loop asks its agents; every
reference and number in it comes from the real tools on the base design over the whole year. It
checks the path from the command line to a verified, costed and explained design, not a model.
"""

from pathlib import Path

from geomind import cli
from tests.fixtures import ROOT

RECORDING = ROOT / "evals" / "runs" / "official_brief_scripted.jsonl"
BRIEF = (
    "Design a deep-geothermal heating and cooling plant for the GEMINI hackathon brief: the "
    "official 2027 daily heating and cooling demand, the brief's reservoir and brine, and its hard "
    "limits."
)


def test_the_official_brief_gives_a_verified_design_that_replays(monkeypatch, tmp_path, capsys):
    """The run ends verified, with capacities, energies, costs and open points, and replays."""
    monkeypatch.chdir(tmp_path)
    arguments = ["run", BRIEF, "--loop", "design", "--mode", "auto", "--recording", str(RECORDING)]
    assert cli.main(arguments) == 0
    output = capsys.readouterr().out
    run = next(path for path in Path(".runs").iterdir() if path.name != "chats")
    assert "design loop: stop: verified after round 1" in output
    for heading in ("## Capacities", "## Delivered", "## Costs", "## Open points", "LCTS"):
        assert heading in output
    assert cli.main(["replay", str(run)]) == 0
    assert capsys.readouterr().out.startswith("pass:")

"""Shared test configuration: tiers, the speed budget, the development-profile guard, shards."""

import json
import re
from pathlib import Path
from time import perf_counter

import pytest

TIER_MARKERS = {
    "unit": pytest.mark.unit,
    "integration": pytest.mark.integration,
    "e2e": pytest.mark.e2e,
}
ROOT = Path(__file__).parents[1]
TEST_BUDGET_S = 1.0
SESSION_BUDGET_S = 300.0
SHARD_TIMES = json.loads((ROOT / "tests" / "fixtures" / "shard_times.json").read_text())
"""Seconds per slow test id, measured on the slow tier, which ``--shard`` balances."""
UNMEASURED_S = 60.0
"""The time a slow test without a measurement counts as, so a new one is not ignored."""


def pytest_addoption(parser):
    """Add the test profile and the shard options."""
    parser.addoption("--profile", choices=["development", "release"], default="release")
    parser.addoption("--shard", help="run shard index/count of the slow tests, such as 0/4")


def parse_shard(text):
    """Return ``(index, count)`` of a ``--shard`` value, or raise ``pytest.UsageError``."""
    found = re.fullmatch(r"(\d+)/(\d+)", text or "")
    if found is None or int(found[1]) >= int(found[2]):
        raise pytest.UsageError(f"--shard = {text!r}; expected index/count, index below count")
    return int(found[1]), int(found[2])


def shards(ids, times, count):
    """Return ``count`` lists of test ids, the longest first to the least loaded shard."""
    load = [0.0] * count
    found = [[] for _ in range(count)]
    for test in sorted(ids, key=lambda item: (-times.get(item, UNMEASURED_S), item)):
        index = load.index(min(load))
        found[index].append(test)
        load[index] += times.get(test, UNMEASURED_S)
    return found


def pytest_collection_modifyitems(config, items):
    """Mark every test from its top-level test folder; keep one shard of the slow tests."""
    tests = ROOT / "tests"
    for item in items:
        if not item.path.is_relative_to(tests):
            continue
        marker = TIER_MARKERS.get(item.path.relative_to(tests).parts[0])
        if marker is not None:
            item.add_marker(marker)
    if config.getoption("--shard"):
        keep_shard(config, items)


def keep_shard(config, items):
    """Deselect the slow tests of the other shards; every other test stays."""
    index, count = parse_shard(config.getoption("--shard"))
    slow = [item.nodeid for item in items if item.get_closest_marker("slow")]
    kept = set(shards(slow, SHARD_TIMES, count)[index])
    dropped = [
        item for item in items if item.get_closest_marker("slow") and item.nodeid not in kept
    ]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = [item for item in items if item not in dropped]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Fail a development-profile fast-tier call that exceeds the one-second budget."""
    outcome = yield
    report = outcome.get_result()
    markers = {marker.name for marker in item.iter_markers()}
    if (
        report.when == "call"
        and report.passed
        and report.duration > TEST_BUDGET_S
        and item.config.getoption("--profile") == "development"
        and not markers.intersection({"e2e", "slow"})
    ):
        report.outcome = "failed"
        report.longrepr = (
            f"Fast-tier test took {report.duration:.2f}s (budget: {TEST_BUDGET_S:.2f}s). "
            "Move it to slow or make it faster, see .claude/docs/testing.md."
        )


class DevelopmentBudget:
    """Fail a development-profile run whose wall time exceeds the session budget.

    Registered only in the controlling process, so under xdist it measures the whole parallel
    run and sees every worker's reports.
    """

    def __init__(self):
        """Start timing when the controller configures the session."""
        self.started = perf_counter()
        self.durations = []
        self.elapsed = 0.0

    def pytest_runtest_logreport(self, report):
        """Remember each test phase duration for the slowest-test listing."""
        self.durations.append((report.duration, report.when, report.nodeid))

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session):
        """Turn an over-budget run into a failed run."""
        self.elapsed = perf_counter() - self.started
        if self.elapsed > SESSION_BUDGET_S:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter):
        """Report the wall time, and explain an over-budget run with its slowest phases."""
        terminalreporter.write_line(f"Development profile took {self.elapsed:.1f}s")
        if self.elapsed <= SESSION_BUDGET_S:
            return
        terminalreporter.section("development profile over budget", red=True)
        terminalreporter.write_line(
            f"Run took {self.elapsed:.0f}s (budget: {SESSION_BUDGET_S:.0f}s). "
            "See .claude/docs/testing.md, section 'Test profiles'. Slowest tests:"
        )
        for duration, when, nodeid in sorted(self.durations, reverse=True)[:10]:
            terminalreporter.write_line(f"{duration:8.2f}s {when:<8} {nodeid}")


def pytest_configure(config):
    """Register the session budget for development-profile runs in the controller."""
    is_worker = hasattr(config, "workerinput")
    if config.getoption("--profile") == "development" and not is_worker:
        config.pluginmanager.register(DevelopmentBudget(), "development-budget")


TEST_MODEL = "deepseek/deepseek-v4.1-flash-1017"
TEST_CHEAP_MODEL = TEST_MODEL
TEST_CONTEXT_WINDOW = "128000"
TEST_RETRY_COUNT = "3"
TEST_RETRY_DELAY = "0.5"
TEST_MAX_STEPS = "30"


@pytest.fixture(autouse=True)
def no_env_files(monkeypatch):
    """Keep a developer's ``.env`` and key out of every test: no file is read, no key is set."""
    monkeypatch.setattr("geomind.cli.env_files", lambda: [])
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def deployment_settings(monkeypatch):
    """Name the models, the context window, the retries and the steps as a deployment does."""
    from geomind.runtime import ROLES, model_variable

    for role in ROLES:
        cheap = role in ("coordinator", "summarizer")
        monkeypatch.setenv(model_variable(role), TEST_CHEAP_MODEL if cheap else TEST_MODEL)
    monkeypatch.setenv("GEOMIND_CONTEXT_WINDOW", TEST_CONTEXT_WINDOW)
    monkeypatch.setenv("GEOMIND_RETRY_COUNT", TEST_RETRY_COUNT)
    monkeypatch.setenv("GEOMIND_RETRY_DELAY", TEST_RETRY_DELAY)
    monkeypatch.setenv("GEOMIND_MAX_STEPS", TEST_MAX_STEPS)
    monkeypatch.setenv("GEOMIND_MEMORY", "off")
    monkeypatch.setenv("GEOMIND_MAX_OUTPUT_TOKENS", "16000")
    monkeypatch.setenv("GEOMIND_DESIGN_CONCURRENCY", "3")


@pytest.fixture(autouse=True)
def no_loaded_windows():
    """Start each test without context windows read from a provider."""
    from geomind.context.compaction import forget_windows

    forget_windows()

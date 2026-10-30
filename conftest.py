"""Shared test configuration: tiers, the speed budget and the development-profile guard."""

from pathlib import Path
from time import perf_counter

import pytest

TIER_MARKERS = {
    "unit": pytest.mark.unit,
    "integration": pytest.mark.integration,
    "e2e": pytest.mark.e2e,
}
ROOT = Path(__file__).parent
TEST_BUDGET_S = 1.0
SESSION_BUDGET_S = 300.0


def pytest_addoption(parser):
    """Add the test profile option."""
    parser.addoption("--profile", choices=["development", "release"], default="release")


def pytest_collection_modifyitems(items):
    """Mark every test from its top-level test folder."""
    tests = ROOT / "tests"
    for item in items:
        if not item.path.is_relative_to(tests):
            continue
        marker = TIER_MARKERS.get(item.path.relative_to(tests).parts[0])
        if marker is not None:
            item.add_marker(marker)


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

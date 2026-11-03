"""``--shard i/n`` splits the slow tier by measured time, so CI runs it as parallel jobs."""

import pytest

from tests.conftest import SHARD_TIMES, parse_shard, shards


def test_every_test_is_in_exactly_one_shard():
    """No test is lost or run twice, whatever the times."""
    ids = [f"t{index}" for index in range(10)]
    found = shards(ids, {"t3": 50.0, "t7": 40.0}, 3)
    assert sorted(item for shard in found for item in shard) == sorted(ids)


def test_the_longest_tests_go_to_different_shards():
    """Greedy by time: the heavy tests spread out first."""
    times = {"a": 100.0, "b": 90.0, "c": 80.0, "d": 1.0}
    found = shards(list(times), times, 3)
    assert [sorted(shard) for shard in found] == [["a"], ["b"], ["c", "d"]]


def test_the_split_does_not_depend_on_the_order_of_collection():
    """Each CI job collects the same tests in its own order and must agree."""
    times = {"a": 3.0, "b": 2.0, "c": 1.0}
    assert shards(["c", "a", "b"], times, 2) == shards(["a", "b", "c"], times, 2)


@pytest.mark.parametrize(("text", "found"), [("0/4", (0, 4)), ("3/4", (3, 4))])
def test_a_shard_is_index_over_count(text, found):
    """The option reads ``index/count`` with the index below the count."""
    assert parse_shard(text) == found


@pytest.mark.parametrize("text", ["4/4", "-1/2", "1", "a/b"])
def test_a_wrong_shard_is_refused(text):
    """A wrong option stops the run instead of running the wrong tests."""
    with pytest.raises(pytest.UsageError):
        parse_shard(text)


def test_the_measured_times_name_slow_tests():
    """The times file holds seconds per test id, measured on the slow tier."""
    assert SHARD_TIMES and all(value > 0 for value in SHARD_TIMES.values())

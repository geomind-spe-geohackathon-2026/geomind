"""The files a case names: safe names, series files and the files economics.json names."""

import json

import pytest

from geomind.stores.casefiles import (
    case_files,
    economics_files,
    is_safe_name,
    named_files,
    series_files,
)

CASE = {
    "economics": "economics.json",
    "demand": {
        "heating": {"power": {"unit": "MW", "file": "data/demand.csv", "column": "heat"}},
        "cooling": {"power": {"unit": "MW", "file": "data/demand.csv", "column": "cold"}},
    },
}


@pytest.mark.parametrize("name", ["case.json", "data/demand.csv", "a/b/c.csv"])
def test_a_relative_path_of_plain_parts_is_safe(name):
    """Plain parts joined by a slash name a file inside the project."""
    assert is_safe_name(name) is True


@pytest.mark.parametrize(
    "name", ["", "/etc/passwd", "../x.csv", "data/../x.csv", "a//b", "./x", "C:/x", "a\\b", None, 3]
)
def test_an_absolute_or_escaping_name_is_not_safe(name):
    """Nothing absolute, no `..`, no empty part, no backslash, no drive."""
    assert is_safe_name(name) is False


def test_series_files_are_found_at_any_depth_in_order():
    """The `file` of every series is listed, also inside lists."""
    assert series_files({"a": [{"file": "x.csv"}, {"b": {"file": "y.csv"}}]}) == ["x.csv", "y.csv"]
    assert series_files("text") == []


def test_a_case_names_its_economics_file_and_its_series():
    """The economics file comes first, then the series, once per mention."""
    assert case_files(CASE) == ["economics.json", "data/demand.csv", "data/demand.csv"]


def test_an_inline_economics_is_not_a_file():
    """Economics written inside the case names no file of its own."""
    assert case_files({"economics": {"currency": "EUR"}}) == []


def test_the_files_economics_names_are_relative_to_its_folder():
    """A series in `sub/economics.json` is `sub/<file>`; broken JSON names nothing."""
    content = json.dumps({"price": {"file": "../prices.csv"}})
    assert economics_files("sub/economics.json", content) == ["prices.csv"]
    assert economics_files("economics.json", "not json") == []


def test_named_files_reads_each_file_once_and_follows_economics():
    """Files that exist are returned, those the economics file names too; others are skipped."""
    disk = {
        "economics.json": json.dumps({"price": {"file": "data/price.csv"}}).encode(),
        "data/demand.csv": b"time,heat\n",
        "data/price.csv": b"time,price\n",
    }
    reads = []

    def read(name):
        reads.append(name)
        return disk.get(name)

    assert set(named_files(CASE, read)) == set(disk)
    assert reads.count("data/demand.csv") == 1


def test_named_files_skips_a_missing_file_and_an_unsafe_name():
    """A file the project lacks is absent from the result, and an unsafe name is never read."""
    case = {
        "demand": {"heating": {"power": {"file": "../secret.csv"}}},
        "economics": "economics.json",
    }
    reads = []
    found = named_files(case, lambda name: reads.append(name))
    assert found == {}
    assert reads == ["economics.json"]

"""Sections of a long document by its markdown headings."""

from geomind.tools.sections import heading_path, outline, section_span

TEXT = "# 1 Intro\nx\n## Scope\ny\n# 2 Wells\n## 2.1 Pumps\nz\n```\n# not\n```\n## 2.2 Pipes\nw\n"


def test_the_outline_numbers_each_heading_and_skips_code():
    """Stated numbers are kept, others follow the tree; a heading in a fence is no heading."""
    found = outline(TEXT)
    assert [item["number"] for item in found] == ["1", "1.1", "2", "2.1", "2.2"]
    assert all(item["title"] != "not" for item in found)


def test_a_section_is_found_by_number_or_title_with_its_subsections():
    """``2`` holds 2.1 and 2.2; a part of a title finds it too."""
    wells = section_span(TEXT, "2")
    assert TEXT[wells["start"] : wells["end"]].count("##") == 2
    assert section_span(TEXT, "pipes")["number"] == "2.2"
    assert section_span(TEXT, "9.9") is None


def test_a_hit_names_its_heading_path():
    """The agent reads the whole section a search hit falls in."""
    assert heading_path(TEXT, TEXT.index("z")) == "2 Wells > 2.1 Pumps"

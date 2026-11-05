"""The sections of a long document by its markdown headings: outline, one section, a hit's path.

A handbook of 25 to 50 pages is read by section, not by character offset: ``outline`` lists the
heading tree, ``section_span`` finds one section by its number (``3.2``) or its title, and
``heading_path`` names the section a search hit falls in.
"""

import re

HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
FENCE = re.compile(r"^```.*?^```", re.M | re.S)
NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$")


def headings(text):
    """Return every heading as ``{level, number, title, start, end, size}``, in order.

    ``number`` is the one the title starts with (``3.2 Pumps``), else the place in the tree
    (``1``, ``1.2``); ``end`` is where the next heading of the same or a higher level starts, so
    a section holds its subsections. Headings inside code fences are skipped.
    """
    fenced = [(match.start(), match.end()) for match in FENCE.finditer(text)]
    found, counters = [], []
    for match in HEADING.finditer(text):
        if any(start <= match.start() < end for start, end in fenced):
            continue
        level, title = len(match.group(1)), match.group(2).strip()
        counters = (counters + [0] * level)[:level]
        counters[-1] += 1
        stated = NUMBER.match(title)
        number = stated.group(1) if stated else ".".join(str(item) for item in counters if item)
        found.append({"level": level, "number": number, "title": title, "start": match.start()})
    for index, item in enumerate(found):
        later = (other["start"] for other in found[index + 1 :] if other["level"] <= item["level"])
        item["end"] = next(later, len(text))
        item["size"] = item["end"] - item["start"]
    return found


def outline(text):
    """Return the heading tree of ``text``: one line each, indented by level, with offsets."""
    return [
        {key: item[key] for key in ("level", "number", "title", "start", "size")}
        for item in headings(text)
    ]


def section_span(text, key):
    """Return the heading of the section ``key`` names: its number, its title, or a part of it.

    ``None`` when no heading matches; an exact number or title wins over a title that holds it.
    A key of a number and a title that match no heading as a whole (``3 Wells``, QA-169) takes
    the heading whose title holds that title, else the heading of that number.
    """
    wanted = str(key).strip().lower().rstrip(".")
    found = headings(text)
    for test in (
        lambda item: item["number"] == wanted,
        lambda item: item["title"].lower() == wanted,
        lambda item: NUMBER.sub(r"\2", item["title"]).lower() == wanted,
        lambda item: wanted in item["title"].lower(),
    ):
        match = next((item for item in found if test(item)), None)
        if match is not None:
            return match
    numbered = NUMBER.match(wanted)
    if numbered:
        number, title = numbered.group(1), numbered.group(2).strip()
        for test in (
            lambda item: title and title in item["title"].lower(),
            lambda item: item["number"] == number,
        ):
            match = next((item for item in found if test(item)), None)
            if match is not None:
                return match
    return None


def label(item):
    """Return how a heading is listed: its title, with its number only if the title has none."""
    if NUMBER.match(item["title"]):
        return item["title"]
    return f"{item['number']} {item['title']}"


def heading_path(text, position):
    """Return the headings that hold ``position``, outermost first, as ``"3 Wells > 3.2 Pumps"``."""
    held = [item for item in headings(text) if item["start"] <= position < item["end"]]
    return " > ".join(item["title"] for item in held) or None

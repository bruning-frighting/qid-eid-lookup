"""Tests for qidlookup.utils.formatting."""

from __future__ import annotations

import json

from qidlookup.core.models import Mapping
from qidlookup.utils.formatting import (
    Colorizer,
    format_delimited,
    format_json,
    format_table,
    should_use_color,
)

MAPPING = Mapping(
    qid=5000849,
    eid="4662",
    devicetypeid=12,
    event_category="Success Audit",
    event_name="Success Audit: An operation was performed on an object",
    description="Success Audit: An operation was performed on an object.",
)


def test_format_table_aligns_columns():
    rows = [{"a": "1", "b": "long value"}, {"a": "22", "b": "x"}]
    text = format_table(rows, [("A", "a"), ("B", "b")])
    lines = text.splitlines()
    assert lines[0].startswith("A")
    assert "22" in lines[2]


def test_format_table_empty_rows():
    assert format_table([], [("A", "a")]) == "(no results)"


def test_format_json_roundtrip():
    text = format_json([MAPPING])
    data = json.loads(text)
    assert data[0]["qid"] == 5000849
    assert data[0]["eid"] == "4662"
    assert "devicetypeid" not in data[0]


def test_format_delimited_csv():
    text = format_delimited([MAPPING], ",")
    lines = text.strip().splitlines()
    assert lines[0] == (
        "qid,eid,event_category,event_name,description,"
        "severity,high_level_category,low_level_category"
    )
    assert "5000849" in lines[1]


def test_format_delimited_tsv():
    text = format_delimited([MAPPING], "\t")
    assert "\t" in text.splitlines()[0]


def test_colorizer_disabled_passes_through():
    colorize = Colorizer(enabled=False)
    assert colorize("hello", "red") == "hello"


def test_colorizer_enabled_wraps_ansi():
    colorize = Colorizer(enabled=True)
    result = colorize("hello", "red")
    assert result != "hello"
    assert "hello" in result


def test_should_use_color_respects_no_color_flag():
    class FakeTTY:
        def isatty(self):
            return True

    assert should_use_color(no_color=True, stream=FakeTTY()) is False
    assert should_use_color(no_color=False, stream=FakeTTY()) is True


def test_should_use_color_false_when_not_a_tty():
    class FakeFile:
        def isatty(self):
            return False

    assert should_use_color(no_color=False, stream=FakeFile()) is False

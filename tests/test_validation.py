"""Tests for qidlookup.utils.validation."""

from __future__ import annotations

import pytest

from qidlookup.utils.validation import (
    InputValidationError,
    parse_device_type_arg,
    parse_qid_arg,
    split_category_arg,
    split_csv_arg,
)


def test_parse_qid_arg_valid():
    assert parse_qid_arg("5000849") == 5000849


def test_parse_qid_arg_invalid_raises():
    with pytest.raises(InputValidationError, match="QID must be an integer"):
        parse_qid_arg("not-a-number")


def test_parse_device_type_arg_invalid_raises():
    with pytest.raises(InputValidationError, match="Device type must be an integer"):
        parse_device_type_arg("abc")


def test_split_csv_arg_trims_and_drops_empty():
    assert split_csv_arg("5000843, 5000849 ,,5000850") == ["5000843", "5000849", "5000850"]


def test_split_category_arg_combined_form():
    assert split_category_arg("System.Process Creation Success") == (
        "System",
        "Process Creation Success",
    )


def test_split_category_arg_with_space_after_dot():
    # QRadar's own UI renders "High Level. Low Level" with a space after the dot.
    assert split_category_arg("Audit. Command Execution Success") == (
        "Audit",
        "Command Execution Success",
    )


def test_split_category_arg_plain_low_level_only():
    assert split_category_arg("Process Creation Success") == (None, "Process Creation Success")


def test_split_category_arg_splits_on_first_dot_only():
    # A low level category name that itself might contain a dot is not
    # expected in practice, but splitting on the FIRST dot keeps the
    # behavior predictable rather than silently mangling later dots.
    high, low = split_category_arg("System.Sub.Category")
    assert high == "System"
    assert low == "Sub.Category"

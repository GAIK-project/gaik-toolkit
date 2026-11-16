"""Offline check for #98: each live date case is its own test, and only A2 and B4
are expected to fail, so the other six can fail."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "_live_date_extraction", Path(__file__).with_name("test_date_extraction.py")
)
live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live)


def test_each_live_date_case_is_a_separate_test():
    ids = [param.id for param in live.FORMAT_PARAMS]

    assert ids == ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4"]


def test_only_a2_and_b4_carry_an_xfail_mark():
    marked = {
        param.id
        for param in live.FORMAT_PARAMS
        if any(mark.name == "xfail" for mark in param.marks)
    }

    assert marked == {"A2", "B4"}
    assert not any(
        mark.name == "xfail" for mark in getattr(live.test_date_format_handling, "pytestmark", [])
    )

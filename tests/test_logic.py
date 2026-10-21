"""Tests for the pure decision helpers."""

from __future__ import annotations

from datetime import time

import pytest

from custom_components.valetudo_essentials.logic import (
    battery_ok,
    format_duration,
    in_time_window,
    is_active,
    is_parked,
    low_consumables,
    normalize_presence,
    parse_percentage,
    parse_time,
    split_service,
    weekday_allowed,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("22:15", time(22, 15)),
        ("07:05:30", time(7, 5, 30)),
        ("7:05", time(7, 5)),
        (time(9, 30), time(9, 30)),
        ("", None),
        ("nope", None),
        ("25:00", None),
        ("12:99", None),
    ],
)
def test_parse_time(value, expected):
    assert parse_time(value) == expected


def test_parse_time_default():
    fallback = time(8, 0)
    assert parse_time("bad", fallback) == fallback
    assert parse_time(None, fallback) == fallback


@pytest.mark.parametrize(
    ("now", "start", "end", "expected"),
    [
        (time(23, 0), time(22, 0), time(7, 0), True),
        (time(6, 59), time(22, 0), time(7, 0), True),
        (time(7, 0), time(22, 0), time(7, 0), False),
        (time(12, 0), time(22, 0), time(7, 0), False),
        (time(13, 0), time(13, 0), time(15, 0), True),
        (time(15, 0), time(13, 0), time(15, 0), False),
        (time(14, 0), time(14, 0), time(14, 0), False),
    ],
)
def test_in_time_window(now, start, end, expected):
    assert in_time_window(now, start, end) is expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("home", True),
        ("on", True),
        ("0", False),
        ("1", True),
        ("2", True),
        ("not_home", False),
        ("off", False),
        ("unknown", None),
        ("unavailable", None),
        (None, None),
        ("something", None),
    ],
)
def test_normalize_presence(state, expected):
    assert normalize_presence(state) is expected


@pytest.mark.parametrize(
    ("battery", "minimum", "expected"),
    [
        (80, 20, True),
        ("80%", 20, True),
        (20, 20, True),
        (19, 20, False),
        ("unknown", 20, True),
        (None, 20, True),
    ],
)
def test_battery_ok(battery, minimum, expected):
    assert battery_ok(battery, minimum) is expected


def test_vacuum_state_helpers():
    assert is_parked("docked")
    assert is_parked("idle")
    assert not is_parked("cleaning")
    assert is_active("cleaning")
    assert is_active("moving")
    assert not is_active("paused")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("59", 59.0),
        ("59%", 59.0),
        (0, 0.0),
        ("unknown", None),
        ("unavailable", None),
        (None, None),
        ("nope", None),
    ],
)
def test_parse_percentage(value, expected):
    assert parse_percentage(value) == expected


def test_low_consumables():
    values = {
        "sensor.main_brush": "8",
        "sensor.filter": 10,
        "sensor.mop_pad": "55",
        "sensor.dead": "unknown",
    }
    assert low_consumables(values, 10) == [("sensor.main_brush", 8.0)]


@pytest.mark.parametrize(
    ("weekday", "days", "expected"),
    [
        (0, ["mon"], True),
        (0, ["MON", "tue"], True),
        (6, ["mon", "tue"], False),
        (2, [], False),
        (9, ["mon"], False),
    ],
)
def test_weekday_allowed(weekday, days, expected):
    assert weekday_allowed(weekday, days) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("notify.mobile_app_phone", ("notify", "mobile_app_phone")),
        ("script.after_vacuum", ("script", "after_vacuum")),
        ("mobile_app_phone", None),
        ("", None),
        (None, None),
        ("notify.bad.service", None),
        ("notify. bad", None),
    ],
)
def test_split_service(value, expected):
    assert split_service(value) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0 s"),
        (30, "30 s"),
        (60, "1 min"),
        (3599, "59 min"),
        (3600, "1 h"),
        (3900, "1 h 5 min"),
        (-10, "0 s"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected

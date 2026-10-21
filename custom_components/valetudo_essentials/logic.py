"""Pure helper functions used by the Valetudo Essentials engine.

Keeping these functions free of Home Assistant imports makes the decision
logic easy to test and reuse.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import time
from typing import Any

from .const import ACTIVE_STATES, PARKED_STATES, WEEKDAYS

HOME_STATES = frozenset({"home", "on", "true", "occupied", "present"})
AWAY_STATES = frozenset({"not_home", "off", "false", "unoccupied", "absent"})
UNKNOWN_STATES = frozenset({"unknown", "unavailable", "none", ""})


def parse_time(value: Any, default: time | None = None) -> time | None:
    """Parse a time value from a config entry or selector."""
    if isinstance(value, time):
        return value
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    parts = text.split(":")
    if len(parts) not in (2, 3):
        return default
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(float(parts[2])) if len(parts) == 3 else 0
    except (TypeError, ValueError):
        return default
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return default
    return time(hour, minute, second)


def in_time_window(now: time, start: time, end: time) -> bool:
    """Return True when now is inside the (possibly overnight) window."""
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


def normalize_presence(state: str | None) -> bool | None:
    """Normalize person, device tracker, zone, and helper states."""
    if state is None:
        return None
    text = state.strip().lower()
    if text in UNKNOWN_STATES:
        return None
    if text in HOME_STATES:
        return True
    if text in AWAY_STATES:
        return False
    try:
        return float(text) > 0
    except ValueError:
        return None


def battery_ok(value: Any, minimum: float) -> bool:
    """Return True when the battery is high enough (or unknown)."""
    if value is None:
        return True
    try:
        level = float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return True
    return level >= minimum


def is_parked(state: str | None) -> bool:
    """Return True when the vacuum is ready for a new cleaning run."""
    return state in PARKED_STATES


def is_active(state: str | None) -> bool:
    """Return True when the vacuum is actively cleaning or moving."""
    return state in ACTIVE_STATES


def parse_percentage(value: Any) -> float | None:
    """Parse a percentage state, returning None for unusable values."""
    if value is None:
        return None
    text = str(value).strip().rstrip("%").strip()
    if text.lower() in UNKNOWN_STATES:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def low_consumables(values: Mapping[str, Any], threshold: float) -> list[tuple[str, float]]:
    """Return (entity_id, percentage) pairs below the threshold."""
    result: list[tuple[str, float]] = []
    for entity_id, value in values.items():
        percentage = parse_percentage(value)
        if percentage is not None and percentage < threshold:
            result.append((entity_id, percentage))
    return result


def weekday_allowed(weekday: int, days: Iterable[str]) -> bool:
    """Return True when a zero-based weekday (Monday=0) is selected."""
    allowed = {str(day).lower() for day in days}
    return 0 <= weekday < len(WEEKDAYS) and WEEKDAYS[weekday] in allowed


def split_service(value: str | None) -> tuple[str, str] | None:
    """Split a service reference into domain and service."""
    if not value:
        return None
    text = value.strip()
    if not text or " " in text or "." not in text:
        return None
    domain, service = text.split(".", 1)
    if not domain or not service or "." in service:
        return None
    return domain, service


def format_duration(seconds: float) -> str:
    """Format a duration for a notification."""
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours} h {minutes} min"
    if hours:
        return f"{hours} h"
    if minutes:
        return f"{minutes} min"
    return f"{seconds} s"


def format_number(value: float) -> str:
    """Format a number without a needless decimal part."""
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"

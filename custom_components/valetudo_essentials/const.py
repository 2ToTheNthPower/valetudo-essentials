"""Constants for the Valetudo Essentials integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

DOMAIN: Final = "valetudo_essentials"
NAME: Final = "Valetudo Essentials"
VERSION: Final = "0.1.0"

CONF_VACUUM_ENTITY: Final = "vacuum_entity"
CONF_PRESENCE_ENTITY: Final = "presence_entity"
CONF_BATTERY_MIN: Final = "battery_min"
CONF_FAN_ENTITY: Final = "fan_entity"
CONF_FAN_SPEED: Final = "fan_speed"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_POST_RUN_SERVICE: Final = "post_run_service"

CONF_AWAY_ENABLED: Final = "away_enabled"
CONF_AWAY_DELAY: Final = "away_delay"

CONF_HOME_ENABLED: Final = "home_enabled"
CONF_HOME_ACTION: Final = "home_action"

CONF_QUIET_ENABLED: Final = "quiet_enabled"
CONF_QUIET_START: Final = "quiet_start"
CONF_QUIET_END: Final = "quiet_end"
CONF_QUIET_ACTION: Final = "quiet_action"
CONF_QUIET_RESUME: Final = "quiet_resume"

CONF_SCHEDULE_ENABLED: Final = "schedule_enabled"
CONF_SCHEDULE_DAYS: Final = "schedule_days"
CONF_SCHEDULE_TIME: Final = "schedule_time"
CONF_SCHEDULE_ONLY_WHEN_AWAY: Final = "schedule_only_when_away"

CONF_ERROR_ENABLED: Final = "error_enabled"
CONF_ERROR_NOTIFY_SERVICE: Final = "error_notify_service"
CONF_COMPLETION_ENABLED: Final = "completion_enabled"
CONF_COMPLETION_NOTIFY_SERVICE: Final = "completion_notify_service"

CONF_MAINTENANCE_ENABLED: Final = "maintenance_enabled"
CONF_MAINTENANCE_SENSORS: Final = "maintenance_sensors"
CONF_MAINTENANCE_THRESHOLD: Final = "maintenance_threshold"
CONF_MAINTENANCE_TIME: Final = "maintenance_time"

CONF_AUTO_EMPTY_ENABLED: Final = "auto_empty_enabled"
CONF_AUTO_EMPTY_ENTITY: Final = "auto_empty_entity"

DEFAULT_PRESENCE_ENTITY: Final = "zone.home"
DEFAULT_BATTERY_MIN: Final = 20
DEFAULT_FAN_SPEED: Final = "no_change"
DEFAULT_AWAY_DELAY: Final = 5
DEFAULT_HOME_ACTION: Final = "return_to_base"
DEFAULT_QUIET_START: Final = "22:00:00"
DEFAULT_QUIET_END: Final = "07:00:00"
DEFAULT_QUIET_ACTION: Final = "pause"
DEFAULT_SCHEDULE_DAYS: Final = ["mon", "tue", "wed", "thu", "fri"]
DEFAULT_SCHEDULE_TIME: Final = "09:00:00"
DEFAULT_MAINTENANCE_THRESHOLD: Final = 10
DEFAULT_MAINTENANCE_TIME: Final = "18:00:00"

FAN_SPEEDS: Final = (
    "no_change",
    "off",
    "min",
    "low",
    "medium",
    "high",
    "turbo",
    "max",
)

ACTIONS: Final = ("return_to_base", "pause", "stop")

WEEKDAYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_LABELS: Final = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}

STATE_CLEANING: Final = "cleaning"
STATE_MOVING: Final = "moving"
STATE_PAUSED: Final = "paused"
STATE_RETURNING: Final = "returning"
STATE_ERROR: Final = "error"
STATE_DOCKED: Final = "docked"
STATE_IDLE: Final = "idle"
STATE_CHARGING: Final = "charging"

PARKED_STATES: Final = frozenset({STATE_DOCKED, STATE_IDLE, STATE_CHARGING})
TERMINAL_STATES: Final = frozenset({STATE_DOCKED, STATE_IDLE, STATE_CHARGING})
ACTIVE_STATES: Final = frozenset({STATE_CLEANING, STATE_MOVING})
INTERRUPTIBLE_STATES: Final = frozenset({STATE_CLEANING, STATE_MOVING, STATE_PAUSED})

DEFAULT_OPTIONS: Final[dict[str, Any]] = {
    CONF_PRESENCE_ENTITY: DEFAULT_PRESENCE_ENTITY,
    CONF_BATTERY_MIN: DEFAULT_BATTERY_MIN,
    CONF_FAN_ENTITY: "",
    CONF_FAN_SPEED: DEFAULT_FAN_SPEED,
    CONF_NOTIFY_SERVICE: "",
    CONF_POST_RUN_SERVICE: "",
    CONF_AWAY_ENABLED: True,
    CONF_AWAY_DELAY: DEFAULT_AWAY_DELAY,
    CONF_HOME_ENABLED: True,
    CONF_HOME_ACTION: DEFAULT_HOME_ACTION,
    CONF_QUIET_ENABLED: True,
    CONF_QUIET_START: DEFAULT_QUIET_START,
    CONF_QUIET_END: DEFAULT_QUIET_END,
    CONF_QUIET_ACTION: DEFAULT_QUIET_ACTION,
    CONF_QUIET_RESUME: True,
    CONF_SCHEDULE_ENABLED: False,
    CONF_SCHEDULE_DAYS: list(DEFAULT_SCHEDULE_DAYS),
    CONF_SCHEDULE_TIME: DEFAULT_SCHEDULE_TIME,
    CONF_SCHEDULE_ONLY_WHEN_AWAY: False,
    CONF_ERROR_ENABLED: True,
    CONF_ERROR_NOTIFY_SERVICE: "",
    CONF_COMPLETION_ENABLED: False,
    CONF_COMPLETION_NOTIFY_SERVICE: "",
    CONF_MAINTENANCE_ENABLED: True,
    CONF_MAINTENANCE_SENSORS: [],
    CONF_MAINTENANCE_THRESHOLD: DEFAULT_MAINTENANCE_THRESHOLD,
    CONF_MAINTENANCE_TIME: DEFAULT_MAINTENANCE_TIME,
    CONF_AUTO_EMPTY_ENABLED: False,
    CONF_AUTO_EMPTY_ENTITY: "",
}


@dataclass(frozen=True, slots=True)
class Automation:
    """Metadata for one built-in automation switch."""

    key: str
    translation_key: str
    icon: str
    description: str


AUTOMATIONS: Final[tuple[Automation, ...]] = (
    Automation(
        CONF_AWAY_ENABLED,
        "clean_when_away",
        "mdi:home-export-outline",
        "Start cleaning when everybody leaves home.",
    ),
    Automation(
        CONF_HOME_ENABLED,
        "dock_when_home",
        "mdi:home-import-outline",
        "Pause, stop, or dock the vacuum when somebody comes home.",
    ),
    Automation(
        CONF_QUIET_ENABLED,
        "quiet_hours",
        "mdi:weather-night",
        "Keep the vacuum quiet during a nightly time window.",
    ),
    Automation(
        CONF_SCHEDULE_ENABLED,
        "schedule",
        "mdi:calendar-clock",
        "Run a weekly cleaning schedule.",
    ),
    Automation(
        CONF_ERROR_ENABLED,
        "error_notifications",
        "mdi:alert-circle-outline",
        "Send a notification when the vacuum reports an error.",
    ),
    Automation(
        CONF_COMPLETION_ENABLED,
        "completion_notifications",
        "mdi:check-circle-outline",
        "Send a notification when a cleaning run finishes.",
    ),
    Automation(
        CONF_MAINTENANCE_ENABLED,
        "maintenance_reminders",
        "mdi:wrench-clock",
        "Remind you when consumables or dock supplies are running low.",
    ),
    Automation(
        CONF_AUTO_EMPTY_ENABLED,
        "auto_empty",
        "mdi:delete-empty-outline",
        "Trigger the auto-empty dock after every completed run.",
    ),
)

AUTOMATION_KEYS: Final = frozenset(automation.key for automation in AUTOMATIONS)

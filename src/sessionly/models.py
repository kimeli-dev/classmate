"""Domain objects shared by services and the UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


DAY_SHORT = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

# Quick picks for the day selector; any combination of days can also be ticked by hand.
DAY_PRESETS = [
    ("Weekdays", (0, 1, 2, 3, 4)),
    ("Mon & Wed", (0, 2)),
    ("Tue & Thu", (1, 3)),
    ("Mon, Wed & Fri", (0, 2, 4)),
    ("Every day", (0, 1, 2, 3, 4, 5, 6)),
]


class Platform(StrEnum):
    ZOOM = "zoom"
    GOOGLE_MEET = "google_meet"
    TEAMS = "teams"
    OTHER = "other"

    @property
    def label(self) -> str:
        return {"zoom": "Zoom", "google_meet": "Google Meet", "teams": "Microsoft Teams", "other": "Other"}[self.value]


class LinkStatus(StrEnum):
    UNVERIFIED = "unverified"  # format looks right; never confirmed to work
    WORKED = "worked"          # the user confirmed it opened the meeting
    FAILED = "failed"          # judged invalid or expired; replacement needed

    @property
    def label(self) -> str:
        return {"unverified": "Link not yet tested", "worked": "Worked last time", "failed": "Needs replacement"}[self.value]


class FailureReason(StrEnum):
    NO_INTERNET = "no_internet"
    HOST_NOT_STARTED = "host_not_started"
    WAITING_ROOM = "waiting_room"
    AUTHENTICATION = "authentication"
    INVALID_LINK = "invalid_link"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            "no_internet": "My internet connection was down",
            "host_not_started": "The host had not started the meeting yet",
            "waiting_room": "I was stuck in the waiting room / waiting for admission",
            "authentication": "It asked me to sign in or for a passcode",
            "invalid_link": "The meeting was not found, has ended, or the link is invalid",
            "unknown": "Something else / I'm not sure",
        }[self.value]

    @property
    def link_is_suspect(self) -> bool:
        """Only these reasons justify asking for a replacement link."""
        return self in (FailureReason.INVALID_LINK, FailureReason.UNKNOWN)


class ExceptionKind(StrEnum):
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"
    EXTRA = "extra"


class SessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    REMINDED = "reminded"
    LINK_OPENED = "link_opened"  # Sessionly handed the link to the browser - NOT proof of joining
    JOINED = "joined"            # only ever set by the user's own confirmation
    NOT_JOINED = "not_joined"
    MISSED = "missed"            # time passed while Sessionly was closed or the laptop slept

    @property
    def label(self) -> str:
        return {
            "scheduled": "Scheduled",
            "reminded": "Reminder shown",
            "link_opened": "Link opened - not confirmed",
            "joined": "Joined - you confirmed",
            "not_joined": "Couldn't join",
            "missed": "Not handled - laptop asleep or Sessionly closed",
        }[self.value]


@dataclass
class Session:
    id: int
    meeting_id: int
    scheduled_start: datetime
    scheduled_end: datetime
    status: SessionStatus
    reminded_at: str | None
    link_opened_at: str | None
    confirmed_at: str | None
    failure_reason: str | None


@dataclass
class Meeting:
    id: int | None
    name: str
    short_code: str = ""
    host_name: str = ""
    preferred_display_name: str | None = None
    automation_enabled: bool = True
    notifications_enabled: bool = True
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def title(self) -> str:
        return f"{self.short_code} - {self.name}" if self.short_code else self.name


@dataclass
class Schedule:
    id: int | None
    meeting_id: int
    day_of_week: int  # 0 = Monday
    start_time: time
    duration_minutes: int
    preparation_minutes: int = 5
    timezone: str = "local"
    enabled: bool = True

    @property
    def end_time(self) -> time:
        return (datetime.combine(date(2000, 1, 3), self.start_time) + timedelta(minutes=self.duration_minutes)).time()

    def describe(self) -> str:
        return (f"{DAY_NAMES[self.day_of_week]} {self.start_time:%H:%M}-{self.end_time:%H:%M}"
                f" ({self.duration_minutes} min, prepare {self.preparation_minutes} min before)")


@dataclass
class ScheduleException:
    id: int | None
    meeting_id: int
    kind: ExceptionKind
    schedule_id: int | None = None
    original_date: date | None = None
    new_start: datetime | None = None
    new_duration_minutes: int | None = None
    note: str = ""


@dataclass
class MeetingLink:
    id: int
    meeting_id: int
    url: str
    platform: Platform
    source: str
    status: LinkStatus
    notes: str
    is_current: bool
    created_at: str
    updated_at: str
    last_success_at: str | None
    last_failure_at: str | None
    failure_reason: FailureReason | None
    passcode: str = ""   # Zoom passcode shared by the host; never logged


@dataclass(frozen=True)
class Occurrence:
    """One concrete session produced from the schedule."""

    meeting_id: int
    meeting_title: str
    start: datetime
    end: datetime
    preparation_minutes: int
    origin: str  # "weekly", "rescheduled" or "extra"
    schedule_id: int | None = None
    cancelled: bool = False
    note: str = ""

    def overlaps(self, other: Occurrence) -> bool:
        return self.start < other.end and other.start < self.end

"""Decides what the background worker should do at a given moment.

The engine is pure logic (no Qt) so it can be tested with a fake clock. Every decision is
persisted through ``SessionService.transition(..., expect=...)`` before it is returned, so
running ``tick`` twice - or after a restart - never repeats a reminder or opens a link twice.
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sessionly.models import Occurrence, Session, LinkStatus, SessionStatus
from sessionly.services.meetings import MeetingService
from sessionly.services.links import LinkService
from sessionly.services.schedules import ScheduleService
from sessionly.services.sessions import SessionService
from sessionly.services.settings import AUTO_OPEN_LINKS, AUTOMATION_PAUSED, SettingsService

log = logging.getLogger(__name__)

LATE_AFTER = timedelta(minutes=10)   # woke up / started this long after the session start -> don't auto-open
MISSED_LOOKBACK = timedelta(hours=24)
SOON_WINDOW = timedelta(minutes=60)


def has_internet(timeout: float = 2.0) -> bool:
    """Cheap reachability check (TCP connect to a public DNS resolver)."""
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class Action:
    kind: str  # "remind" | "open_link" | "offline" | "missed"
    title: str
    message: str
    occurrence: Occurrence | None = None
    session: Session | None = None
    url: str | None = None


@dataclass
class LiveInfo:
    """What is happening right now - drives the tray icon and the dashboard's live card."""

    kind: str  # "paused" | "idle" | "soon" | "live"
    occurrence: Occurrence | None = None
    session: Session | None = None
    next_occurrence: Occurrence | None = None

    @property
    def status(self) -> SessionStatus | None:
        return self.session.status if self.session else None


class AutomationEngine:
    def __init__(self, meetings: MeetingService, schedules: ScheduleService, links: LinkService,
                 sessions: SessionService, settings: SettingsService,
                 online: Callable[[], bool] = has_internet) -> None:
        self.meetings = meetings
        self.schedules = schedules
        self.links = links
        self.sessions = sessions
        self.settings = settings
        self.online = online
        self._offline_warned: set[int] = set()

    @property
    def paused(self) -> bool:
        return bool(self.settings.get(AUTOMATION_PAUSED, False))

    def tick(self, now: datetime) -> list[Action]:
        if self.paused:
            return []
        meetings = {c.id: c for c in self.meetings.list()}
        occurrences = self.schedules.occurrences((now - MISSED_LOOKBACK).date(), now.date())
        auto_open = bool(self.settings.get(AUTO_OPEN_LINKS, False))
        actions: list[Action] = []
        missed: list[Occurrence] = []

        for occ in occurrences:
            meeting = meetings.get(occ.meeting_id)
            prep = occ.start - timedelta(minutes=occ.preparation_minutes)
            if occ.cancelled or meeting is None or now < prep or now - occ.end > MISSED_LOOKBACK:
                continue
            session = self.sessions.ensure(occ)
            if session.status != SessionStatus.SCHEDULED:
                continue

            if now >= occ.end:
                if self.sessions.transition(session.id, SessionStatus.MISSED, expect=SessionStatus.SCHEDULED):
                    missed.append(occ)
                continue

            link = self.links.current(occ.meeting_id)
            late = now > occ.start + LATE_AFTER
            can_open = (auto_open and meeting.automation_enabled and link is not None
                        and link.status != LinkStatus.FAILED and not late)

            if can_open:
                if not self.online():
                    if session.id not in self._offline_warned:
                        self._offline_warned.add(session.id)
                        actions.append(Action("offline", f"{occ.meeting_title} - no internet",
                                              "Sessionly will open the link as soon as you're back online.",
                                              occ, session))
                    continue  # stays SCHEDULED; retried next tick until it becomes late
                if self.sessions.transition(session.id, SessionStatus.LINK_OPENED, expect=SessionStatus.SCHEDULED):
                    actions.append(Action(
                        "open_link", f"Opening {occ.meeting_title}",
                        f"Starts at {occ.start:%H:%M}. Sessionly opened the link - tap \"I'm in\" once you've joined.",
                        occ, self.sessions.find(occ.meeting_id, occ.start), link.url))
                continue

            if self.sessions.transition(session.id, SessionStatus.REMINDED, expect=SessionStatus.SCHEDULED):
                if not meeting.notifications_enabled:
                    continue
                if late:
                    detail = (f"Started at {occ.start:%H:%M}. You may have missed the start - "
                              "the laptop was asleep or Sessionly wasn't running.")
                elif link is None:
                    detail = f"Starts at {occ.start:%H:%M}. No meeting link saved - add it in Sessionly."
                elif link.status == LinkStatus.FAILED:
                    detail = f"Starts at {occ.start:%H:%M}. The saved link needs replacing."
                else:
                    detail = f"Starts at {occ.start:%H:%M} on {link.platform.label}."
                actions.append(Action("remind", occ.meeting_title, detail, occ, session,
                                      link.url if link and link.status != LinkStatus.FAILED else None))

        if missed:
            names = ", ".join(f"{o.meeting_title} ({o.start:%a %H:%M})" for o in missed)
            actions.append(Action("missed", "Sessions passed while Sessionly was off",
                                  f"Not handled: {names}. Nothing was opened for them."))
        return actions

    def live(self, now: datetime) -> LiveInfo:
        if self.paused:
            return LiveInfo("paused")
        occurrences = [o for o in self.schedules.occurrences(now.date(), (now + timedelta(days=7)).date())
                       if not o.cancelled]
        for occ in occurrences:
            if occ.start - timedelta(minutes=occ.preparation_minutes) <= now < occ.end:
                return LiveInfo("live", occ, self.sessions.find(occ.meeting_id, occ.start))
        upcoming = [o for o in occurrences if o.start > now]
        nxt = upcoming[0] if upcoming else None
        if nxt and nxt.start - now <= SOON_WINDOW:
            return LiveInfo("soon", nxt, self.sessions.find(nxt.meeting_id, nxt.start), nxt)
        return LiveInfo("idle", next_occurrence=nxt)

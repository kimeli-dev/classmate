"""Weekly schedule, one-off changes, and expansion into concrete sessions.

Times are local wall-clock times (``timezone = 'local'``): a session at 10:00 stays at
10:00 even if the laptop's clock changes for daylight saving.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, time, timedelta
from itertools import combinations

from sessionly.db import Database, utc_now
from sessionly.models import DAY_NAMES, Occurrence, Meeting, ExceptionKind, Schedule, ScheduleException
from sessionly.services import ValidationError

log = logging.getLogger(__name__)

MINUTES_PER_WEEK = 7 * 24 * 60


def _row_to_schedule(row: sqlite3.Row) -> Schedule:
    return Schedule(
        id=row["id"],
        meeting_id=row["meeting_id"],
        day_of_week=row["day_of_week"],
        start_time=time.fromisoformat(row["start_time"]),
        duration_minutes=row["duration_minutes"],
        preparation_minutes=row["preparation_minutes"],
        timezone=row["timezone"],
        enabled=bool(row["enabled"]),
    )


def _row_to_exception(row: sqlite3.Row) -> ScheduleException:
    return ScheduleException(
        id=row["id"],
        meeting_id=row["meeting_id"],
        kind=ExceptionKind(row["kind"]),
        schedule_id=row["schedule_id"],
        original_date=date.fromisoformat(row["original_date"]) if row["original_date"] else None,
        new_start=datetime.fromisoformat(row["new_start"]) if row["new_start"] else None,
        new_duration_minutes=row["new_duration_minutes"],
        note=row["note"],
    )


def _week_intervals(day: int, start: time, duration: int) -> list[tuple[int, int]]:
    """Minute-of-week intervals, split in two if the session wraps past Sunday midnight."""
    begin = day * 1440 + start.hour * 60 + start.minute
    end = begin + duration
    if end <= MINUTES_PER_WEEK:
        return [(begin, end)]
    return [(begin, MINUTES_PER_WEEK), (0, end - MINUTES_PER_WEEK)]


class ScheduleService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- weekly schedules -------------------------------------------------

    @staticmethod
    def _validate(s: Schedule) -> None:
        if not 0 <= s.day_of_week <= 6:
            raise ValidationError("Please choose a day of the week.")
        if not 1 <= s.duration_minutes <= 720:
            raise ValidationError("Duration must be between 1 minute and 12 hours.")
        if not 0 <= s.preparation_minutes <= 120:
            raise ValidationError("Preparation time must be between 0 and 120 minutes.")

    def add(self, s: Schedule) -> Schedule:
        self._validate(s)
        now = utc_now()
        with self.db.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO schedules (meeting_id, day_of_week, start_time, duration_minutes, preparation_minutes,
                       timezone, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s.meeting_id, s.day_of_week, s.start_time.strftime("%H:%M"), s.duration_minutes,
                 s.preparation_minutes, s.timezone, int(s.enabled), now, now),
            )
        log.info("Added schedule id=%s for meeting id=%s", cur.lastrowid, s.meeting_id)
        return self.get(cur.lastrowid)

    def update(self, s: Schedule) -> Schedule:
        self._validate(s)
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE schedules SET day_of_week = ?, start_time = ?, duration_minutes = ?, preparation_minutes = ?,
                       enabled = ?, updated_at = ? WHERE id = ?""",
                (s.day_of_week, s.start_time.strftime("%H:%M"), s.duration_minutes, s.preparation_minutes,
                 int(s.enabled), utc_now(), s.id),
            )
        return self.get(s.id)

    def delete(self, schedule_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))

    def get(self, schedule_id: int) -> Schedule:
        row = self.db.conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        if row is None:
            raise ValidationError("That weekly time no longer exists.")
        return _row_to_schedule(row)

    def for_meeting(self, meeting_id: int) -> list[Schedule]:
        rows = self.db.conn.execute(
            "SELECT * FROM schedules WHERE meeting_id = ? ORDER BY day_of_week, start_time", (meeting_id,)
        ).fetchall()
        return [_row_to_schedule(r) for r in rows]

    def weekly_conflicts(self, day: int, start: time, duration: int,
                         exclude_schedule_id: int | None = None) -> list[str]:
        """Describe enabled weekly sessions that would overlap the proposed slot."""
        proposed = _week_intervals(day, start, duration)
        rows = self.db.conn.execute(
            """SELECT s.*, c.name AS meeting_name FROM schedules s JOIN meetings c ON c.id = s.meeting_id
               WHERE s.enabled = 1 AND s.id IS NOT ?""",
            (exclude_schedule_id,),
        ).fetchall()
        clashes = []
        for row in rows:
            other = _row_to_schedule(row)
            for a0, a1 in proposed:
                if any(a0 < b1 and b0 < a1 for b0, b1 in
                       _week_intervals(other.day_of_week, other.start_time, other.duration_minutes)):
                    clashes.append(f"{row['meeting_name']} ({other.describe()})")
                    break
        return clashes

    # ---- one-off changes --------------------------------------------------

    def add_exception(self, e: ScheduleException) -> ScheduleException:
        if e.kind in (ExceptionKind.CANCELLED, ExceptionKind.RESCHEDULED):
            if e.schedule_id is None or e.original_date is None:
                raise ValidationError("Choose which regular session and date this change applies to.")
            sched = self.get(e.schedule_id)
            if sched.meeting_id != e.meeting_id:
                raise ValidationError("That weekly time belongs to a different meeting.")
            if e.original_date.weekday() != sched.day_of_week:
                raise ValidationError(
                    f"{e.original_date:%d %b %Y} is a {DAY_NAMES[e.original_date.weekday()]}, "
                    f"but this meeting is on {DAY_NAMES[sched.day_of_week]}s."
                )
        if e.kind == ExceptionKind.CANCELLED:
            e.new_start = None
            e.new_duration_minutes = None
        else:
            if e.new_start is None:
                raise ValidationError("Choose the new date and time.")
            if e.kind == ExceptionKind.EXTRA:
                e.schedule_id = None
                e.original_date = None
                if not e.new_duration_minutes:
                    raise ValidationError("Enter how long the extra session lasts.")
        try:
            with self.db.transaction() as conn:
                cur = conn.execute(
                    """INSERT INTO schedule_exceptions (meeting_id, schedule_id, kind, original_date, new_start,
                           new_duration_minutes, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (e.meeting_id, e.schedule_id, e.kind.value,
                     e.original_date.isoformat() if e.original_date else None,
                     e.new_start.isoformat(timespec="minutes") if e.new_start else None,
                     e.new_duration_minutes, e.note.strip(), utc_now()),
                )
        except sqlite3.IntegrityError as exc:
            if "ux_exceptions_occurrence" in str(exc) or "UNIQUE" in str(exc):
                raise ValidationError("That session already has a change recorded. "
                                      "Remove the existing change first.") from exc
            raise
        e.id = cur.lastrowid
        log.info("Added %s exception id=%s for meeting id=%s", e.kind, e.id, e.meeting_id)
        return e

    def delete_exception(self, exception_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM schedule_exceptions WHERE id = ?", (exception_id,))

    def exceptions_for_meeting(self, meeting_id: int) -> list[ScheduleException]:
        rows = self.db.conn.execute(
            "SELECT * FROM schedule_exceptions WHERE meeting_id = ? ORDER BY COALESCE(new_start, original_date)",
            (meeting_id,),
        ).fetchall()
        return [_row_to_exception(r) for r in rows]

    # ---- expansion ----------------------------------------------------------

    def occurrences(self, first_day: date, last_day: date) -> list[Occurrence]:
        """All sessions starting between ``first_day`` and ``last_day`` inclusive.
        Cancelled sessions are returned with ``cancelled=True`` so they can be shown."""
        conn = self.db.conn
        meetings = {
            r["id"]: Meeting(id=r["id"], name=r["name"], short_code=r["short_code"])
            for r in conn.execute("SELECT id, name, short_code FROM meetings")
        }
        schedules = [_row_to_schedule(r) for r in conn.execute("SELECT * FROM schedules WHERE enabled = 1")]
        schedules = [s for s in schedules if s.meeting_id in meetings]
        by_id = {s.id: s for s in schedules}
        exceptions = [_row_to_exception(r) for r in conn.execute("SELECT * FROM schedule_exceptions")]
        overrides = {(e.schedule_id, e.original_date): e for e in exceptions if e.schedule_id is not None}

        result: list[Occurrence] = []
        day = first_day
        while day <= last_day:
            for s in schedules:
                if s.day_of_week != day.weekday():
                    continue
                exc = overrides.get((s.id, day))
                if exc and exc.kind == ExceptionKind.RESCHEDULED:
                    continue  # emitted below at its new time
                start = datetime.combine(day, s.start_time)
                result.append(Occurrence(
                    meeting_id=s.meeting_id, meeting_title=meetings[s.meeting_id].title, start=start,
                    end=start + timedelta(minutes=s.duration_minutes), preparation_minutes=s.preparation_minutes,
                    origin="weekly", schedule_id=s.id, cancelled=bool(exc), note=exc.note if exc else "",
                ))
            day += timedelta(days=1)

        for e in exceptions:
            if e.kind == ExceptionKind.CANCELLED or e.meeting_id not in meetings or e.new_start is None:
                continue
            if not first_day <= e.new_start.date() <= last_day:
                continue
            base = by_id.get(e.schedule_id) if e.schedule_id else None
            if e.kind == ExceptionKind.RESCHEDULED and base is None:
                continue  # its weekly entry is disabled
            duration = e.new_duration_minutes or (base.duration_minutes if base else 60)
            result.append(Occurrence(
                meeting_id=e.meeting_id, meeting_title=meetings[e.meeting_id].title, start=e.new_start,
                end=e.new_start + timedelta(minutes=duration),
                preparation_minutes=base.preparation_minutes if base else 5,
                origin=e.kind.value, schedule_id=e.schedule_id, note=e.note,
            ))

        result.sort(key=lambda o: (o.start, o.meeting_title))
        return result


def find_overlaps(occurrences: list[Occurrence]) -> list[tuple[Occurrence, Occurrence]]:
    """Pairs of active sessions that overlap. The user is told; nothing is resolved silently."""
    active = [o for o in occurrences if not o.cancelled]
    return [(a, b) for a, b in combinations(active, 2) if a.overlaps(b)]

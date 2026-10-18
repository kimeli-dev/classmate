from __future__ import annotations

import logging
import sqlite3

from sessionly.db import Database, utc_now
from sessionly.models import Meeting
from sessionly.services import ValidationError

log = logging.getLogger(__name__)


def _row_to_meeting(row: sqlite3.Row) -> Meeting:
    return Meeting(
        id=row["id"],
        name=row["name"],
        short_code=row["short_code"],
        host_name=row["host_name"],
        preferred_display_name=row["preferred_display_name"],
        automation_enabled=bool(row["automation_enabled"]),
        notifications_enabled=bool(row["notifications_enabled"]),
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class MeetingService:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _clean(meeting: Meeting) -> Meeting:
        meeting.name = meeting.name.strip()
        meeting.short_code = " ".join(meeting.short_code.split()).upper()
        meeting.host_name = meeting.host_name.strip()
        name = (meeting.preferred_display_name or "").strip()
        meeting.preferred_display_name = name or None
        if not meeting.name:
            raise ValidationError("Please enter a meeting name.")
        if len(meeting.name) > 200 or len(meeting.short_code) > 30:
            raise ValidationError("The meeting name or code is too long.")
        return meeting

    def _check_code_unique(self, code: str, exclude_id: int | None) -> None:
        if not code:
            return
        row = self.db.conn.execute(
            "SELECT id, name FROM meetings WHERE short_code = ? COLLATE NOCASE AND id IS NOT ?",
            (code, exclude_id),
        ).fetchone()
        if row:
            raise ValidationError(f"Meeting code {code} is already used by \"{row['name']}\".")

    def create(self, meeting: Meeting) -> Meeting:
        meeting = self._clean(meeting)
        now = utc_now()
        with self.db.transaction() as conn:
            self._check_code_unique(meeting.short_code, None)
            cur = conn.execute(
                """INSERT INTO meetings (name, short_code, host_name, preferred_display_name,
                       automation_enabled, notifications_enabled, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (meeting.name, meeting.short_code, meeting.host_name, meeting.preferred_display_name,
                 int(meeting.automation_enabled), int(meeting.notifications_enabled), meeting.notes, now, now),
            )
        log.info("Created meeting id=%s", cur.lastrowid)
        return self.get(cur.lastrowid)

    def update(self, meeting: Meeting) -> Meeting:
        if meeting.id is None:
            raise ValueError("Cannot update a meeting without an id")
        meeting = self._clean(meeting)
        with self.db.transaction() as conn:
            self._check_code_unique(meeting.short_code, meeting.id)
            cur = conn.execute(
                """UPDATE meetings SET name = ?, short_code = ?, host_name = ?, preferred_display_name = ?,
                       automation_enabled = ?, notifications_enabled = ?, notes = ?, updated_at = ?
                   WHERE id = ?""",
                (meeting.name, meeting.short_code, meeting.host_name, meeting.preferred_display_name,
                 int(meeting.automation_enabled), int(meeting.notifications_enabled), meeting.notes,
                 utc_now(), meeting.id),
            )
            if cur.rowcount == 0:
                raise ValidationError("That meeting no longer exists.")
        log.info("Updated meeting id=%s", meeting.id)
        return self.get(meeting.id)

    def delete(self, meeting_id: int) -> None:
        """Deletes the meeting with its schedules, exceptions and links (ON DELETE CASCADE)."""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        log.info("Deleted meeting id=%s", meeting_id)

    def get(self, meeting_id: int) -> Meeting:
        row = self.db.conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise ValidationError("That meeting no longer exists.")
        return _row_to_meeting(row)

    def list(self) -> list[Meeting]:
        rows = self.db.conn.execute("SELECT * FROM meetings ORDER BY name COLLATE NOCASE").fetchall()
        return [_row_to_meeting(r) for r in rows]

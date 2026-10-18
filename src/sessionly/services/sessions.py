"""Concrete sessions and their join status."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from sessionly.db import Database, utc_now
from sessionly.models import Occurrence, Session, SessionStatus

log = logging.getLogger(__name__)


def _key(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        meeting_id=row["meeting_id"],
        scheduled_start=datetime.fromisoformat(row["scheduled_start"]),
        scheduled_end=datetime.fromisoformat(row["scheduled_end"]),
        status=SessionStatus(row["join_status"]),
        reminded_at=row["reminded_at"],
        link_opened_at=row["link_opened_at"],
        confirmed_at=row["confirmed_at"],
        failure_reason=row["failure_reason"],
    )


class SessionService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def find(self, meeting_id: int, start: datetime) -> Session | None:
        row = self.db.conn.execute(
            "SELECT * FROM sessions WHERE meeting_id = ? AND scheduled_start = ?", (meeting_id, _key(start))
        ).fetchone()
        return _row_to_session(row) if row else None

    def ensure(self, occ: Occurrence) -> Session:
        """Get or create the session row for an occurrence (safe to call repeatedly)."""
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO sessions (meeting_id, scheduled_start, scheduled_end, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (occ.meeting_id, _key(occ.start), _key(occ.end), now, now),
            )
        return self.find(occ.meeting_id, occ.start)

    def transition(self, session_id: int, new: SessionStatus, *, expect: SessionStatus | None = None,
                   reason: str | None = None) -> bool:
        """Change status. With ``expect``, only succeeds if the current status matches -
        this is the compare-and-set that prevents handling one session twice."""
        now = utc_now()
        stamp = {SessionStatus.REMINDED: "reminded_at", SessionStatus.LINK_OPENED: "link_opened_at",
                 SessionStatus.JOINED: "confirmed_at", SessionStatus.NOT_JOINED: "confirmed_at"}.get(new)
        sets = "join_status = ?, updated_at = ?, failure_reason = ?" + (f", {stamp} = ?" if stamp else "")
        params: list = [new.value, now, reason] + ([now] if stamp else [])
        sql = f"UPDATE sessions SET {sets} WHERE id = ?"
        params.append(session_id)
        if expect is not None:
            sql += " AND join_status = ?"
            params.append(expect.value)
        with self.db.transaction() as conn:
            changed = conn.execute(sql, params).rowcount == 1
        if changed:
            log.info("Session id=%s -> %s", session_id, new)
        return changed

    def confirm_joined(self, occ: Occurrence) -> Session:
        session = self.ensure(occ)
        self.transition(session.id, SessionStatus.JOINED)
        return self.find(occ.meeting_id, occ.start)

    def mark_not_joined(self, occ: Occurrence, reason: str | None = None) -> Session:
        session = self.ensure(occ)
        self.transition(session.id, SessionStatus.NOT_JOINED, reason=reason)
        return self.find(occ.meeting_id, occ.start)

    def between(self, first: datetime, last: datetime) -> dict[tuple[int, datetime], Session]:
        rows = self.db.conn.execute(
            "SELECT * FROM sessions WHERE scheduled_start >= ? AND scheduled_start <= ?", (_key(first), _key(last))
        ).fetchall()
        sessions = [_row_to_session(r) for r in rows]
        return {(s.meeting_id, s.scheduled_start): s for s in sessions}

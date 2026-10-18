"""Per-meeting meeting links: current link, history, replacement and problem reports."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from sessionly.db import Database, utc_now
from sessionly.models import FailureReason, LinkStatus, MeetingLink, Platform
from sessionly.services import ValidationError
from sessionly.services.link_validation import LinkCheck, check_meeting_url

log = logging.getLogger(__name__)


def _row_to_link(row: sqlite3.Row) -> MeetingLink:
    return MeetingLink(
        id=row["id"],
        meeting_id=row["meeting_id"],
        url=row["url"],
        platform=Platform(row["platform"]),
        source=row["source"],
        status=LinkStatus(row["status"]),
        notes=row["notes"],
        is_current=bool(row["is_current"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_success_at=row["last_success_at"],
        last_failure_at=row["last_failure_at"],
        failure_reason=FailureReason(row["failure_reason"]) if row["failure_reason"] else None,
        passcode=row["passcode"],
    )


def clean_passcode(raw: str) -> str:
    passcode = (raw or "").strip()
    if any(c.isspace() for c in passcode):
        raise ValidationError("The passcode contains spaces. Paste only the passcode itself.")
    if len(passcode) > 32:
        raise ValidationError("That passcode is too long. Zoom passcodes are at most 10 characters.")
    return passcode


@dataclass
class ProblemOutcome:
    needs_replacement: bool
    advice: str


_ADVICE = {
    FailureReason.NO_INTERNET: "The link was kept. Check your Wi-Fi or data connection and try again.",
    FailureReason.HOST_NOT_STARTED: "The link was kept - a meeting that has not started is not a broken link. "
                                    "Try again in a few minutes or check for an announcement.",
    FailureReason.WAITING_ROOM: "The link was kept. The host has to admit you; Sessionly will never bypass a waiting room.",
    FailureReason.AUTHENTICATION: "The link was kept. Sign in with your work or school account, or enter the passcode "
                                  "your host shared, then try again.",
    FailureReason.INVALID_LINK: "The link was marked as needing replacement. Paste the latest link from your host.",
    FailureReason.UNKNOWN: "The link was marked as needing replacement. If you get a new link, paste it in; "
                           "if the old one starts working, mark it as worked.",
}


class LinkService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def current(self, meeting_id: int) -> MeetingLink | None:
        row = self.db.conn.execute(
            "SELECT * FROM meeting_links WHERE meeting_id = ? AND is_current = 1", (meeting_id,)
        ).fetchone()
        return _row_to_link(row) if row else None

    def history(self, meeting_id: int) -> list[MeetingLink]:
        rows = self.db.conn.execute(
            "SELECT * FROM meeting_links WHERE meeting_id = ? ORDER BY is_current DESC, updated_at DESC, id DESC",
            (meeting_id,),
        ).fetchall()
        return [_row_to_link(r) for r in rows]

    def other_meetings_using(self, url: str, meeting_id: int) -> list[tuple[int, str]]:
        """Meetings whose *current* link is this URL - a sign the association may be wrong."""
        check = check_meeting_url(url)
        target = check.url if check.ok else url.strip()
        rows = self.db.conn.execute(
            """SELECT c.id, c.name FROM meeting_links l JOIN meetings c ON c.id = l.meeting_id
               WHERE l.url = ? AND l.is_current = 1 AND l.meeting_id <> ?""",
            (target, meeting_id),
        ).fetchall()
        return [(r["id"], r["name"]) for r in rows]

    def set_current(self, meeting_id: int, raw_url: str, source: str = "manual", notes: str = "",
                    passcode: str | None = None) -> tuple[MeetingLink, LinkCheck]:
        """Validate and save a link as the meeting's preferred link, keeping the old one in history.

        ``passcode`` is the Zoom passcode the host shared; ``None`` keeps a re-entered link's saved one."""
        check = check_meeting_url(raw_url)
        if not check.ok:
            raise ValidationError(check.error)
        if passcode is not None:
            passcode = clean_passcode(passcode)
        now = utc_now()
        with self.db.transaction() as conn:
            if conn.execute("SELECT 1 FROM meetings WHERE id = ?", (meeting_id,)).fetchone() is None:
                raise ValidationError("That meeting no longer exists.")
            existing = conn.execute(
                "SELECT id FROM meeting_links WHERE meeting_id = ? AND url = ?", (meeting_id, check.url)
            ).fetchone()
            conn.execute(
                "UPDATE meeting_links SET is_current = 0, updated_at = ? WHERE meeting_id = ? AND is_current = 1",
                (now, meeting_id),
            )
            if existing:
                # Re-entering a known link revives it; its history (successes) is preserved.
                conn.execute(
                    """UPDATE meeting_links SET is_current = 1, source = ?, notes = ?, updated_at = ?,
                           passcode = COALESCE(?, passcode),
                           status = CASE WHEN status = 'failed' THEN 'unverified' ELSE status END
                       WHERE id = ?""",
                    (source, notes, now, passcode, existing["id"]),
                )
                link_id = existing["id"]
            else:
                cur = conn.execute(
                    """INSERT INTO meeting_links (meeting_id, url, platform, source, status, notes, is_current,
                           created_at, updated_at, passcode)
                       VALUES (?, ?, ?, ?, 'unverified', ?, 1, ?, ?, ?)""",
                    (meeting_id, check.url, check.platform.value, source, notes, now, now, passcode or ""),
                )
                link_id = cur.lastrowid
        log.info("Meeting id=%s now uses link id=%s (%s, source=%s)", meeting_id, link_id, check.platform, source)
        return self._get(link_id), check

    def make_current(self, link_id: int) -> MeetingLink:
        """Restore a link from history."""
        link = self._get(link_id)
        return self.set_current(link.meeting_id, link.url, source=link.source, notes=link.notes)[0]

    def set_passcode(self, link_id: int, passcode: str) -> MeetingLink:
        with self.db.transaction() as conn:
            conn.execute("UPDATE meeting_links SET passcode = ?, updated_at = ? WHERE id = ?",
                         (clean_passcode(passcode), utc_now(), link_id))
        log.info("Passcode updated for link id=%s", link_id)  # never the passcode itself
        return self._get(link_id)

    def mark_worked(self, link_id: int) -> MeetingLink:
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE meeting_links SET status = 'worked', last_success_at = ?, failure_reason = NULL,
                       updated_at = ? WHERE id = ?""",
                (now, now, link_id),
            )
        log.info("Link id=%s confirmed working by user", link_id)
        return self._get(link_id)

    def report_problem(self, link_id: int, reason: FailureReason) -> ProblemOutcome:
        """Record a failed attempt. Only reasons that implicate the link itself mark it as failed,
        so a host who has not started yet never triggers a replacement request."""
        now = utc_now()
        with self.db.transaction() as conn:
            if reason.link_is_suspect:
                conn.execute(
                    """UPDATE meeting_links SET status = 'failed', last_failure_at = ?, failure_reason = ?,
                           updated_at = ? WHERE id = ?""",
                    (now, reason.value, now, link_id),
                )
            else:
                conn.execute(
                    "UPDATE meeting_links SET last_failure_at = ?, failure_reason = ?, updated_at = ? WHERE id = ?",
                    (now, reason.value, now, link_id),
                )
        log.info("Problem reported for link id=%s: %s", link_id, reason)
        return ProblemOutcome(needs_replacement=reason.link_is_suspect, advice=_ADVICE[reason])

    def delete_from_history(self, link_id: int) -> None:
        link = self._get(link_id)
        if link.is_current:
            raise ValidationError("The current link cannot be deleted. Replace it first.")
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM meeting_links WHERE id = ?", (link_id,))

    def _get(self, link_id: int) -> MeetingLink:
        row = self.db.conn.execute("SELECT * FROM meeting_links WHERE id = ?", (link_id,)).fetchone()
        if row is None:
            raise ValidationError("That link no longer exists.")
        return _row_to_link(row)

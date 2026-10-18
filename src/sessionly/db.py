"""SQLite access with versioned migrations.

The schema version is kept in ``PRAGMA user_version``. Each migration runs in its own
transaction, and an existing database is copied to ``sessionly.db.bak-v<N>`` before it
is upgraded, so a failed upgrade can always be undone by hand.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    """Raised with a user-readable message when the database cannot be used."""


def utc_now() -> str:
    """Timestamps are stored as UTC ISO-8601 and converted to local time for display."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE courses (
            id                     INTEGER PRIMARY KEY,
            name                   TEXT NOT NULL CHECK (length(trim(name)) > 0),
            course_code            TEXT NOT NULL DEFAULT '',
            lecturer_name          TEXT NOT NULL DEFAULT '',
            preferred_display_name TEXT,
            automation_enabled     INTEGER NOT NULL DEFAULT 1 CHECK (automation_enabled IN (0, 1)),
            notifications_enabled  INTEGER NOT NULL DEFAULT 1 CHECK (notifications_enabled IN (0, 1)),
            notes                  TEXT NOT NULL DEFAULT '',
            created_at             TEXT NOT NULL,
            updated_at             TEXT NOT NULL
        );
        CREATE UNIQUE INDEX ux_courses_code ON courses (course_code COLLATE NOCASE) WHERE course_code <> '';

        CREATE TABLE schedules (
            id                  INTEGER PRIMARY KEY,
            course_id           INTEGER NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
            day_of_week         INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
            start_time          TEXT NOT NULL CHECK (start_time GLOB '[0-2][0-9]:[0-5][0-9]'),
            duration_minutes    INTEGER NOT NULL CHECK (duration_minutes BETWEEN 1 AND 720),
            preparation_minutes INTEGER NOT NULL DEFAULT 5 CHECK (preparation_minutes BETWEEN 0 AND 120),
            timezone            TEXT NOT NULL DEFAULT 'local',
            enabled             INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL
        );
        CREATE INDEX ix_schedules_course ON schedules (course_id);

        CREATE TABLE schedule_exceptions (
            id                   INTEGER PRIMARY KEY,
            course_id            INTEGER NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
            schedule_id          INTEGER REFERENCES schedules (id) ON DELETE CASCADE,
            kind                 TEXT NOT NULL CHECK (kind IN ('cancelled', 'rescheduled', 'extra')),
            original_date        TEXT,
            new_start            TEXT,
            new_duration_minutes INTEGER CHECK (new_duration_minutes IS NULL OR new_duration_minutes BETWEEN 1 AND 720),
            note                 TEXT NOT NULL DEFAULT '',
            created_at           TEXT NOT NULL,
            CHECK (
                (kind = 'cancelled'   AND schedule_id IS NOT NULL AND original_date IS NOT NULL AND new_start IS NULL)
             OR (kind = 'rescheduled' AND schedule_id IS NOT NULL AND original_date IS NOT NULL AND new_start IS NOT NULL)
             OR (kind = 'extra'       AND schedule_id IS NULL     AND original_date IS NULL     AND new_start IS NOT NULL)
            )
        );
        CREATE UNIQUE INDEX ux_exceptions_occurrence ON schedule_exceptions (schedule_id, original_date)
            WHERE schedule_id IS NOT NULL;
        CREATE INDEX ix_exceptions_course ON schedule_exceptions (course_id);

        CREATE TABLE meeting_links (
            id              INTEGER PRIMARY KEY,
            course_id       INTEGER NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
            url             TEXT NOT NULL,
            platform        TEXT NOT NULL CHECK (platform IN ('zoom', 'google_meet', 'teams', 'other')),
            source          TEXT NOT NULL DEFAULT 'manual',
            status          TEXT NOT NULL DEFAULT 'unverified' CHECK (status IN ('unverified', 'worked', 'failed')),
            notes           TEXT NOT NULL DEFAULT '',
            is_current      INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0, 1)),
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            last_success_at TEXT,
            last_failure_at TEXT,
            failure_reason  TEXT,
            UNIQUE (course_id, url)
        );
        CREATE UNIQUE INDEX ux_links_one_current ON meeting_links (course_id) WHERE is_current = 1;
        CREATE INDEX ix_links_url ON meeting_links (url);

        CREATE TABLE settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        # One row per concrete class meeting. The UNIQUE key is what makes background
        # handling idempotent: a class is reminded / opened at most once, even across restarts.
        """
        CREATE TABLE class_sessions (
            id              INTEGER PRIMARY KEY,
            course_id       INTEGER NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
            scheduled_start TEXT NOT NULL,
            scheduled_end   TEXT NOT NULL,
            join_status     TEXT NOT NULL DEFAULT 'scheduled' CHECK (join_status IN
                                ('scheduled', 'reminded', 'link_opened', 'joined', 'not_joined', 'missed')),
            reminded_at     TEXT,
            link_opened_at  TEXT,
            confirmed_at    TEXT,
            failure_reason  TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            UNIQUE (course_id, scheduled_start)
        );
        CREATE INDEX ix_sessions_start ON class_sessions (scheduled_start);
        """,
    ),
    (
        3,
        # Listening, voice responses and lecture notes. Both permission switches default OFF.
        """
        ALTER TABLE courses ADD COLUMN allow_auto_response INTEGER NOT NULL DEFAULT 0
            CHECK (allow_auto_response IN (0, 1));
        ALTER TABLE courses ADD COLUMN allow_transcription INTEGER NOT NULL DEFAULT 0
            CHECK (allow_transcription IN (0, 1));

        CREATE TABLE name_detection_events (
            id              INTEGER PRIMARY KEY,
            session_id      INTEGER REFERENCES class_sessions (id) ON DELETE CASCADE,
            detected_text   TEXT NOT NULL,          -- a short snippet only, never the whole transcript
            confidence      REAL NOT NULL,
            detected_at     TEXT NOT NULL,
            response_status TEXT NOT NULL DEFAULT 'pending' CHECK (response_status IN
                ('pending', 'responded', 'tapped', 'notified', 'skipped', 'cancelled', 'test_mode', 'failed')),
            reason          TEXT NOT NULL DEFAULT '',
            handled_at      TEXT
        );
        CREATE INDEX ix_detections_session ON name_detection_events (session_id);

        -- Temporary: kept only until the lecture is summarised (unless the student opts to keep it).
        CREATE TABLE transcript_segments (
            id         INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL REFERENCES class_sessions (id) ON DELETE CASCADE,
            spoken_at  TEXT NOT NULL,
            text       TEXT NOT NULL
        );
        CREATE INDEX ix_transcript_session ON transcript_segments (session_id);

        CREATE TABLE lecture_summaries (
            id            INTEGER PRIMARY KEY,
            session_id    INTEGER REFERENCES class_sessions (id) ON DELETE SET NULL,
            course_id     INTEGER REFERENCES courses (id) ON DELETE CASCADE,
            title         TEXT NOT NULL,
            lecture_date  TEXT NOT NULL,
            summary_text  TEXT NOT NULL,
            source_type   TEXT NOT NULL CHECK (source_type IN ('live_transcript', 'pasted_transcript', 'notes')),
            provider      TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'new' CHECK (review_status IN ('new', 'reviewed', 'revise')),
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );
        CREATE INDEX ix_summaries_course ON lecture_summaries (course_id, lecture_date);
        """,
    ),
    (
        4,
        # Zoom passcode the lecturer shared, kept with the link (same trust level as a pwd= link).
        """
        ALTER TABLE meeting_links ADD COLUMN passcode TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        5,
        # Study companion: saved explanations / notes, and sampled slide snapshots (opt-in per course).
        """
        ALTER TABLE courses ADD COLUMN allow_slide_capture INTEGER NOT NULL DEFAULT 0
            CHECK (allow_slide_capture IN (0, 1));

        CREATE TABLE slide_captures (
            id          INTEGER PRIMARY KEY,
            course_id   INTEGER NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
            session_id  INTEGER REFERENCES class_sessions (id) ON DELETE SET NULL,
            captured_at TEXT NOT NULL,
            file_name   TEXT NOT NULL UNIQUE,   -- relative to <data>/slides
            width       INTEGER NOT NULL,
            height      INTEGER NOT NULL
        );
        CREATE INDEX ix_slides_course ON slide_captures (course_id, captured_at);

        CREATE TABLE study_notes (
            id          INTEGER PRIMARY KEY,
            course_id   INTEGER NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
            session_id  INTEGER REFERENCES class_sessions (id) ON DELETE SET NULL,
            slide_id    INTEGER REFERENCES slide_captures (id) ON DELETE SET NULL,
            lecture_date TEXT NOT NULL,
            question    TEXT NOT NULL,
            answer      TEXT NOT NULL,
            source      TEXT NOT NULL CHECK (source IN ('ai', 'student')),
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        CREATE INDEX ix_notes_course ON study_notes (course_id, lecture_date);
        """,
    ),
    (
        6,
        # Sessionly: general vocabulary (course -> meeting, class session -> session, lecturer -> host),
        # and removal of the unused voice-response / transcript tables. Data is kept; SQLite rewrites
        # foreign keys and index definitions that refer to renamed tables and columns.
        """
        DROP TABLE IF EXISTS name_detection_events;
        DROP TABLE IF EXISTS transcript_segments;
        DROP TABLE IF EXISTS lecture_summaries;
        ALTER TABLE courses DROP COLUMN allow_auto_response;
        ALTER TABLE courses DROP COLUMN allow_transcription;

        ALTER TABLE courses RENAME TO meetings;
        ALTER TABLE meetings RENAME COLUMN course_code TO short_code;
        ALTER TABLE meetings RENAME COLUMN lecturer_name TO host_name;
        DROP INDEX ux_courses_code;
        CREATE UNIQUE INDEX ux_meetings_code ON meetings (short_code COLLATE NOCASE) WHERE short_code <> '';

        ALTER TABLE class_sessions RENAME TO sessions;
        ALTER TABLE study_notes RENAME TO notes;
        ALTER TABLE notes RENAME COLUMN lecture_date TO session_date;
        ALTER TABLE schedules RENAME COLUMN course_id TO meeting_id;
        ALTER TABLE schedule_exceptions RENAME COLUMN course_id TO meeting_id;
        ALTER TABLE meeting_links RENAME COLUMN course_id TO meeting_id;
        ALTER TABLE sessions RENAME COLUMN course_id TO meeting_id;
        ALTER TABLE slide_captures RENAME COLUMN course_id TO meeting_id;
        ALTER TABLE notes RENAME COLUMN course_id TO meeting_id;
        """,
    ),
    (
        7,
        # The Learn page (companion notes and sample slide snapshots) was removed.
        """
        DROP TABLE IF EXISTS notes;
        DROP TABLE IF EXISTS slide_captures;
        ALTER TABLE meetings DROP COLUMN allow_slide_capture;
        """,
    ),
    (
        8,
        # One-tap voice replies the user recorded in their own voice. The audio lives in
        # <data>/voice/<file_name>; only the user ever triggers playback.
        """
        CREATE TABLE voice_replies (
            id          INTEGER PRIMARY KEY,
            label       TEXT NOT NULL,
            file_name   TEXT NOT NULL UNIQUE,
            position    INTEGER NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        """,
    ),
]

LATEST_VERSION = MIGRATIONS[-1][0]


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path) if str(path) != ":memory:" else None
        try:
            # Autocommit mode; transactions are explicit via ``transaction()``.
            self.conn = sqlite3.connect(str(path), isolation_level=None)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA busy_timeout = 5000")
            if self.path is not None:
                self.conn.execute("PRAGMA journal_mode = WAL")
            self._check_integrity()
        except sqlite3.DatabaseError as exc:
            raise DatabaseError(
                f"The Sessionly database at {path} could not be opened ({exc}). "
                "It may be damaged. Close Sessionly, rename the file, and restore a "
                "sessionly.db.bak-* copy from the same folder if one exists."
            ) from exc
        self._tx_depth = 0

    def _check_integrity(self) -> None:
        result = self.conn.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise sqlite3.DatabaseError(f"integrity check failed: {result}")

    @property
    def schema_version(self) -> int:
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def migrate(self) -> None:
        current = self.schema_version
        if current > LATEST_VERSION:
            raise DatabaseError(
                f"This database was created by a newer version of Sessionly (schema {current}). "
                "Please update the application."
            )
        pending = [(v, sql) for v, sql in MIGRATIONS if v > current]
        if not pending:
            return
        if current > 0 and self.path is not None:
            self.conn.execute("PRAGMA wal_checkpoint(FULL)")
            backup = self.path.with_name(f"{self.path.name}.bak-v{current}")
            shutil.copy2(self.path, backup)
            log.info("Backed up database schema v%s before migrating", current)
        for version, sql in pending:
            try:
                self.conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
            except sqlite3.Error as exc:
                if self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                raise DatabaseError(f"Upgrading the database to schema {version} failed: {exc}") from exc
            log.info("Database migrated to schema v%s", version)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Atomic unit of work. Nested calls join the outer transaction."""
        if self._tx_depth == 0:
            self.conn.execute("BEGIN IMMEDIATE")
        self._tx_depth += 1
        try:
            yield self.conn
        except BaseException:
            self._tx_depth -= 1
            if self._tx_depth == 0:
                self.conn.execute("ROLLBACK")
            raise
        else:
            self._tx_depth -= 1
            if self._tx_depth == 0:
                self.conn.execute("COMMIT")

    def close(self) -> None:
        self.conn.close()


def open_database(path: Path | str) -> Database:
    db = Database(path)
    db.migrate()
    return db

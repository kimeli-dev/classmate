"""The user's recorded one-tap voice replies ("Present", "Yes, I'm here", "Sorry, my mic was off").

Replies are recorded once and reused so they always sound the same. Sessionly plays one only
when the user presses it (button, tray menu or hotkey) - never automatically, and nothing in
the app listens to the meeting.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from sessionly.audio.clip import Clip, ClipError, prepare_clip, read_wav, write_wav
from sessionly.db import Database, utc_now
from sessionly.services import ValidationError

log = logging.getLogger(__name__)

MAX_REPLIES = 9          # one per hotkey, Ctrl+Alt+1 ... Ctrl+Alt+9
MAX_LABEL = 40
SUGGESTED = ["Present", "Yes, I'm here", "Sorry, my mic was off", "Could you repeat that, please?"]


@dataclass
class VoiceReply:
    id: int
    label: str
    file_name: str
    position: int       # 1-based; also its hotkey number
    duration_ms: int
    created_at: str
    updated_at: str

    @property
    def hotkey(self) -> str:
        return f"Ctrl+Alt+{self.position}"


def _row(row: sqlite3.Row) -> VoiceReply:
    return VoiceReply(row["id"], row["label"], row["file_name"], row["position"], row["duration_ms"],
                      row["created_at"], row["updated_at"])


def _clean_label(label: str) -> str:
    text = " ".join((label or "").split())
    if not text:
        raise ValidationError("Give the reply a short name, e.g. \"Present\".")
    if len(text) > MAX_LABEL:
        raise ValidationError(f"Keep the name under {MAX_LABEL} characters.")
    return text


class VoiceReplyService:
    def __init__(self, db: Database, voice_dir: Path) -> None:
        self.db = db
        self.voice_dir = voice_dir

    def list(self) -> list[VoiceReply]:
        rows = self.db.conn.execute("SELECT * FROM voice_replies ORDER BY position").fetchall()
        return [_row(r) for r in rows]

    def get(self, reply_id: int) -> VoiceReply:
        row = self.db.conn.execute("SELECT * FROM voice_replies WHERE id = ?", (reply_id,)).fetchone()
        if row is None:
            raise ValidationError("That reply no longer exists.")
        return _row(row)

    def path(self, reply: VoiceReply) -> Path:
        return self.voice_dir / reply.file_name

    def clip(self, reply: VoiceReply) -> Clip:
        try:
            return read_wav(self.path(reply))
        except FileNotFoundError:
            raise ValidationError(f"The recording for \"{reply.label}\" is missing. Record it again.") from None
        except (ClipError, EOFError, OSError) as exc:
            raise ValidationError(f"The recording for \"{reply.label}\" can't be read. Record it again.") from exc

    @staticmethod
    def process(pcm: bytes, sample_rate: int) -> Clip:
        """Trim and level a raw recording; ValidationError explains an unusable one."""
        try:
            return prepare_clip(pcm, sample_rate)
        except ClipError as exc:
            raise ValidationError(str(exc)) from None

    def add(self, label: str, clip: Clip) -> VoiceReply:
        label = _clean_label(label)
        existing = self.list()
        if len(existing) >= MAX_REPLIES:
            raise ValidationError(f"You can keep up to {MAX_REPLIES} replies. Delete one first.")
        if any(r.label.lower() == label.lower() for r in existing):
            raise ValidationError(f"You already have a reply called \"{label}\".")
        file_name = f"{uuid.uuid4().hex}.wav"
        write_wav(self.voice_dir / file_name, clip)
        now = utc_now()
        try:
            with self.db.transaction() as conn:
                cur = conn.execute(
                    """INSERT INTO voice_replies (label, file_name, position, duration_ms, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (label, file_name, len(existing) + 1, round(clip.seconds * 1000), now, now))
        except Exception:
            (self.voice_dir / file_name).unlink(missing_ok=True)
            raise
        log.info("Voice reply id=%s recorded (%.1f s)", cur.lastrowid, clip.seconds)  # never the audio
        return self.get(cur.lastrowid)

    def rerecord(self, reply_id: int, clip: Clip) -> VoiceReply:
        reply = self.get(reply_id)
        write_wav(self.path(reply), clip)
        with self.db.transaction() as conn:
            conn.execute("UPDATE voice_replies SET duration_ms = ?, updated_at = ? WHERE id = ?",
                         (round(clip.seconds * 1000), utc_now(), reply_id))
        return self.get(reply_id)

    def rename(self, reply_id: int, label: str) -> VoiceReply:
        label = _clean_label(label)
        if any(r.label.lower() == label.lower() and r.id != reply_id for r in self.list()):
            raise ValidationError(f"You already have a reply called \"{label}\".")
        with self.db.transaction() as conn:
            conn.execute("UPDATE voice_replies SET label = ?, updated_at = ? WHERE id = ?",
                         (label, utc_now(), reply_id))
        return self.get(reply_id)

    def move(self, reply_id: int, delta: int) -> None:
        """Move up (-1) or down (+1); positions stay 1..n so hotkeys stay contiguous."""
        replies = self.list()
        i = next(i for i, r in enumerate(replies) if r.id == reply_id)
        j = i + delta
        if not 0 <= j < len(replies):
            return
        replies[i], replies[j] = replies[j], replies[i]
        self._renumber(replies)

    def delete(self, reply_id: int) -> None:
        reply = self.get(reply_id)
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM voice_replies WHERE id = ?", (reply_id,))
        self.path(reply).unlink(missing_ok=True)
        self._renumber(self.list())

    def _renumber(self, ordered: list[VoiceReply]) -> None:
        with self.db.transaction() as conn:
            for pos, r in enumerate(ordered, start=1):
                conn.execute("UPDATE voice_replies SET position = ? WHERE id = ?", (pos, r.id))

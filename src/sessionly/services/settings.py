"""Key/value application settings. Never store secrets here - see docs/SECURITY_PRIVACY.md."""

from __future__ import annotations

import json
from typing import Any

from sessionly.db import Database, utc_now

DISPLAY_NAME = "display_name"
SETUP_COMPLETED = "setup_completed"
AUTOMATION_PAUSED = "automation_paused"      # master switch: no reminders, nothing opened
AUTO_OPEN_LINKS = "auto_open_links"          # open the link at preparation time (default off)
TRAY_HINT_SHOWN = "tray_hint_shown"

# Joining quietly
ZOOM_QUIET_JOIN_DONE = "zoom_quiet_join_done"  # user finished the "join with mic off" Zoom setup

# Joining meetings
GOOGLE_MEET_ACCOUNT = "google_meet_account"  # e-mail of the Google account to open Meet with
GOOGLE_MEET_ALLOWED = "google_meet_allowed"  # user allowed Sessionly to use that account (default off)

# One-tap voice replies (played only when the user presses one)
VOICE_MIC = "voice_mic_device"               # microphone name used to record replies ("" = Windows default)
VOICE_OUTPUT = "voice_output_device"         # virtual cable input the meeting app listens to ("" = none)
VOICE_MONITOR = "voice_monitor"              # also play replies on your speakers/headphones (default on)
VOICE_HOTKEYS = "voice_hotkeys"              # Ctrl+Alt+1..9 work while Zoom/Meet has focus (default on)
VOICE_REPLY_KEY = "voice_reply_key"          # the one key that plays your main reply ("" = off; default F9)
VOICE_REPLY_KEY_REPLY = "voice_reply_key_reply"  # id of the reply that key plays (default: reply 1)


class SettingsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key: str, value: Any) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (key, json.dumps(value), utc_now()),
            )

    @property
    def display_name(self) -> str:
        return self.get(DISPLAY_NAME, "")

    @display_name.setter
    def display_name(self, value: str) -> None:
        self.set(DISPLAY_NAME, value.strip())

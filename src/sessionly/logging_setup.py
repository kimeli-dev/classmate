"""Structured, privacy-preserving logging.

Meeting URLs often embed passcodes (e.g. Zoom ``pwd=``), so every URL is reduced to
its host and every e-mail address is masked before anything reaches a log file.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Meeting hosts are masked even when pasted without a scheme.
_MEETING_HOST_RE = re.compile(
    r"(?:https?://)?\b((?:[\w-]+\.)*(?:zoom\.us|zoomgov\.com|meet\.google\.com|teams\.microsoft\.com|teams\.live\.com))"
    r"(?:[/?#][^\s'\"<>]*)?",
    re.IGNORECASE,
)
_SCHEME_URL_RE = re.compile(r"https?://([^/\s'\"<>?#]+)[^\s'\"<>]*", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_SECRET_RE = re.compile(r"(?i)\b(pwd|passcode|password|token|api[_-]?key|secret)=([^\s&]+)")


def redact(text: str) -> str:
    """Remove information that should never be persisted in logs."""
    text = _EMAIL_RE.sub("<email>", text)
    text = _MEETING_HOST_RE.sub(lambda m: f"<url:{m.group(1).lower()}>", text)
    text = _SCHEME_URL_RE.sub(lambda m: f"<url:{m.group(1).lower()}>", text)
    text = _SECRET_RE.sub(lambda m: f"{m.group(1)}=<redacted>", text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(log_dir: Path, level: str = "INFO") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "sessionly.log"

    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(RedactingFormatter(LOG_FORMAT))
    console = logging.StreamHandler()
    console.setFormatter(RedactingFormatter(LOG_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console)
    return log_file

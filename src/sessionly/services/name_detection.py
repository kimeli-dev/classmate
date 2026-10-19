from __future__ import annotations

"""Conservative name matching for an opt-in, user-visible lecture alert.

Consumes transcript text from a speech-to-text component. It does not capture
meeting audio, connect to meetings, mark attendance, or trigger voice replies.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import time
import unicodedata
from typing import Iterable


@dataclass(frozen=True)
class NameMatch:
    matched: bool
    confidence: float
    matched_alias: str | None = None
    transcript: str = ""
    reason: str = "no_match"


def normalize_text(value: str) -> str:
    """Normalize Unicode, case, punctuation and whitespace for comparison."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("’", "'")
    value = re.sub(r"[^\w']+", " ", value, flags=re.UNICODE)
    return " ".join(value.split()).strip()


class NameDetector:
    """Match configured names in transcript text; results are suggestions only."""

    def __init__(self, full_name: str, aliases: Iterable[str] = (), *,
                 allow_first_name: bool = True, min_asr_confidence: float = 0.55,
                 fuzzy_threshold: float = 0.90, cooldown_seconds: float = 4.0) -> None:
        primary = normalize_text(full_name)
        if not primary:
            raise ValueError("full_name must contain at least one letter or number")
        if not 0.0 <= min_asr_confidence <= 1.0:
            raise ValueError("min_asr_confidence must be between 0 and 1")
        if not 0.80 <= fuzzy_threshold <= 1.0:
            raise ValueError("fuzzy_threshold must be between 0.80 and 1")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")
        candidates = [primary, *(normalize_text(a) for a in aliases)]
        if allow_first_name:
            candidates.append(primary.split()[0])
        self.aliases = tuple(sorted({a for a in candidates if a}, key=lambda x: (-len(x.split()), -len(x))))
        self.min_asr_confidence = min_asr_confidence
        self.fuzzy_threshold = fuzzy_threshold
        self.cooldown_seconds = cooldown_seconds
        self._last_event_key: str | None = None
        self._last_event_time = float("-inf")

    def detect(self, transcript: str, *, asr_confidence: float = 1.0) -> NameMatch:
        raw = (transcript or "").strip()
        text = normalize_text(raw)
        if not text:
            return NameMatch(False, 0.0, transcript=raw, reason="empty_transcript")
        if not 0.0 <= asr_confidence <= 1.0:
            raise ValueError("asr_confidence must be between 0 and 1")
        if asr_confidence < self.min_asr_confidence:
            return NameMatch(False, asr_confidence, transcript=raw, reason="low_asr_confidence")
        words = text.split()
        for alias in self.aliases:
            alias_words = alias.split()
            width = len(alias_words)
            for start in range(0, len(words) - width + 1):
                if words[start:start + width] == alias_words:
                    return NameMatch(True, min(1.0, asr_confidence), alias, raw, "exact")
        # Fuzzy matching is intentionally restricted to long, single-token names.
        for alias in self.aliases:
            if len(alias) < 5 or " " in alias:
                continue
            for word in words:
                if len(word) < 5:
                    continue
                similarity = SequenceMatcher(None, alias, word).ratio()
                if similarity >= self.fuzzy_threshold:
                    score = min(asr_confidence, 0.70 + 0.25 * similarity)
                    return NameMatch(True, score, alias, raw, "fuzzy_review")
        return NameMatch(False, asr_confidence, transcript=raw, reason="no_match")

    def should_alert(self, match: NameMatch, *, now: float | None = None) -> bool:
        """Gate a user-visible notification with a duplicate-alert cooldown."""
        if not match.matched:
            return False
        timestamp = time.monotonic() if now is None else now
        key = normalize_text(match.transcript)
        if key == self._last_event_key and timestamp - self._last_event_time < self.cooldown_seconds:
            return False
        self._last_event_key = key
        self._last_event_time = timestamp
        return True

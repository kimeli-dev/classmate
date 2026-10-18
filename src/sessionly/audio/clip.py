"""Processing for recorded voice replies: 16-bit mono PCM in, consistent clip out.

Pure Python (stdlib ``array`` + ``wave``) so it is testable without audio hardware.
Every saved reply goes through ``prepare_clip`` so all replies sound the same in a
meeting: leading/trailing silence trimmed (with a little padding so words aren't
clipped), short fades so there's no click, and peak-normalised to the same level.
"""

from __future__ import annotations

import math
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 48_000
MIN_SECONDS = 0.3
MAX_SECONDS = 15.0
TARGET_PEAK = 0.89          # about -1 dBFS: loud and clear, no clipping
SILENCE_THRESHOLD = 0.02    # below ~-34 dBFS counts as silence when trimming
TOO_QUIET_PEAK = 0.03       # a recording whose loudest moment is below this is treated as empty
PAD_SECONDS = 0.12          # kept around the speech when trimming
FADE_SECONDS = 0.01

_FULL_SCALE = 32767


class ClipError(ValueError):
    """The recording can't be used; the message is shown to the user as-is."""


@dataclass(frozen=True)
class Clip:
    pcm: bytes          # 16-bit little-endian mono
    sample_rate: int

    @property
    def samples(self) -> int:
        return len(self.pcm) // 2

    @property
    def seconds(self) -> float:
        return self.samples / self.sample_rate


def _samples(pcm: bytes) -> array:
    a = array("h")
    a.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    return a


def peak(pcm: bytes) -> float:
    a = _samples(pcm)
    return max((abs(s) for s in a), default=0) / _FULL_SCALE


def rms_dbfs(pcm: bytes) -> float:
    """Loudness of a chunk, for the recording level meter (-90 for silence)."""
    a = _samples(pcm)
    if not a:
        return -90.0
    mean_sq = sum(s * s for s in a) / len(a)
    return max(-90.0, 20 * math.log10(math.sqrt(mean_sq) / _FULL_SCALE)) if mean_sq else -90.0


def _trim_bounds(a: array, sample_rate: int) -> tuple[int, int]:
    # Work on 10 ms windows so one stray click doesn't count as speech.
    win = max(1, sample_rate // 100)
    limit = SILENCE_THRESHOLD * _FULL_SCALE
    loud = [i for i in range(0, len(a), win) if max(abs(s) for s in a[i:i + win]) >= limit]
    if not loud:
        return 0, 0
    pad = int(PAD_SECONDS * sample_rate)
    return max(0, loud[0] - pad), min(len(a), loud[-1] + win + pad)


def prepare_clip(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> Clip:
    """Trim, fade and normalise a raw recording. Raises ClipError if it's unusable."""
    a = _samples(pcm)
    if not a or peak(pcm) < TOO_QUIET_PEAK:
        raise ClipError("Nothing was heard. Check that the right microphone is selected and speak a bit closer.")
    start, end = _trim_bounds(a, sample_rate)
    a = a[start:end]
    seconds = len(a) / sample_rate
    if seconds < MIN_SECONDS:
        raise ClipError("That was too short. Say the whole phrase, e.g. \"Yes, I'm here\".")
    if seconds > MAX_SECONDS:
        raise ClipError(f"Replies can be at most {MAX_SECONDS:.0f} seconds. Keep it short.")

    top = max(abs(s) for s in a)
    gain = TARGET_PEAK * _FULL_SCALE / top
    fade = max(1, int(FADE_SECONDS * sample_rate))
    n = len(a)
    out = array("h", bytes(2 * n))
    for i, s in enumerate(a):
        g = gain
        if i < fade:
            g *= i / fade
        elif i >= n - fade:
            g *= (n - 1 - i) / fade
        out[i] = max(-_FULL_SCALE, min(_FULL_SCALE, int(round(s * g))))
    return Clip(out.tobytes(), sample_rate)


def write_wav(path: Path, clip: Clip) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(clip.sample_rate)
        w.writeframes(clip.pcm)
    tmp.replace(path)  # never leave a half-written reply behind


def read_wav(path: Path) -> Clip:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ClipError("That reply file is not in the expected format. Record it again.")
        return Clip(w.readframes(w.getnframes()), w.getframerate())

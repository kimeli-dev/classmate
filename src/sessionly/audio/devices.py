"""Microphone recording and playback to a chosen output (e.g. a virtual audio cable).

How a reply reaches the meeting: Sessionly plays it into a virtual cable's *input*
(e.g. VB-Audio "CABLE Input"), and Zoom/Meet use the cable's *output* as their
microphone. ``sounddevice`` is imported lazily so the rest of the app (and the tests)
work on machines without it; callers get ``AudioUnavailable`` with a readable message.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from sessionly.audio.clip import MAX_SECONDS, SAMPLE_RATE, Clip

log = logging.getLogger(__name__)

# Output names of common virtual cables, best match first.
CABLE_HINTS = ("cable input", "voicemeeter input", "voicemeeter aux input", "vb-audio", "virtual cable")


class AudioUnavailable(RuntimeError):
    """Audio can't be used right now; the message is shown to the user as-is."""


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    inputs: int
    outputs: int
    hostapi: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({self.hostapi})" if self.hostapi else self.name


def _sd():
    try:
        import sounddevice
    except (ImportError, OSError) as exc:  # OSError: PortAudio DLL missing
        raise AudioUnavailable("Audio support isn't installed. Run: pip install -r requirements.txt") from exc
    return sounddevice


def list_devices() -> list[Device]:
    sd = _sd()
    apis = [a["name"] for a in sd.query_hostapis()]
    return [Device(i, d["name"], d["max_input_channels"], d["max_output_channels"], apis[d["hostapi"]])
            for i, d in enumerate(sd.query_devices())]


def preferred_api(devices: list[Device]) -> list[Device]:
    """Windows lists every device once per audio API. Keep one entry per name, preferring
    DirectSound, then MME: both convert sample rates for us, whereas shared-mode WASAPI fails
    when the device's mixer rate isn't 48 kHz. Latency doesn't matter for short replies."""
    order = {"Windows DirectSound": 0, "MME": 1, "Windows WASAPI": 2}
    best: dict[str, Device] = {}
    for d in devices:
        key = d.name.lower()[:31]  # MME truncates names to 31 characters
        if key not in best or order.get(d.hostapi, 9) < order.get(best[key].hostapi, 9):
            best[key] = d
    return sorted(best.values(), key=lambda d: d.name.lower())


def find_cable(devices: list[Device]) -> Device | None:
    outputs = [d for d in devices if d.outputs > 0]
    for hint in CABLE_HINTS:
        for d in outputs:
            if hint in d.name.lower():
                return d
    return None


def find_by_name(devices: list[Device], name: str, *, output: bool) -> Device | None:
    for d in devices:
        if d.name == name and (d.outputs if output else d.inputs) > 0:
            return d
    return None


class Recorder:
    """Records mono 16-bit audio from a microphone until ``stop()`` or ``MAX_SECONDS``."""

    def __init__(self, device: int | None = None) -> None:
        self.device = device
        self._chunks: list[bytes] = []
        self._lock = threading.Lock()
        self._stream = None
        self.last_chunk = b""   # for the level meter

    def start(self) -> None:
        sd = _sd()
        limit = int(MAX_SECONDS * SAMPLE_RATE * 2) + SAMPLE_RATE  # bytes, with a second of slack

        def callback(indata, _frames, _time, status) -> None:
            if status:
                log.debug("Recording status: %s", status)
            data = bytes(indata)
            with self._lock:
                if sum(map(len, self._chunks)) < limit:
                    self._chunks.append(data)
                self.last_chunk = data

        try:
            self._stream = sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                             device=self.device, callback=callback)
            self._stream.start()
        except Exception as exc:  # PortAudioError and friends
            raise AudioUnavailable(f"The microphone couldn't be opened: {exc}") from exc

    @property
    def seconds(self) -> float:
        with self._lock:
            return sum(map(len, self._chunks)) / 2 / SAMPLE_RATE

    def stop(self) -> bytes:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            return b"".join(self._chunks)


class Player:
    """Plays one clip at a time to one or more outputs, off the UI thread.

    Starting a new clip stops the one playing, so pressing two hotkeys quickly never
    overlaps two replies in the meeting."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None

    def play(self, clip: Clip, outputs: list[int | None], on_error=None) -> None:
        sd = _sd()
        self.stop()
        self._stop = threading.Event()
        stop = self._stop

        def run() -> None:
            streams = []
            try:
                for dev in outputs:
                    s = sd.RawOutputStream(samplerate=clip.sample_rate, channels=1, dtype="int16", device=dev)
                    s.start()
                    streams.append(s)
                block = clip.sample_rate // 20 * 2  # 50 ms chunks so stop() is responsive
                for i in range(0, len(clip.pcm), block):
                    if stop.is_set():
                        break
                    chunk = clip.pcm[i:i + block]
                    for s in streams:
                        s.write(chunk)
            except Exception as exc:
                log.warning("Playback failed: %s", exc)
                if on_error:
                    on_error(f"Playback failed: {exc}")
            finally:
                for s in streams:
                    try:
                        s.stop()
                        s.close()
                    except Exception:
                        pass

        self._thread = threading.Thread(target=run, name="voice-reply", daemon=True)
        self._thread.start()

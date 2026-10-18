import math
from array import array

import pytest

from sessionly.audio.clip import SAMPLE_RATE, TARGET_PEAK, ClipError, peak, prepare_clip, read_wav, rms_dbfs
from sessionly.audio.devices import Device, find_by_name, find_cable, preferred_api
from sessionly.services import ValidationError
from sessionly.services.voice_replies import MAX_REPLIES, VoiceReplyService


def _tone(seconds, amp=0.3, freq=220.0):
    n = int(seconds * SAMPLE_RATE)
    return array("h", (int(amp * 32767 * math.sin(2 * math.pi * freq * i / SAMPLE_RATE)) for i in range(n))).tobytes()


def _silence(seconds):
    return bytes(2 * int(seconds * SAMPLE_RATE))


@pytest.fixture
def replies(db, tmp_path):
    return VoiceReplyService(db, tmp_path / "voice")


def test_clip_is_trimmed_padded_and_normalised():
    raw = _silence(1.0) + _tone(0.8, amp=0.2) + _silence(1.5)
    clip = prepare_clip(raw)
    assert 0.8 < clip.seconds < 1.2           # speech plus ~0.12 s padding each side
    assert abs(peak(clip.pcm) - TARGET_PEAK) < 0.01
    assert array("h", clip.pcm[:2])[0] == 0   # faded in: no click at the start


def test_quiet_and_loud_recordings_end_up_equally_loud():
    soft = prepare_clip(_tone(1.0, amp=0.05))
    loud = prepare_clip(_tone(1.0, amp=0.9))
    assert abs(rms_dbfs(soft.pcm) - rms_dbfs(loud.pcm)) < 0.5


@pytest.mark.parametrize("raw, message", [
    (_silence(2.0), "Nothing was heard"),
    (_silence(0.5) + _tone(0.05) + _silence(0.5), "too short"),
    (_tone(16.0), "at most 15 seconds"),
])
def test_unusable_recordings_are_explained(raw, message):
    with pytest.raises(ClipError, match=message):
        prepare_clip(raw)


def test_add_saves_a_wav_and_assigns_hotkeys_in_order(replies):
    a = replies.add("Present", prepare_clip(_tone(0.6)))
    b = replies.add("Yes, I'm here", prepare_clip(_tone(0.9)))
    assert [(r.label, r.hotkey) for r in replies.list()] == [("Present", "Ctrl+Alt+1"), ("Yes, I'm here", "Ctrl+Alt+2")]
    assert replies.path(a).exists() and 500 < b.duration_ms < 1200
    assert read_wav(replies.path(a)).sample_rate == SAMPLE_RATE


def test_labels_are_required_unique_and_short(replies):
    replies.add("Present", prepare_clip(_tone(0.6)))
    for bad in ("", "   ", "present", "x" * 41):
        with pytest.raises(ValidationError):
            replies.add(bad, prepare_clip(_tone(0.6)))


def test_at_most_nine_replies(replies):
    for i in range(MAX_REPLIES):
        replies.add(f"Reply {i}", prepare_clip(_tone(0.4)))
    with pytest.raises(ValidationError, match="up to 9"):
        replies.add("One more", prepare_clip(_tone(0.4)))


def test_delete_removes_the_file_and_closes_the_gap_in_hotkeys(replies):
    a = replies.add("Present", prepare_clip(_tone(0.6)))
    replies.add("Here", prepare_clip(_tone(0.6)))
    replies.add("Mic was off", prepare_clip(_tone(0.6)))
    replies.delete(a.id)
    assert not replies.path(a).exists()
    assert [(r.label, r.position) for r in replies.list()] == [("Here", 1), ("Mic was off", 2)]


def test_move_and_rename_and_rerecord(replies):
    a = replies.add("Present", prepare_clip(_tone(0.6)))
    b = replies.add("Here", prepare_clip(_tone(0.6)))
    replies.move(b.id, -1)
    assert [r.label for r in replies.list()] == ["Here", "Present"]
    replies.move(b.id, -1)  # already first: no change
    assert replies.rename(a.id, "  Yes   present ").label == "Yes present"
    assert replies.rerecord(a.id, prepare_clip(_tone(2.0))).duration_ms > 1900


def test_missing_recording_is_reported_not_crashed(replies):
    a = replies.add("Present", prepare_clip(_tone(0.6)))
    replies.path(a).unlink()
    with pytest.raises(ValidationError, match="missing"):
        replies.clip(a)


def test_virtual_cable_is_found_and_duplicates_collapse():
    devices = [
        Device(0, "Speakers (Realtek(R) Audio)", 0, 2, "MME"),
        Device(1, "CABLE Input (VB-Audio Virtual C", 0, 2, "MME"),
        Device(2, "CABLE Input (VB-Audio Virtual Cable)", 0, 2, "Windows DirectSound"),
        Device(3, "Microphone (Realtek(R) Audio)", 2, 0, "Windows WASAPI"),
    ]
    shown = preferred_api(devices)
    assert [d.index for d in shown if "CABLE" in d.name] == [2]
    assert find_cable(shown).index == 2
    assert find_by_name(shown, "Microphone (Realtek(R) Audio)", output=False).index == 3
    assert find_by_name(shown, "Microphone (Realtek(R) Audio)", output=True) is None
    assert find_cable([devices[0], devices[3]]) is None

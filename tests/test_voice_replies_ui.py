"""Voice replies window and playback routing, with the sound devices faked."""

import math
from array import array

import pytest

from sessionly.audio.clip import SAMPLE_RATE, prepare_clip
from sessionly.audio.devices import AudioUnavailable, Device
from sessionly.config import AppConfig
from sessionly.context import AppContext
from sessionly.services.settings import VOICE_MONITOR, VOICE_OUTPUT, VOICE_REPLY_KEY, VOICE_REPLY_KEY_REPLY
from sessionly.ui import voice_replies as vr

DEVICES = [
    Device(0, "Speakers (Realtek(R) Audio)", 0, 2, "Windows DirectSound"),
    Device(1, "CABLE Input (VB-Audio Virtual Cable)", 0, 2, "Windows DirectSound"),
    Device(2, "Microphone (Realtek(R) Audio)", 2, 0, "Windows DirectSound"),
]


def _tone(seconds=0.6):
    n = int(seconds * SAMPLE_RATE)
    return array("h", (int(9000 * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)) for i in range(n))).tobytes()


@pytest.fixture
def ctx(db, tmp_path):
    return AppContext.create(AppConfig(data_dir=tmp_path), db)


@pytest.fixture
def played(monkeypatch):
    calls = []
    monkeypatch.setattr(vr, "list_devices", lambda: DEVICES)
    monkeypatch.setattr(vr.Player, "play", lambda self, clip, outputs, on_error=None: calls.append(outputs))
    return calls


@pytest.fixture
def controller(qtbot, ctx):
    c = vr.VoiceReplyController(ctx)
    yield c
    c.shutdown()


def test_reply_goes_into_the_cable_and_to_your_speakers(ctx, controller, played):
    reply = ctx.voice_replies.add("Present", prepare_clip(_tone()))
    ctx.settings.set(VOICE_OUTPUT, "CABLE Input (VB-Audio Virtual Cable)")
    assert controller.play(reply)
    assert played == [[1, None]]
    ctx.settings.set(VOICE_MONITOR, False)
    controller.play_number(1)
    assert played[-1] == [1]


def test_without_a_cable_it_warns_and_only_plays_on_speakers(ctx, controller, played, qtbot):
    reply = ctx.voice_replies.add("Present", prepare_clip(_tone()))
    with qtbot.waitSignal(controller.failed) as sig:
        controller.play(reply)
    assert "aren't connected" in sig.args[0]
    assert played == [[None]]


def test_preview_never_goes_into_the_meeting(ctx, controller, played):
    reply = ctx.voice_replies.add("Present", prepare_clip(_tone()))
    ctx.settings.set(VOICE_OUTPUT, "CABLE Input (VB-Audio Virtual Cable)")
    controller.play(reply, into_meeting=False)
    assert played == [[None]]


def test_missing_audio_support_is_reported(ctx, controller, monkeypatch, qtbot):
    def unavailable():
        raise AudioUnavailable("Audio support isn't installed.")
    monkeypatch.setattr(vr, "list_devices", unavailable)
    reply = ctx.voice_replies.add("Present", prepare_clip(_tone()))
    with qtbot.waitSignal(controller.failed) as sig:
        assert not controller.play(reply)
    assert "isn't installed" in sig.args[0]


def test_dialog_lists_replies_and_preselects_the_detected_cable(ctx, controller, played, qtbot):
    ctx.voice_replies.add("Present", prepare_clip(_tone()))
    ctx.voice_replies.add("Yes, I'm here", prepare_clip(_tone()))
    dialog = vr.VoiceRepliesDialog(ctx, controller)
    qtbot.addWidget(dialog)
    assert dialog.list.count() == 2 and "Ctrl+Alt+2" in dialog.list.item(1).text()
    assert ctx.settings.get(VOICE_OUTPUT) == "CABLE Input (VB-Audio Virtual Cable)"
    assert dialog.output.currentData() == "CABLE Input (VB-Audio Virtual Cable)"


def test_reply_key_says_the_chosen_reply_else_reply_one(ctx, controller, played):
    ctx.settings.set(VOICE_OUTPUT, "CABLE Input (VB-Audio Virtual Cable)")
    ctx.settings.set(VOICE_MONITOR, False)
    first = ctx.voice_replies.add("Present", prepare_clip(_tone()))
    here = ctx.voice_replies.add("Yes, I'm here", prepare_clip(_tone()))
    assert controller.reply_key() == "F9"                 # default
    assert controller.reply_key_reply().id == first.id     # nothing chosen yet: reply 1
    ctx.settings.set(VOICE_REPLY_KEY_REPLY, here.id)
    controller._hotkey(vr.REPLY_KEY_ID)                    # what pressing F9 does
    assert played == [[1]]
    assert controller.reply_key_reply().id == here.id
    ctx.voice_replies.delete(here.id)                      # chosen reply gone: falls back to reply 1
    assert controller.reply_key_reply().id == first.id


def test_pressing_the_reply_key_while_playing_stops_it(ctx, controller, played, monkeypatch):
    ctx.voice_replies.add("Present", prepare_clip(_tone()))
    stopped = []
    monkeypatch.setattr(vr.Player, "playing", property(lambda self: True))
    monkeypatch.setattr(vr.Player, "stop", lambda self: stopped.append(True))
    controller.press_reply_key()
    assert stopped and played == []


def test_reply_key_without_any_reply_explains(ctx, controller, played, qtbot):
    with qtbot.waitSignal(controller.failed) as sig:
        controller.press_reply_key()
    assert "No reply recorded" in sig.args[0] and played == []


def test_reply_key_can_be_turned_off_or_changed_in_the_dialog(ctx, controller, played, qtbot):
    ctx.voice_replies.add("Present", prepare_clip(_tone()))
    dialog = vr.VoiceRepliesDialog(ctx, controller)
    qtbot.addWidget(dialog)
    assert dialog.reply_key.currentData() == "F9" and dialog.reply_key_reply.currentText() == "Present"
    dialog.reply_key.setCurrentIndex(dialog.reply_key.findData("Pause"))
    assert ctx.settings.get(VOICE_REPLY_KEY) == "Pause" and controller.reply_key() == "Pause"
    dialog.reply_key.setCurrentIndex(dialog.reply_key.findData(""))
    assert controller.reply_key() == ""


def test_tray_menu_lists_replies_with_hotkeys(ctx, controller, played, qtbot):
    from PySide6.QtWidgets import QMenu
    ctx.voice_replies.add("Present", prepare_clip(_tone()))
    menu = QMenu()
    controller.fill_menu(menu, lambda: None)
    texts = [a.text() for a in menu.actions() if a.text()]
    assert texts[0] == "Present\tF9, Ctrl+Alt+1"   # reply 1 is also on the Reply key
    assert "Record and manage replies…" in texts

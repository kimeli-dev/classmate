"""One-tap voice replies: record short phrases in your own voice once, then play one into the
meeting when you press it (Voice replies window, tray "Say…" menu, or Ctrl+Alt+1-9).

Nothing here is triggered automatically - Sessionly doesn't listen to the meeting.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from sessionly.audio.clip import MAX_SECONDS, SAMPLE_RATE, Clip, rms_dbfs
from sessionly.audio.devices import (
    AudioUnavailable, Device, Player, Recorder, find_by_name, find_cable, list_devices, preferred_api,
)
from sessionly.context import AppContext
from sessionly.services import ValidationError
from sessionly.services.settings import (
    VOICE_HOTKEYS, VOICE_MIC, VOICE_MONITOR, VOICE_OUTPUT, VOICE_REPLY_KEY, VOICE_REPLY_KEY_REPLY,
)
from sessionly.services.voice_replies import MAX_REPLIES, SUGGESTED, VoiceReply
from sessionly.ui import hotkeys as hk

log = logging.getLogger(__name__)

REPLY_KEY_ID = 0  # hotkey id of the single Reply key; 1-9 are the numbered replies

CABLE_HELP = (
    "<b>How a reply reaches the meeting</b><ol style='margin-left:-20px'>"
    "<li>Install a free virtual audio cable, e.g. <i>VB-CABLE</i> from vb-audio.com, then restart.</li>"
    "<li>Below, set <b>Play replies into</b> to <i>CABLE Input</i>.</li>"
    "<li>In Zoom or Meet, set the <b>microphone</b> to <i>CABLE Output</i>.</li>"
    "<li>So people still hear your live voice: Windows Sound settings → your microphone → "
    "<i>Properties → Listen</i> → tick <i>Listen to this device</i> and choose <i>CABLE Input</i>.</li></ol>"
    "Use <b>Test into meeting</b> while someone listens (or Zoom's <i>Test mic</i>) to check."
)


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Muted")
    return label


class VoiceReplyController(QObject):
    """Plays replies and owns the hotkeys. One per app (created by the main window)."""

    played = Signal(str)          # label - for a quiet confirmation
    failed = Signal(str)          # message to show
    replies_changed = Signal()
    _async_error = Signal(str)    # from the playback thread

    def __init__(self, ctx: AppContext, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.player = Player()
        self.hotkeys = hk.GlobalHotkeys(self._hotkey)
        self._async_error.connect(self.failed)
        self.replies_changed.connect(self.refresh_hotkeys)
        self.refresh_hotkeys()

    # ---- devices ------------------------------------------------------------------

    def devices(self) -> list[Device]:
        return preferred_api(list_devices())

    def output_device(self, devices: list[Device]) -> Device | None:
        name = self.ctx.settings.get(VOICE_OUTPUT, "")
        return find_by_name(devices, name, output=True) if name else None

    def mic_device(self, devices: list[Device]) -> Device | None:
        name = self.ctx.settings.get(VOICE_MIC, "")
        return find_by_name(devices, name, output=False) if name else None

    # ---- playback ---------------------------------------------------------------

    def play(self, reply: VoiceReply, *, into_meeting: bool = True) -> bool:
        """Play a reply. ``into_meeting=False`` previews it on your speakers only."""
        try:
            clip = self.ctx.voice_replies.clip(reply)
            devices = self.devices()
        except (ValidationError, AudioUnavailable) as exc:
            self.failed.emit(str(exc))
            return False
        outputs: list[int | None] = []
        if into_meeting:
            cable = self.output_device(devices)
            if cable is None:
                self.failed.emit("Replies aren't connected to your meetings yet. Choose a virtual cable under "
                                 "Settings → Voice replies; until then they play on your speakers only.")
            else:
                outputs.append(cable.index)
        if not into_meeting or not outputs or self.ctx.settings.get(VOICE_MONITOR, True):
            outputs.append(None)  # Windows default output: your speakers / headphones
        try:
            self.player.play(clip, outputs, on_error=self._async_error.emit)
        except AudioUnavailable as exc:
            self.failed.emit(str(exc))
            return False
        log.info("Voice reply id=%s played (%s)", reply.id, "meeting" if into_meeting else "preview")
        self.played.emit(reply.label)
        return True

    def play_number(self, number: int) -> None:
        reply = next((r for r in self.ctx.voice_replies.list() if r.position == number), None)
        if reply:
            self.play(reply)

    def stop(self) -> None:
        self.player.stop()

    # ---- reply key ---------------------------------------------------------------

    def reply_key(self) -> str:
        """Name of the single Reply key, or "" when it's turned off."""
        name = self.ctx.settings.get(VOICE_REPLY_KEY, hk.DEFAULT_REPLY_KEY)
        return name if name in hk.REPLY_KEYS else ""

    def reply_key_reply(self) -> VoiceReply | None:
        """The reply the Reply key plays: the one chosen for it, else reply 1."""
        replies = self.ctx.voice_replies.list()
        chosen = self.ctx.settings.get(VOICE_REPLY_KEY_REPLY)
        return next((r for r in replies if r.id == chosen), replies[0] if replies else None)

    def press_reply_key(self) -> None:
        """Play the main reply; pressing again while it plays stops it (to cancel a mistaken press)."""
        if self.player.playing:
            self.stop()
            return
        reply = self.reply_key_reply()
        if reply is None:
            self.failed.emit("No reply recorded yet. Record one under Settings → Voice replies.")
        else:
            self.play(reply)

    # ---- hotkeys / menus ----------------------------------------------------------

    def _hotkey(self, key_id: int) -> None:
        if key_id == REPLY_KEY_ID:
            self.press_reply_key()
        else:
            self.play_number(key_id)

    def refresh_hotkeys(self) -> None:
        keys: dict[int, tuple[str, tuple[int, int]]] = {}
        if name := self.reply_key():
            keys[REPLY_KEY_ID] = (name, hk.REPLY_KEYS[name])
        if self.ctx.settings.get(VOICE_HOTKEYS, True):
            for r in self.ctx.voice_replies.list():
                keys[r.position] = (r.hotkey, hk.numbered_key(r.position))
        self.hotkeys.set_keys(keys)

    def fill_menu(self, menu: QMenu, manage) -> None:
        """(Re)build a "Say…" menu: one item per reply, then Stop and Manage."""
        menu.clear()
        replies = self.ctx.voice_replies.list()
        main = self.reply_key_reply()
        key = self.reply_key()
        for r in replies:
            shortcut = f"{key}, {r.hotkey}" if key and main and r.id == main.id else r.hotkey
            action = menu.addAction(f"{r.label}\t{shortcut}")
            action.triggered.connect(lambda _=False, r=r: self.play(r))
        if not replies:
            menu.addAction("No replies recorded yet").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Stop playing", self.stop)
        menu.addAction("Record and manage replies…", manage)

    def shutdown(self) -> None:
        self.player.stop()
        self.hotkeys.clear()


class RecordDialog(QDialog):
    """Record (or re-record) one reply, hear it back, and save it."""

    def __init__(self, ctx: AppContext, controller: VoiceReplyController, reply: VoiceReply | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx, self.controller, self.reply = ctx, controller, reply
        self.clip: Clip | None = None
        self.recorder: Recorder | None = None
        self.saved: VoiceReply | None = None
        self.setWindowTitle(f"Re-record \"{reply.label}\"" if reply else "Record a reply")
        self.setMinimumWidth(460)

        self.label = QComboBox()
        self.label.setEditable(True)
        used = {r.label.lower() for r in ctx.voice_replies.list()}
        self.label.addItems([s for s in SUGGESTED if s.lower() not in used])
        if reply:
            self.label.setEditText(reply.label)
            self.label.setEnabled(False)
        self.record_btn = QPushButton("●  Record")
        self.record_btn.setProperty("accent", True)
        self.record_btn.clicked.connect(self._toggle)
        self.level = QProgressBar()
        self.level.setRange(0, 60)
        self.level.setTextVisible(False)
        self.level.setFixedHeight(8)
        self.status = QLabel("Press Record, say the phrase once, then press Stop.")
        self.status.setWordWrap(True)
        self.play_btn = QPushButton("▶  Play back")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._play_back)

        form = QFormLayout()
        form.addRow("&Reply", self.label)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(self.record_btn)
        row.addWidget(self.play_btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self.level)
        layout.addWidget(self.status)
        layout.addWidget(_hint("Speak as you normally would in a meeting. Sessionly trims the silence and evens "
                               f"out the volume, so all your replies sound the same. Up to {MAX_SECONDS:.0f} s."))
        self.box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.box.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.box.accepted.connect(self.accept)
        self.box.rejected.connect(self.reject)
        layout.addWidget(self.box)

        self.meter = QTimer(self)
        self.meter.setInterval(60)
        self.meter.timeout.connect(self._tick)

    def _toggle(self) -> None:
        if self.recorder is None:
            self._start()
        else:
            self._stop()

    def _start(self) -> None:
        self.controller.stop()
        try:
            mic = self.controller.mic_device(self.controller.devices())
            self.recorder = Recorder(mic.index if mic else None)
            self.recorder.start()
        except AudioUnavailable as exc:
            self.recorder = None
            QMessageBox.warning(self, "Can't record", str(exc))
            return
        self.record_btn.setText("■  Stop")
        self.play_btn.setEnabled(False)
        self.box.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.status.setText("Recording… say your reply now.")
        self.meter.start()

    def _tick(self) -> None:
        if self.recorder is None:
            return
        self.level.setValue(int(max(0.0, rms_dbfs(self.recorder.last_chunk) + 60)))
        secs = self.recorder.seconds
        self.status.setText(f"Recording… {secs:.1f} s")
        if secs >= MAX_SECONDS:
            self._stop()

    def _stop(self) -> None:
        self.meter.stop()
        self.level.setValue(0)
        pcm = self.recorder.stop()
        self.recorder = None
        self.record_btn.setText("●  Record again")
        try:
            self.clip = self.ctx.voice_replies.process(pcm, SAMPLE_RATE)
        except ValidationError as exc:
            self.clip = None
            self.status.setText(str(exc))
            return
        self.status.setText(f"Got it - {self.clip.seconds:.1f} s. Play it back, then Save.")
        self.play_btn.setEnabled(True)
        self.box.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)

    def _play_back(self) -> None:
        if self.clip:
            try:
                self.controller.player.play(self.clip, [None])
            except AudioUnavailable as exc:
                QMessageBox.warning(self, "Can't play", str(exc))

    def accept(self) -> None:
        if self.clip is None:
            return
        try:
            if self.reply:
                self.saved = self.ctx.voice_replies.rerecord(self.reply.id, self.clip)
            else:
                self.saved = self.ctx.voice_replies.add(self.label.currentText(), self.clip)
        except ValidationError as exc:
            QMessageBox.warning(self, "Check the reply", str(exc))
            return
        super().accept()

    def reject(self) -> None:
        if self.recorder is not None:
            self.meter.stop()
            self.recorder.stop()
            self.recorder = None
        super().reject()


class VoiceRepliesDialog(QDialog):
    """Manage replies and where they're played."""

    def __init__(self, ctx: AppContext, controller: VoiceReplyController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx, self.controller = ctx, controller
        self.setWindowTitle("Voice replies")
        self.setMinimumSize(560, 600)

        intro = _hint("Record short replies once in your own voice. During a meeting, press your <b>Reply key</b> "
                      "and Sessionly says your reply into the meeting. Press it again to stop. Other replies are in "
                      "the tray icon's <b>Say…</b> menu and on Ctrl+Alt+1-9. Replies only ever play when you "
                      "press a key.")
        intro.setTextFormat(Qt.TextFormat.RichText)

        self.reply_key = QComboBox()
        self.reply_key.setAccessibleName("Reply key")
        self.reply_key.addItem("Off", "")
        for name in hk.REPLY_KEYS:
            self.reply_key.addItem(name, name)
        self.reply_key.setCurrentIndex(max(0, self.reply_key.findData(controller.reply_key())))
        self.reply_key_reply = QComboBox()
        self.reply_key_reply.setAccessibleName("Reply the key plays")
        key_box = QGroupBox("Reply key")
        kf = QFormLayout(key_box)
        kf.addRow("Press", self.reply_key)
        kf.addRow("It &says", self.reply_key_reply)
        kf.addRow("", _hint("Works while Zoom or Meet is in front. Pick a key your meeting app doesn't use."))

        self.list = QListWidget()
        self.list.setAccessibleName("Voice replies")
        self.list.itemDoubleClicked.connect(lambda *_: self._preview())
        self.list.currentRowChanged.connect(lambda *_: self._sync_buttons())
        self.add_btn = QPushButton("●  &Record new…")
        self.add_btn.setProperty("accent", True)
        self.add_btn.clicked.connect(self._record_new)
        self.preview_btn = QPushButton("▶  &Preview")
        self.preview_btn.setToolTip("Play on your speakers only")
        self.preview_btn.clicked.connect(self._preview)
        self.test_btn = QPushButton("&Test into meeting")
        self.test_btn.setToolTip("Play into the meeting, exactly as the hotkey would")
        self.test_btn.clicked.connect(self._test)
        self.rerecord_btn = QPushButton("Re-record…")
        self.rerecord_btn.clicked.connect(self._rerecord)
        self.rename_btn = QPushButton("Re&name…")
        self.rename_btn.clicked.connect(self._rename)
        self.up_btn = QPushButton("↑")
        self.up_btn.setAccessibleName("Move up")
        self.up_btn.clicked.connect(lambda: self._move(-1))
        self.down_btn = QPushButton("↓")
        self.down_btn.setAccessibleName("Move down")
        self.down_btn.clicked.connect(lambda: self._move(1))
        self.delete_btn = QPushButton("&Delete")
        self.delete_btn.clicked.connect(self._delete)
        for b in (self.up_btn, self.down_btn):
            b.setFixedWidth(36)

        replies_box = QGroupBox("Your replies")
        rv = QVBoxLayout(replies_box)
        rv.addWidget(self.list)
        r1 = QHBoxLayout()
        for b in (self.add_btn, self.preview_btn, self.test_btn):
            r1.addWidget(b)
        r1.addStretch()
        r2 = QHBoxLayout()
        for b in (self.rerecord_btn, self.rename_btn, self.up_btn, self.down_btn, self.delete_btn):
            r2.addWidget(b)
        r2.addStretch()
        rv.addLayout(r1)
        rv.addLayout(r2)

        self.mic = QComboBox()
        self.output = QComboBox()
        self.monitor = QCheckBox("Also play replies on my speakers or headphones")
        self.hotkeys = QCheckBox("Hotkeys Ctrl+Alt+1-9 work while Zoom or Meet is in front")
        self.hotkey_note = QLabel()
        self.hotkey_note.setWordWrap(True)
        self.hotkey_note.setObjectName("Muted")
        devices_box = QGroupBox("Sound")
        df = QFormLayout(devices_box)
        df.addRow("Record &with", self.mic)
        df.addRow("&Play replies into", self.output)
        df.addRow("", self.monitor)
        df.addRow("", self.hotkeys)
        df.addRow("", self.hotkey_note)
        help_label = QLabel(CABLE_HELP)
        help_label.setWordWrap(True)
        help_label.setTextFormat(Qt.TextFormat.RichText)
        df.addRow(help_label)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(key_box)
        layout.addWidget(replies_box, 1)
        layout.addWidget(devices_box)
        layout.addWidget(close)

        self._load_devices()
        self.mic.currentIndexChanged.connect(lambda _: self.ctx.settings.set(VOICE_MIC, self.mic.currentData() or ""))
        self.output.currentIndexChanged.connect(
            lambda _: self.ctx.settings.set(VOICE_OUTPUT, self.output.currentData() or ""))
        self.monitor.setChecked(bool(ctx.settings.get(VOICE_MONITOR, True)))
        self.monitor.toggled.connect(lambda on: self.ctx.settings.set(VOICE_MONITOR, on))
        self.hotkeys.setChecked(bool(ctx.settings.get(VOICE_HOTKEYS, True)))
        self.hotkeys.toggled.connect(self._toggle_hotkeys)
        self.reply_key.currentIndexChanged.connect(self._reply_key_changed)
        self.reply_key_reply.currentIndexChanged.connect(self._reply_key_reply_changed)
        self._reload()

    # ---- reply key ----------------------------------------------------------------

    def _reply_key_changed(self, _index: int) -> None:
        self.ctx.settings.set(VOICE_REPLY_KEY, self.reply_key.currentData() or "")
        self.controller.refresh_hotkeys()
        self._sync_hotkey_note()

    def _reply_key_reply_changed(self, _index: int) -> None:
        if self.reply_key_reply.currentData() is not None:
            self.ctx.settings.set(VOICE_REPLY_KEY_REPLY, self.reply_key_reply.currentData())

    def _load_reply_key_reply(self) -> None:
        main = self.controller.reply_key_reply()
        self.reply_key_reply.blockSignals(True)
        self.reply_key_reply.clear()
        for r in self.replies:
            self.reply_key_reply.addItem(r.label, r.id)
        if not self.replies:
            self.reply_key_reply.addItem("Record a reply first", None)
        self.reply_key_reply.setCurrentIndex(max(0, self.reply_key_reply.findData(main.id if main else None)))
        self.reply_key_reply.setEnabled(bool(self.replies))
        self.reply_key_reply.blockSignals(False)

    # ---- devices ------------------------------------------------------------------

    def _load_devices(self) -> None:
        try:
            devices = self.controller.devices()
        except AudioUnavailable as exc:
            for combo in (self.mic, self.output):
                combo.addItem(str(exc), "")
                combo.setEnabled(False)
            return
        self.mic.addItem("Windows default microphone", "")
        for d in devices:
            if d.inputs:
                self.mic.addItem(d.name, d.name)
        self.output.addItem("Nothing - play on my speakers only", "")
        for d in devices:
            if d.outputs:
                self.output.addItem(d.name, d.name)
        saved_out = self.ctx.settings.get(VOICE_OUTPUT, "")
        if not saved_out:
            cable = find_cable(devices)
            if cable:  # first time: pre-select the detected cable
                saved_out = cable.name
                self.ctx.settings.set(VOICE_OUTPUT, saved_out)
        for combo, value in ((self.mic, self.ctx.settings.get(VOICE_MIC, "")), (self.output, saved_out)):
            i = combo.findData(value)
            combo.setCurrentIndex(max(0, i))

    def _toggle_hotkeys(self, on: bool) -> None:
        self.ctx.settings.set(VOICE_HOTKEYS, on)
        self.controller.refresh_hotkeys()
        self._sync_hotkey_note()

    def _sync_hotkey_note(self) -> None:
        if not hk.supported():
            self.hotkey_note.setText("Hotkeys are only available on Windows.")
        elif self.controller.hotkeys.failed:
            taken = ", ".join(self.controller.hotkeys.failed)
            self.hotkey_note.setText(f"{taken} is already used by another app - pick another Reply key, "
                                     "or use the tray menu.")
        else:
            self.hotkey_note.setText("")

    # ---- replies ------------------------------------------------------------------

    def _reload(self, select_id: int | None = None) -> None:
        self.replies = self.ctx.voice_replies.list()
        self.list.clear()
        for r in self.replies:
            item = QListWidgetItem(f"{r.label}    ·    {r.duration_ms / 1000:.1f} s    ·    {r.hotkey}")
            item.setData(Qt.ItemDataRole.UserRole, r.id)
            self.list.addItem(item)
            if r.id == select_id:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.replies:
            self.list.setCurrentRow(0)
        self.add_btn.setEnabled(len(self.replies) < MAX_REPLIES)
        self._load_reply_key_reply()
        self._sync_buttons()
        self._sync_hotkey_note()

    def _selected(self) -> VoiceReply | None:
        row = self.list.currentRow()
        return self.replies[row] if 0 <= row < len(self.replies) else None

    def _sync_buttons(self) -> None:
        has = self._selected() is not None
        for b in (self.preview_btn, self.test_btn, self.rerecord_btn, self.rename_btn, self.up_btn, self.down_btn,
                  self.delete_btn):
            b.setEnabled(has)

    def _changed(self, select_id: int | None = None) -> None:
        self._reload(select_id)
        self.controller.replies_changed.emit()

    def _record_new(self) -> None:
        dialog = RecordDialog(self.ctx, self.controller, parent=self)
        if dialog.exec():
            self._changed(dialog.saved.id)

    def _rerecord(self) -> None:
        r = self._selected()
        if r and RecordDialog(self.ctx, self.controller, r, parent=self).exec():
            self._changed(r.id)

    def _preview(self) -> None:
        if r := self._selected():
            self.controller.play(r, into_meeting=False)

    def _test(self) -> None:
        if r := self._selected():
            self.controller.play(r, into_meeting=True)

    def _rename(self) -> None:
        r = self._selected()
        if not r:
            return
        text, ok = QInputDialog.getText(self, "Rename reply", "Name:", text=r.label)
        if ok:
            try:
                self.ctx.voice_replies.rename(r.id, text)
            except ValidationError as exc:
                QMessageBox.warning(self, "Check the name", str(exc))
                return
            self._changed(r.id)

    def _move(self, delta: int) -> None:
        if r := self._selected():
            self.ctx.voice_replies.move(r.id, delta)
            self._changed(r.id)

    def _delete(self) -> None:
        r = self._selected()
        if r and QMessageBox.question(self, "Delete reply", f"Delete \"{r.label}\" and its recording?") \
                == QMessageBox.StandardButton.Yes:
            self.ctx.voice_replies.delete(r.id)
            self._changed()

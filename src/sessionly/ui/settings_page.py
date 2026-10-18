from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from sessionly import __version__
from sessionly.context import AppContext
from sessionly.services import startup
from sessionly.services.meeting_launch import valid_email
from sessionly.services.settings import (
    AUTO_OPEN_LINKS, AUTOMATION_PAUSED, GOOGLE_MEET_ACCOUNT, GOOGLE_MEET_ALLOWED, VOICE_OUTPUT, ZOOM_QUIET_JOIN_DONE,
)


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


class SettingsPage(QWidget):
    data_changed = Signal()
    voice_replies_requested = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        title = QLabel("Settings")
        title.setObjectName("Title")

        self.display_name = QLineEdit()
        self.display_name.setPlaceholderText("The name you use in online meetings")
        self.saved = QLabel()
        self.saved.setObjectName("Muted")
        save = QPushButton("&Save")
        save.setProperty("accent", True)
        save.clicked.connect(self.save)
        self.display_name.returnPressed.connect(self.save)
        name_row = QHBoxLayout()
        name_row.addWidget(self.display_name)
        name_row.addWidget(save)
        profile = QGroupBox("Profile")
        pf = QFormLayout(profile)
        name_label = QLabel("Default &display name")
        name_label.setBuddy(self.display_name)
        pf.addRow(name_label, name_row)
        pf.addRow("", self.saved)

        background = QGroupBox("Background")
        bv = QVBoxLayout(background)
        self.startup = QCheckBox("Start Sessionly in the background when I sign in to Windows")
        self.startup.toggled.connect(self._toggle_startup)
        self.auto_open = QCheckBox("Open meeting links automatically at preparation time")
        self.auto_open.toggled.connect(lambda on: self._set(AUTO_OPEN_LINKS, on))
        self.paused = QCheckBox("Pause all automation (no reminders, nothing opened)")
        self.paused.toggled.connect(lambda on: self._set(AUTOMATION_PAUSED, on))
        bv.addWidget(self.startup)
        bv.addWidget(_hint("Closing the window keeps Sessionly running in the hidden icons (^) next to the "
                           "clock. Quit from the tray icon's menu."))
        bv.addWidget(self.auto_open)
        bv.addWidget(_hint("Sessionly opens Zoom in the Zoom app (with your saved passcode) and Meet with your "
                           "allowed Google account - see Joining meetings below. It can't see inside the meeting or "
                           "skip waiting rooms, so you confirm with \"I'm in\". Meetings with automatic actions "
                           "turned off are only reminded."))
        bv.addWidget(self.paused)
        bv.addWidget(_hint("Nothing runs while the laptop is asleep, shut down or Sessionly has been quit. "
                           "Sessions that passed meanwhile are reported when it starts again."))

        joining = QGroupBox("Joining meetings")
        mv = QVBoxLayout(joining)
        mv.addWidget(QLabel("<b>Zoom</b>"))
        mv.addWidget(_hint("Save each meeting's passcode on the Meetings page. Sessionly opens the Zoom app with the "
                           "meeting ID, passcode and your display name, so Zoom joins with the account you're "
                           "signed in to in the app. If the Zoom app isn't installed, the link opens in your "
                           "browser and the passcode is copied for you to paste."))
        mv.addWidget(QLabel("<b>Google Meet</b>"))
        self.google_email = QLineEdit()
        self.google_email.setPlaceholderText("you@example.com")
        self.google_email.setAccessibleName("Google account for Meet")
        self.google_email.textChanged.connect(self._google_email_changed)
        self.google_email.editingFinished.connect(self._save_google_email)
        gform = QFormLayout()
        email_label = QLabel("Google &account")
        email_label.setBuddy(self.google_email)
        gform.addRow(email_label, self.google_email)
        mv.addLayout(gform)
        self.google_allowed = QCheckBox("Allow Sessionly to open Google Meet with this account")
        self.google_allowed.toggled.connect(self._toggle_google)
        mv.addWidget(self.google_allowed)
        mv.addWidget(_hint("Meet only lets you in with a signed-in Google account. Sign in to this account in "
                           "your browser once; after you allow it, Sessionly opens every Meet meeting as this "
                           "account. Sessionly never sees your Google password. You still click Join (or Ask to "
                           "join) and the host may need to admit you."))

        quiet = QGroupBox("Join with your mic off")
        qv = QVBoxLayout(quiet)
        qv.addWidget(_hint("Zoom decides mute-on-join from its own settings - a link can't change it. Set these "
                           "once in the Zoom app (profile picture → Settings) and every meeting Sessionly opens will "
                           "skip the preview and join with your microphone off (the wording differs slightly "
                           "between Zoom versions):"))
        qv.addWidget(QLabel(
            "<ol style='margin-left:-20px'>"
            "<li><b>Audio</b>: tick <i>Automatically join audio by computer when joining a meeting</i></li>"
            "<li><b>Audio</b>: tick <i>Always mute my microphone when joining a meeting</i></li>"
            "<li><b>Video</b>: tick <i>Always turn off my video when joining a meeting</i></li>"
            "<li><b>Video</b>: untick <i>Always show video preview dialog when joining a video meeting</i></li>"
            "</ol>"))
        open_zoom = QPushButton("Open Zoom")
        open_zoom.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("zoommtg://zoom.us/")))
        self.quiet_done = QCheckBox("I've changed these Zoom settings")
        self.quiet_done.toggled.connect(lambda on: self.ctx.settings.set(ZOOM_QUIET_JOIN_DONE, on))
        qrow = QHBoxLayout()
        qrow.addWidget(open_zoom)
        qrow.addWidget(self.quiet_done)
        qrow.addStretch()
        qv.addLayout(qrow)
        qv.addWidget(_hint("Google Meet: on the join screen press Ctrl+D (mic) and Ctrl+E (camera) before "
                           "clicking Join. In Zoom, Alt+A toggles your mic at any time."))

        voice = QGroupBox("Voice replies")
        vv = QVBoxLayout(voice)
        vv.addWidget(_hint("Record short replies in your own voice once - \"Present\", \"Yes, I'm here\", "
                           "\"Sorry, my mic was off\" - then press your Reply key (F9 unless you change it) and "
                           "Sessionly says your reply into the meeting. Other replies are in the tray icon's Say… "
                           "menu and on Ctrl+Alt+1-9. Replies play only when you press a key; Sessionly never "
                           "listens to the meeting or answers for you."))
        self.voice_status = QLabel()
        manage_voice = QPushButton("Record and manage replies…")
        manage_voice.clicked.connect(self.voice_replies_requested.emit)
        vrow = QHBoxLayout()
        vrow.addWidget(manage_voice)
        vrow.addWidget(self.voice_status, 1)
        vv.addLayout(vrow)

        storage = QGroupBox("Your data")
        sf = QFormLayout(storage)
        sf.addRow("Data folder", self._path_row(ctx.config.data_dir))
        sf.addRow("Log folder", self._path_row(ctx.config.log_dir))
        sf.addRow("", _hint("Logs never contain meeting links, passcodes or e-mail addresses."))

        about = _hint(f"Sessionly {__version__}. See docs/CAPABILITIES.md for what it can and can't do.")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        for w in (profile, background, joining, quiet, voice, storage, about):
            layout.addWidget(w)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.load()

    def load(self) -> None:
        self.display_name.setText(self.ctx.settings.display_name)
        count = len(self.ctx.voice_replies.list())
        routed = bool(self.ctx.settings.get(VOICE_OUTPUT, ""))
        self.voice_status.setText(
            "No replies recorded yet." if not count else
            f"{count} repl{'y' if count == 1 else 'ies'} recorded"
            + ("." if routed else " - not connected to meetings yet (choose a virtual cable)."))
        self.google_email.blockSignals(True)
        self.google_email.setText(self.ctx.settings.get(GOOGLE_MEET_ACCOUNT, ""))
        self.google_email.blockSignals(False)
        self.google_allowed.blockSignals(True)
        self.google_allowed.setChecked(bool(self.ctx.settings.get(GOOGLE_MEET_ALLOWED, False)))
        self.google_allowed.blockSignals(False)
        self.google_allowed.setEnabled(valid_email(self.google_email.text()))
        for box, value in ((self.quiet_done, bool(self.ctx.settings.get(ZOOM_QUIET_JOIN_DONE, False))),
                           (self.startup, startup.is_enabled()),
                           (self.auto_open, bool(self.ctx.settings.get(AUTO_OPEN_LINKS, False))),
                           (self.paused, bool(self.ctx.settings.get(AUTOMATION_PAUSED, False)))):
            box.blockSignals(True)
            box.setChecked(value)
            box.blockSignals(False)

    def _google_email_changed(self, text: str) -> None:
        ok = valid_email(text)
        self.google_allowed.setEnabled(ok)
        if not ok and self.google_allowed.isChecked():
            self.google_allowed.setChecked(False)  # permission belongs to one specific account

    def _save_google_email(self) -> None:
        email = self.google_email.text().strip()
        if email != self.ctx.settings.get(GOOGLE_MEET_ACCOUNT, ""):
            self.ctx.settings.set(GOOGLE_MEET_ACCOUNT, email)
            if self.google_allowed.isChecked():  # a new account needs a fresh "allow"
                self.google_allowed.setChecked(False)

    def _toggle_google(self, on: bool) -> None:
        if on:
            self._save_google_email()
            email = self.google_email.text().strip()
            answer = QMessageBox.question(
                self, "Use this Google account for Meet?",
                f"Sessionly will open your Google Meet meetings as {email}.\n\n"
                "It only adds the account to the meeting link - it never sees your password or signs in for "
                "you. Make sure you're signed in to this account in your browser. Allow?")
            if answer != QMessageBox.StandardButton.Yes:
                self.google_allowed.blockSignals(True)
                self.google_allowed.setChecked(False)
                self.google_allowed.blockSignals(False)
                return
        self._set(GOOGLE_MEET_ALLOWED, on)

    def _set(self, key: str, value: bool) -> None:
        self.ctx.settings.set(key, value)
        self.data_changed.emit()

    def _toggle_startup(self, on: bool) -> None:
        try:
            startup.set_enabled(on)
        except OSError as exc:
            QMessageBox.warning(self, "Start with Windows", f"Windows did not allow the change: {exc}")
        self.load()

    def _path_row(self, path: Path) -> QWidget:
        label = QLabel(str(path))
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setToolTip(str(path))
        # Long paths must not widen the page; they're clipped, with the full path in the tooltip.
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        button = QPushButton("Open")
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(label, 1)
        h.addWidget(button)
        return row

    def save(self) -> None:
        self.ctx.settings.display_name = self.display_name.text()
        self.saved.setText("Saved.")
        self.data_changed.emit()

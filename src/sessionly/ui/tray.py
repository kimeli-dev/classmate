"""System-tray (hidden icons) presence and the background worker loop.

Sessionly keeps running here after the window is closed. Every 30 seconds it asks the
automation engine what to do, shows quiet notifications, opens links when allowed, and
updates the tray icon badge:

    plain       nothing soon
    sky dot     a session starts within the hour
    green dot   the meeting is on now (from preparation time until the session ends)
    green check the meeting is on and you confirmed you joined
    grey        automation paused
"""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from sessionly import APP_NAME
from sessionly.context import AppContext
from sessionly.models import SessionStatus
from sessionly.services.automation import Action, LiveInfo
from sessionly.services.settings import AUTOMATION_PAUSED, TRAY_HINT_SHOWN
from sessionly.ui.icon import app_icon
from sessionly.ui.launch import open_meeting
from sessionly.ui.main_window import MainWindow

log = logging.getLogger(__name__)

TICK_MS = 30_000


def badge_for(info: LiveInfo) -> tuple[str | None, bool]:
    if info.kind == "paused":
        return None, True
    if info.kind == "live":
        return ("joined" if info.status == SessionStatus.JOINED else "live"), False
    if info.kind == "soon":
        return "soon", False
    return None, False


class TrayController(QObject):
    def __init__(self, ctx: AppContext, window: MainWindow) -> None:
        super().__init__(window)
        self.ctx = ctx
        self.window = window
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QSystemTrayIcon(app_icon(), self)
        self._badge: tuple[str | None, bool] | None = None
        self._last_tick: datetime | None = None
        self.info: LiveInfo | None = None

        menu = QMenu()
        self.status_action = menu.addAction("")
        self.status_action.setEnabled(False)
        menu.addSeparator()
        self.joined_action = menu.addAction("✓  I'm in")
        self.joined_action.triggered.connect(self._confirm_joined)
        self.open_link_action = menu.addAction("Open meeting link")
        self.open_link_action.triggered.connect(self._open_link)
        # Recorded voice replies - each plays only when picked here (or via its Ctrl+Alt+N hotkey).
        self.say_menu = menu.addMenu("Say…")
        self.say_menu.aboutToShow.connect(
            lambda: self.window.voice.fill_menu(self.say_menu, self.window.open_voice_replies))
        window.voice.failed.connect(self._voice_failed)
        menu.addSeparator()
        menu.addAction("Open Sessionly", self.window.bring_to_front)
        self.pause_action = QAction("Pause automation", menu, checkable=True)
        self.pause_action.toggled.connect(self._toggle_pause)
        menu.addAction(self.pause_action)
        menu.addSeparator()
        menu.addAction("Quit Sessionly", self.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._activated)
        self.tray.messageClicked.connect(self.window.bring_to_front)

        window.state_changed.connect(self.update_state)
        window.hide_on_close = self.available
        window.state_changed.connect(self._maybe_show_hint)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def start(self) -> None:
        if self.available:
            self.tray.show()
        else:
            log.warning("System tray not available; Sessionly will stop when the window closes.")
        self.timer.start(TICK_MS)
        QTimer.singleShot(1500, self.tick)  # catch up right after start / log-on

    # ---- worker -------------------------------------------------------------------

    def tick(self) -> None:
        now = datetime.now()
        if self._last_tick and (now - self._last_tick).total_seconds() > 5 * 60:
            log.info("Resumed after %.0f minutes without ticks (sleep or busy system)",
                     (now - self._last_tick).total_seconds() / 60)
        self._last_tick = now
        try:
            actions = self.ctx.engine.tick(now)
        except Exception:  # never let one bad tick kill the background loop
            log.exception("Background tick failed")
            self.notify("Sessionly had a problem", "A background check failed. See the log in Settings.")
            return
        for action in actions:
            self._execute(action)
        if actions:
            self.window.dashboard.refresh()
        self.update_state()

    def _execute(self, action: Action) -> None:
        if action.kind == "open_link":
            link = self.ctx.links.current(action.occurrence.meeting_id)
            plan = open_meeting(self.ctx, link) if link else None
            if plan:
                log.info("Opened link for meeting id=%s", action.occurrence.meeting_id)
                self.notify(action.title, f"{action.message} {plan.note}".strip())
            else:
                self.ctx.sessions.transition(action.session.id, SessionStatus.REMINDED, reason="browser_failed")
                self.notify(action.occurrence.meeting_title,
                            "Sessionly couldn't open your browser. Open Sessionly to use the link manually.")
        else:
            self.notify(action.title, action.message)

    def notify(self, title: str, message: str) -> None:
        if self.available and self.tray.supportsMessages():
            self.tray.showMessage(title, message, app_icon(), 10_000)

    # ---- state ----------------------------------------------------------------------

    def update_state(self) -> None:
        info = self.ctx.engine.live(datetime.now())
        self.info = info
        badge = badge_for(info)
        if badge != self._badge:
            self._badge = badge
            self.tray.setIcon(app_icon(*badge))

        occ = info.occurrence
        if info.kind == "paused":
            status = "Automation paused"
        elif info.kind == "live":
            status = f"{occ.meeting_title} · {info.status.label if info.status else 'In progress'}"
        elif info.kind == "soon":
            status = f"{occ.meeting_title} at {occ.start:%H:%M}"
        else:
            nxt = info.next_occurrence
            status = f"Next: {nxt.meeting_title}, {nxt.start:%a %H:%M}" if nxt else "No sessions this week"
        self.status_action.setText(status)
        self.tray.setToolTip(f"{APP_NAME}\n{status}")

        has_link = occ is not None and self.ctx.links.current(occ.meeting_id) is not None
        self.joined_action.setVisible(info.kind == "live" and info.status != SessionStatus.JOINED)
        self.open_link_action.setVisible(info.kind in ("live", "soon") and has_link)
        self.pause_action.blockSignals(True)
        self.pause_action.setChecked(info.kind == "paused")
        self.pause_action.blockSignals(False)

    # ---- menu actions -------------------------------------------------------------

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.window.bring_to_front()

    def _confirm_joined(self) -> None:
        if self.info and self.info.occurrence:
            self.window.dashboard.live.confirm_joined(self.info.occurrence)

    def _open_link(self) -> None:
        if self.info and self.info.occurrence:
            self.window.dashboard.live.open_link(self.info.occurrence)

    def _toggle_pause(self, paused: bool) -> None:
        self.ctx.settings.set(AUTOMATION_PAUSED, paused)
        self.window.settings.load()
        self.window._data_changed()

    def _maybe_show_hint(self) -> None:
        if self.window.isHidden() and self.available and not self.ctx.settings.get(TRAY_HINT_SHOWN, False):
            self.ctx.settings.set(TRAY_HINT_SHOWN, True)
            self.notify("Sessionly is still running",
                        "It's in the hidden icons (^) next to the clock. Right-click it for options or to quit.")

    def _voice_failed(self, message: str) -> None:
        if not self.window.isVisible():  # the window shows its own message box when open
            self.notify("Voice reply", message)

    def quit(self) -> None:
        self.window.voice.shutdown()
        self.window.hide_on_close = False
        self.tray.hide()
        QApplication.quit()

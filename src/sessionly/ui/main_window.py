from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QStackedWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from sessionly import APP_NAME, __version__
from sessionly.context import AppContext
from sessionly.models import Occurrence
from sessionly.services.settings import AUTOMATION_PAUSED
from sessionly.ui.dashboard import Dashboard
from sessionly.ui.dialogs import ProblemDialog
from sessionly.ui.icon import app_icon, icon_pixmap
from sessionly.ui.meetings_page import MeetingsPage
from sessionly.ui.settings_page import SettingsPage
from sessionly.ui.sidebar import GlassSidebar
from sessionly.ui.voice_replies import VoiceRepliesDialog, VoiceReplyController
from sessionly.ui.widgets import GlassBackdrop, Pill, glyph_icon

NAV = [("Dashboard", ""), ("Meetings", ""), ("Settings", "")]


class MainWindow(QMainWindow):
    state_changed = Signal()  # tray should re-evaluate its icon

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.hide_on_close = False  # set by the tray controller when a tray icon exists
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1280, 800)
        self.setMinimumSize(1000, 640)

        self.dashboard = Dashboard(ctx)
        self.meetings = MeetingsPage(ctx)
        self.settings = SettingsPage(ctx)
        # Recorded voice replies: played only when the user presses one (dialog, tray menu, hotkey).
        self.voice = VoiceReplyController(ctx, self)
        self.voice.failed.connect(lambda msg: QMessageBox.warning(self, "Voice reply", msg)
                                  if self.isVisible() else None)
        self.settings.voice_replies_requested.connect(self.open_voice_replies)
        self.pages = QStackedWidget()
        for page in (self.dashboard, self.meetings, self.settings):
            self.pages.addWidget(page)

        # ---- glass sidebar ----
        self.sidebar = GlassSidebar()
        self.sidebar.setFixedWidth(112)
        logo = QLabel()
        logo.setPixmap(icon_pixmap(48))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setToolTip(f"{APP_NAME} {__version__}")
        self.sidebar.layout_.addWidget(logo)
        self.sidebar.layout_.addSpacing(22)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons: list[QToolButton] = []
        for i, (label, glyph) in enumerate(NAV):
            b = QToolButton()
            b.setObjectName("Nav")
            b.setText(label)
            b.setIcon(glyph_icon(glyph, size=26))
            b.setIconSize(QSize(26, 26))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setFixedSize(76, 68)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # keyboard focus ring only, not after a click
            b.setToolTip(f"{label} (Ctrl+{i + 1})")
            b.setAccessibleName(label)
            self.nav_group.addButton(b, i)
            self.nav_buttons.append(b)
            self.sidebar.add_button(b)
        self.sidebar.layout_.addStretch()
        self.auto_pill = Pill()
        self.auto_pill.setToolTip("Background automation status. Change it in Settings or the tray menu.")
        self.sidebar.layout_.addWidget(self.auto_pill, 0, Qt.AlignmentFlag.AlignHCenter)

        content = QFrame()
        content.setObjectName("Content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(2, 2, 2, 2)
        cl.addWidget(self.pages)

        root = GlassBackdrop()  # colour glows that show through the glass sidebar, content frame and cards
        root.setObjectName("Root")
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 12, 12)
        rl.setSpacing(0)
        rl.addWidget(self.sidebar)
        cwrap = QVBoxLayout()
        cwrap.setContentsMargins(0, 10, 0, 0)
        cwrap.addWidget(content)
        rl.addLayout(cwrap, 1)
        self.setCentralWidget(root)

        self.nav_group.idClicked.connect(self.show_page)
        self.nav_buttons[0].setChecked(True)
        self.sidebar.set_active(self.nav_buttons[0], animate=False)

        # ---- wiring ----
        self.meetings.data_changed.connect(self._data_changed)
        self.settings.data_changed.connect(self._data_changed)
        self.dashboard.state_changed.connect(self._data_changed)
        self.dashboard.meeting_selected.connect(self.show_meeting)
        self.dashboard.new_meeting.connect(self._new_meeting)
        self.dashboard.report_problem.connect(self._report_problem)

        for i in range(len(NAV)):
            action = QAction(self)
            action.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            action.triggered.connect(lambda _=False, i=i: self.show_page(i))
            self.addAction(action)
        new_meeting = QAction(self)
        new_meeting.setShortcut(QKeySequence.StandardKey.New)
        new_meeting.triggered.connect(self._new_meeting)
        self.addAction(new_meeting)
        refresh = QAction(self)
        refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh.triggered.connect(self.dashboard.refresh)
        self.addAction(refresh)

        self.update_automation_pill()

    # ---- navigation ------------------------------------------------------------------

    def show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self.sidebar.set_active(self.nav_buttons[index])
        page = self.pages.widget(index)
        if page is self.dashboard:
            self.dashboard.refresh()
        elif page is self.meetings:
            self.meetings.reload()

    def show_meeting(self, meeting_id: int) -> None:
        self.show_page(1)
        self.meetings.select_meeting(meeting_id)

    def bring_to_front(self) -> None:
        self.show()
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.raise_()
        self.activateWindow()
        self.dashboard.refresh()

    def _new_meeting(self) -> None:
        self.show_page(1)
        self.meetings.add_meeting()

    def open_voice_replies(self) -> None:
        self.bring_to_front()
        VoiceRepliesDialog(self.ctx, self.voice, parent=self).exec()
        self.settings.load()

    # ---- state ------------------------------------------------------------------------

    def update_automation_pill(self) -> None:
        if self.ctx.settings.get(AUTOMATION_PAUSED, False):
            self.auto_pill.setText("Paused")
            self.auto_pill.set_kind("muted")
        else:
            self.auto_pill.setText("● Active")
            self.auto_pill.set_kind("ok")

    def _data_changed(self) -> None:
        self.update_automation_pill()
        self.dashboard.refresh()
        self.state_changed.emit()

    def _report_problem(self, occ: Occurrence) -> None:
        link = self.ctx.links.current(occ.meeting_id)
        if link is None:
            self.show_meeting(occ.meeting_id)
            return
        dialog = ProblemDialog(self)
        if dialog.exec():
            outcome = self.ctx.links.report_problem(link.id, dialog.reason)
            QMessageBox.information(self, "Problem recorded", outcome.advice)
            if outcome.needs_replacement:
                self.show_meeting(occ.meeting_id)
                self.meetings.paste_link()
        self._data_changed()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.hide_on_close:
            event.ignore()
            self.hide()
            self.state_changed.emit()
        else:
            event.accept()

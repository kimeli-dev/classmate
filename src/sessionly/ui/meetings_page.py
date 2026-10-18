from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from sessionly.context import AppContext
from sessionly.models import DAY_NAMES, Meeting, ExceptionKind, LinkStatus, Platform
from sessionly.services import ValidationError
from sessionly.ui import local_time, theme
from sessionly.ui.launch import open_meeting
from sessionly.ui.dialogs import (
    MeetingDialog, ExceptionDialog, LinkDialog, LinkHistoryDialog, ProblemDialog, ScheduleDialog, confirm,
)


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.setMaximumHeight(170)
    return t


def _row_buttons(*buttons: QPushButton) -> QHBoxLayout:
    row = QHBoxLayout()
    for b in buttons:
        row.addWidget(b)
    row.addStretch()
    return row


class MeetingsPage(QWidget):
    data_changed = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.meeting: Meeting | None = None

        # ---- left: meeting list ----
        self.list = QListWidget()
        self.list.setAccessibleName("Meetings")
        self.list.currentItemChanged.connect(lambda *_: self._show_selected())
        self.list.itemDoubleClicked.connect(lambda *_: self.edit_meeting())
        add = QPushButton("&Add meeting")
        add.clicked.connect(self.add_meeting)
        self.edit_btn = QPushButton("&Edit")
        self.edit_btn.clicked.connect(self.edit_meeting)
        self.delete_btn = QPushButton("De&lete")
        self.delete_btn.clicked.connect(self.delete_meeting)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.list)
        lv.addLayout(_row_buttons(add, self.edit_btn, self.delete_btn))

        # ---- right: details ----
        self.header = QLabel()
        self.header.setTextFormat(Qt.TextFormat.RichText)
        self.header.setWordWrap(True)

        self.sched_table = _table(["Day", "Time", "Duration", "Prepare", "Active"])
        self.sched_table.doubleClicked.connect(lambda *_: self.edit_schedule())
        add_s = QPushButton("Add &weekly time")
        add_s.clicked.connect(self.add_schedule)
        edit_s = QPushButton("Edit")
        edit_s.clicked.connect(self.edit_schedule)
        del_s = QPushButton("Remove")
        del_s.clicked.connect(self.delete_schedule)
        sched_box = QGroupBox("Weekly schedule")
        sv = QVBoxLayout(sched_box)
        sv.addWidget(self.sched_table)
        sv.addLayout(_row_buttons(add_s, edit_s, del_s))

        self.exc_table = _table(["Change", "Regular date", "New time", "Note"])
        add_e = QPushButton("&Cancel / move / add a session…")
        add_e.clicked.connect(self.add_exception)
        del_e = QPushButton("Remove change")
        del_e.clicked.connect(self.delete_exception)
        exc_box = QGroupBox("Schedule changes")
        ev = QVBoxLayout(exc_box)
        ev.addWidget(self.exc_table)
        ev.addLayout(_row_buttons(add_e, del_e))

        self.link_labels = {k: QLabel() for k in ("url", "platform", "passcode", "status", "source", "updated",
                                                   "worked", "problem")}
        self.link_labels["url"].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.link_labels["url"].setWordWrap(True)
        grid = QGridLayout()
        for row, (key, title) in enumerate([("url", "Link"), ("platform", "Platform"), ("passcode", "Passcode"),
                                            ("status", "Status"),
                                            ("source", "Source"), ("updated", "Last updated"),
                                            ("worked", "Last worked"), ("problem", "Last problem")]):
            grid.addWidget(QLabel(f"<b>{title}</b>"), row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(self.link_labels[key], row, 1)
        grid.setColumnStretch(1, 1)
        self.paste_btn = QPushButton("&Paste new link…")
        self.paste_btn.clicked.connect(self.paste_link)
        self.open_btn = QPushButton("&Open in browser")
        self.open_btn.setToolTip("Opens the link in your default browser. Sessionly cannot tell whether you joined.")
        self.open_btn.clicked.connect(self.open_link)
        self.copy_btn = QPushButton("Cop&y")
        self.copy_btn.clicked.connect(self.copy_link)
        self.worked_btn = QPushButton("It &worked")
        self.worked_btn.setToolTip("Confirm that this link took you to the meeting.")
        self.worked_btn.clicked.connect(self.mark_worked)
        self.problem_btn = QPushButton("&Report a problem…")
        self.problem_btn.clicked.connect(self.report_problem)
        self.passcode_btn = QPushButton("Pass&code…")
        self.passcode_btn.setToolTip("Save the Zoom passcode your host shared. Sessionly hands it to the "
                                     "Zoom app when it joins.")
        self.passcode_btn.clicked.connect(self.edit_passcode)
        self.copy_pass_btn = QPushButton("Copy pass&code")
        self.copy_pass_btn.clicked.connect(self.copy_passcode)
        history = QPushButton("&History…")
        history.clicked.connect(self.show_history)
        link_box = QGroupBox("Meeting link")
        kv = QVBoxLayout(link_box)
        kv.addLayout(grid)
        kv.addLayout(_row_buttons(self.paste_btn, self.open_btn, self.copy_btn, self.worked_btn,
                                  self.problem_btn, history))
        kv.addLayout(_row_buttons(self.passcode_btn, self.copy_pass_btn))

        details = QWidget()
        dv = QVBoxLayout(details)
        dv.addWidget(self.header)
        dv.addWidget(link_box)  # most needed just before a session, so it comes first
        dv.addWidget(sched_box)
        dv.addWidget(exc_box)
        dv.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(details)

        self.empty = QLabel("Add your first meeting with <b>Add meeting</b> (Ctrl+N).")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.right = QWidget()
        rv = QVBoxLayout(self.right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.empty)
        rv.addWidget(scroll)
        self.details_scroll = scroll

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.right)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([260, 740])
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.reload()

    # ---- meeting list -------------------------------------------------------

    def reload(self, select_id: int | None = None) -> None:
        select_id = select_id if select_id is not None else (self.meeting.id if self.meeting else None)
        self.list.blockSignals(True)
        self.list.clear()
        for c in self.ctx.meetings.list():
            item = QListWidgetItem(c.title)
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self.list.addItem(item)
            if c.id == select_id:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._show_selected()

    def select_meeting(self, meeting_id: int) -> None:
        self.reload(select_id=meeting_id)

    def _show_selected(self) -> None:
        item = self.list.currentItem()
        self.meeting = self.ctx.meetings.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
        has = self.meeting is not None
        self.empty.setVisible(not has)
        self.details_scroll.setVisible(has)
        self.edit_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        if has:
            self._render_meeting()

    def _changed(self, select_id: int | None = None) -> None:
        self.reload(select_id)
        self.data_changed.emit()

    def add_meeting(self) -> None:
        dialog = MeetingDialog(self.ctx, parent=self)
        if dialog.exec():
            self._changed(dialog.saved.id)

    def edit_meeting(self) -> None:
        if self.meeting and MeetingDialog(self.ctx, self.meeting, parent=self).exec():
            self._changed()

    def delete_meeting(self) -> None:
        if self.meeting and confirm(self, "Delete meeting",
                                   f"Delete {self.meeting.title}?\n\nIts schedule, schedule changes and saved "
                                   f"meeting links will be deleted too. This cannot be undone."):
            self.ctx.meetings.delete(self.meeting.id)
            self.meeting = None
            self._changed()

    # ---- details -------------------------------------------------------------

    def _render_meeting(self) -> None:
        c = self.meeting
        display = c.preferred_display_name or self.ctx.settings.display_name or "not set"
        flags = []
        if not c.automation_enabled:
            flags.append("automatic actions off")
        if not c.notifications_enabled:
            flags.append("reminders off")
        esc = html.escape
        self.header.setText(
            f"<h2>{esc(c.title)}</h2>"
            f"Host: {esc(c.host_name) or '—'} &nbsp;·&nbsp; Display name: {esc(display)}"
            + (f" &nbsp;·&nbsp; <i>{', '.join(flags)}</i>" if flags else "")
            + (f"<br><small>{esc(c.notes)}</small>" if c.notes else "")
        )

        self.schedules = self.ctx.schedules.for_meeting(c.id)
        self.sched_table.setRowCount(len(self.schedules))
        for row, s in enumerate(self.schedules):
            values = [DAY_NAMES[s.day_of_week], f"{s.start_time:%H:%M}–{s.end_time:%H:%M}",
                      f"{s.duration_minutes} min", f"{s.preparation_minutes} min", "Yes" if s.enabled else "No"]
            for col, v in enumerate(values):
                self.sched_table.setItem(row, col, QTableWidgetItem(v))

        self.exceptions = self.ctx.schedules.exceptions_for_meeting(c.id)
        self.exc_table.setRowCount(len(self.exceptions))
        labels = {ExceptionKind.CANCELLED: "Cancelled", ExceptionKind.RESCHEDULED: "Moved",
                  ExceptionKind.EXTRA: "Extra session"}
        for row, e in enumerate(self.exceptions):
            values = [labels[e.kind], f"{e.original_date:%a %d %b %Y}" if e.original_date else "—",
                      f"{e.new_start:%a %d %b %Y %H:%M}" if e.new_start else "—", e.note]
            for col, v in enumerate(values):
                self.exc_table.setItem(row, col, QTableWidgetItem(v))

        link = self.ctx.links.current(c.id)
        self.link = link
        L = self.link_labels
        if link is None:
            L["url"].setTextFormat(Qt.TextFormat.PlainText)
            L["url"].setText("No link saved yet.")
            for k in ("platform", "passcode", "status", "source", "updated", "worked", "problem"):
                L[k].setText("—")
        else:
            L["url"].setTextFormat(Qt.TextFormat.PlainText)
            L["url"].setText(link.url)
            L["platform"].setText(link.platform.label)
            L["passcode"].setText("Saved (hidden)" if link.passcode else
                                  ("Not needed for this platform" if link.platform != Platform.ZOOM else "None saved"))
            colour = {LinkStatus.WORKED: theme.OK, LinkStatus.FAILED: theme.DANGER}.get(link.status, "")
            L["status"].setText(f"<span style='color:{colour}'>{link.status.label}</span>" if colour
                                else link.status.label)
            L["source"].setText(link.source.capitalize())
            L["updated"].setText(local_time(link.updated_at))
            L["worked"].setText(local_time(link.last_success_at, "never confirmed"))
            L["problem"].setText(f"{link.failure_reason.label} ({local_time(link.last_failure_at)})"
                                 if link.failure_reason else "—")
        for b in (self.open_btn, self.copy_btn, self.worked_btn, self.problem_btn):
            b.setEnabled(link is not None)
        is_zoom = link is not None and link.platform == Platform.ZOOM
        self.passcode_btn.setVisible(is_zoom)
        self.copy_pass_btn.setVisible(is_zoom)
        self.copy_pass_btn.setEnabled(is_zoom and bool(link.passcode))
        self.paste_btn.setText("&Replace link…" if link else "&Paste link…")

    def _selected_row(self, table: QTableWidget) -> int | None:
        rows = table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def add_schedule(self) -> None:
        if ScheduleDialog(self.ctx, self.meeting.id, parent=self).exec():
            self._changed()

    def edit_schedule(self) -> None:
        row = self._selected_row(self.sched_table)
        if row is not None and ScheduleDialog(self.ctx, self.meeting.id, self.schedules[row], parent=self).exec():
            self._changed()

    def delete_schedule(self) -> None:
        row = self._selected_row(self.sched_table)
        if row is not None and confirm(self, "Remove weekly time",
                                       f"Remove {self.schedules[row].describe()}?\n"
                                       "Any cancellations or moves recorded for it are removed too."):
            self.ctx.schedules.delete(self.schedules[row].id)
            self._changed()

    def add_exception(self) -> None:
        if ExceptionDialog(self.ctx, self.meeting.id, parent=self).exec():
            self._changed()

    def delete_exception(self) -> None:
        row = self._selected_row(self.exc_table)
        if row is not None and confirm(self, "Remove change", "Remove this schedule change?"):
            self.ctx.schedules.delete_exception(self.exceptions[row].id)
            self._changed()

    # ---- meeting link ----------------------------------------------------------

    def paste_link(self) -> None:
        if LinkDialog(self.ctx, self.meeting, replacing=self.link, parent=self).exec():
            self._changed()

    def open_link(self) -> None:
        if self.link and not open_meeting(self.ctx, self.link):
            QMessageBox.warning(self, "Couldn't open the meeting",
                                "Sessionly couldn't open your browser or the Zoom app. Copy the link instead.")

    def copy_passcode(self) -> None:
        if self.link and self.link.passcode:
            QGuiApplication.clipboard().setText(self.link.passcode)

    def edit_passcode(self) -> None:
        if not self.link:
            return
        text, ok = QInputDialog.getText(self, "Zoom passcode",
                                        f"Passcode for {self.meeting.title} (leave empty to remove):",
                                        QLineEdit.EchoMode.Password, self.link.passcode)
        if not ok:
            return
        try:
            self.ctx.links.set_passcode(self.link.id, text)
        except ValidationError as exc:
            QMessageBox.warning(self, "Check the passcode", str(exc))
            return
        self._changed()

    def copy_link(self) -> None:
        if self.link:
            QGuiApplication.clipboard().setText(self.link.url)

    def mark_worked(self) -> None:
        if self.link:
            self.ctx.links.mark_worked(self.link.id)
            self._changed()

    def report_problem(self) -> None:
        if not self.link:
            return
        dialog = ProblemDialog(self)
        if not dialog.exec():
            return
        outcome = self.ctx.links.report_problem(self.link.id, dialog.reason)
        self._changed()
        if outcome.needs_replacement:
            answer = QMessageBox.question(self, "Replace the link?",
                                          outcome.advice + "\n\nDo you have the new link now?")
            if answer == QMessageBox.StandardButton.Yes:
                self.paste_link()
        else:
            QMessageBox.information(self, "Problem recorded", outcome.advice)

    def show_history(self) -> None:
        LinkHistoryDialog(self.ctx, self.meeting, parent=self).exec()
        self._changed()

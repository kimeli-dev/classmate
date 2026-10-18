"""Dialogs for editing meetings, weekly times, schedule changes and meeting links.

Each dialog saves through a service inside ``accept()`` so a validation problem keeps the
dialog open with the user's input intact.
"""

from __future__ import annotations

import html
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QDateTime, QTime
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem, QTimeEdit, QToolButton, QVBoxLayout, QWidget,
)

from sessionly.context import AppContext
from sessionly.models import (
    DAY_NAMES, DAY_PRESETS, DAY_SHORT, ExceptionKind, FailureReason, Meeting, MeetingLink, Platform, Schedule,
    ScheduleException,
)
from sessionly.services import ValidationError
from sessionly.services.link_validation import check_meeting_url
from sessionly.services.settings import AUTO_OPEN_LINKS
from sessionly.ui import local_time, theme


def _buttons(dialog: QDialog, ok_text: str = "Save") -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    box.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Muted")
    return label


def _link_feedback(label: QLabel, text: str) -> bool:
    """Show live feedback for a pasted meeting link; returns whether it is usable."""
    check = check_meeting_url(text)
    if not check.ok:
        label.setStyleSheet(f"color: {theme.DANGER};")
        label.setText(check.error)
    elif check.warnings:
        label.setStyleSheet(f"color: {theme.WARN};")
        label.setText(f"{check.platform.label}. " + " ".join(check.warnings))
    else:
        label.setStyleSheet(f"color: {theme.OK};")
        label.setText(f"Looks like a {check.platform.label} link.")
    return check.ok


def _passcode_field() -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)  # visible while typing, hidden after
    field.setPlaceholderText("Optional - the passcode your host shared")
    field.setToolTip("Sessionly hands this to the Zoom app when it joins, so you aren't asked for it.")
    return field


def _is_zoom(text: str) -> bool:
    check = check_meeting_url(text)
    return check.ok and check.platform == Platform.ZOOM


def _confirm_shared_link(dialog: QWidget, ctx: AppContext, url: str, meeting_id: int | None, title: str) -> bool:
    others = ctx.links.other_meetings_using(url, meeting_id or -1)
    if not others:
        return True
    names = ", ".join(name for _, name in others)
    answer = QMessageBox.question(
        dialog, "Is this the right meeting?",
        f"This exact link is already the current link for: {names}.\n\n"
        f"Some hosts reuse one link, but it may also have been pasted into the wrong meeting. "
        f"Save it for {title} as well?",
    )
    return answer == QMessageBox.StandardButton.Yes


class ScheduleFields:
    """Day / start / duration / prepare inputs shared by the meeting and weekly-time dialogs.

    With ``multi`` the day selector is shown: toggle any days (Mo-Su) or use a
    quick pick such as Weekdays. Each ticked day becomes one weekly time with the same start and
    length. Without it, a single day is chosen (used when editing one existing weekly time)."""

    def __init__(self, multi: bool = False) -> None:
        self.multi = multi
        self.day_buttons: list[QToolButton] = []
        if multi:
            self.day = QWidget()
            row = QHBoxLayout(self.day)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            for i, short in enumerate(DAY_SHORT):
                b = QToolButton()
                b.setObjectName("DayToggle")
                b.setText(short)
                b.setCheckable(True)
                b.setToolTip(DAY_NAMES[i])
                b.setAccessibleName(DAY_NAMES[i])
                self.day_buttons.append(b)
                row.addWidget(b)
            self.presets = QComboBox()
            self.presets.addItem("Quick pick…")
            for label, days in DAY_PRESETS:
                self.presets.addItem(label, days)
            self.presets.activated.connect(self._apply_preset)
            row.addSpacing(6)
            row.addWidget(self.presets)
            row.addStretch()
        else:
            self.day = QComboBox()
            self.day.addItems(DAY_NAMES)
        self.start = QTimeEdit()
        self.start.setDisplayFormat("HH:mm")
        self.duration = QSpinBox()
        self.duration.setRange(1, 720)
        self.duration.setSingleStep(15)
        self.duration.setSuffix(" min")
        self.prep = QSpinBox()
        self.prep.setRange(0, 120)
        self.prep.setSuffix(" min before")
        self.conflicts = QLabel()
        self.conflicts.setWordWrap(True)
        self.conflicts.setStyleSheet(f"color: {theme.WARN};")

    def _apply_preset(self, index: int) -> None:
        days = self.presets.itemData(index)
        if days is not None:
            self.set_days(days)
        self.presets.setCurrentIndex(0)

    def set_days(self, days) -> None:
        if self.multi:
            for i, b in enumerate(self.day_buttons):
                b.setChecked(i in days)
        else:
            self.day.setCurrentIndex(days[0])

    def days(self) -> tuple[int, ...]:
        if self.multi:
            return tuple(i for i, b in enumerate(self.day_buttons) if b.isChecked())
        return (self.day.currentIndex(),)

    def add_rows(self, form: QFormLayout) -> None:
        form.addRow("Days" if self.multi else "&Day", self.day)
        form.addRow("&Starts at", self.start)
        form.addRow("D&uration", self.duration)
        form.addRow("&Prepare", self.prep)

    def check_days(self, dialog: QWidget) -> bool:
        if self.days():
            return True
        QMessageBox.warning(dialog, "Pick the days", "Tick at least one day of the week.")
        return False

    def load(self, s: Schedule) -> None:
        self.set_days((s.day_of_week,))
        self.start.setTime(QTime(s.start_time.hour, s.start_time.minute))
        self.duration.setValue(s.duration_minutes)
        self.prep.setValue(s.preparation_minutes)

    def schedules(self, schedule_id: int | None, meeting_id: int | None, enabled: bool = True) -> list[Schedule]:
        """One weekly time per selected day, all with the same start and length."""
        return [Schedule(
            id=schedule_id, meeting_id=meeting_id, day_of_week=day,
            start_time=self.start.time().toPython().replace(second=0),
            duration_minutes=self.duration.value(), preparation_minutes=self.prep.value(), enabled=enabled,
        ) for day in self.days()]

    def schedule(self, schedule_id: int | None, meeting_id: int | None, enabled: bool = True) -> Schedule:
        return self.schedules(schedule_id, meeting_id, enabled)[0]

    def watch_conflicts(self, ctx: AppContext, exclude_id: int | None = None) -> None:
        self._ctx, self._exclude = ctx, exclude_id
        signals = [b.toggled for b in self.day_buttons] if self.multi else [self.day.currentIndexChanged]
        for signal in signals + [self.start.timeChanged, self.duration.valueChanged]:
            signal.connect(self._update_conflicts)
        self._update_conflicts()

    def clashes(self) -> list[str]:
        found: list[str] = []
        for day in self.days():
            for clash in self._ctx.schedules.weekly_conflicts(
                    day, self.start.time().toPython(), self.duration.value(), self._exclude):
                if clash not in found:
                    found.append(clash)
        return found

    def _update_conflicts(self) -> None:
        clashes = self.clashes()
        self.conflicts.setText("Overlaps with: " + "; ".join(clashes) if clashes else "")

    def confirm_overlap(self, dialog: QWidget) -> bool:
        clashes = self.clashes()
        if not clashes:
            return True
        answer = QMessageBox.question(
            dialog, "Sessions overlap",
            "This time overlaps with:\n\n• " + "\n• ".join(clashes) +
            "\n\nSessionly will show a warning on the dashboard and will not choose between them for you. "
            "Save anyway?",
        )
        return answer == QMessageBox.StandardButton.Yes


class MeetingDialog(QDialog):
    """Edit a meeting. When adding, it also takes the weekly schedule and meeting link so the
    meeting is ready to be joined automatically straight away."""

    def __init__(self, ctx: AppContext, meeting: Meeting | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.meeting = meeting
        self.saved: Meeting | None = None
        self.adding = meeting is None
        self.setWindowTitle("Edit meeting" if meeting else "Add meeting")
        self.setMinimumWidth(580)

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Weekly team sync, Software Testing, Spanish class")
        self.code = QLineEdit()
        self.code.setPlaceholderText("Optional, e.g. SWE 320 or TEAM")
        self.host = QLineEdit()
        default_name = ctx.settings.display_name or "not set"
        self.display_name = QLineEdit()
        self.display_name.setPlaceholderText(f"Use my default name ({default_name})")
        self.automation = QCheckBox("Allow automatic actions for this meeting")
        self.automation.setToolTip("Reminders and automatic link opening. Turning this off keeps the meeting in your schedule.")
        self.notifications = QCheckBox("Show reminders for this meeting")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Anything useful, e.g. 'Link is posted in the group chat every Monday'")
        self.notes.setFixedHeight(70)

        form = QFormLayout()
        form.addRow("Meeting &name *", self.name)
        form.addRow("Short &code", self.code)
        form.addRow("&Host", self.host)
        form.addRow("&Display name", self.display_name)
        form.addRow("", self.automation)
        form.addRow("", self.notifications)
        form.addRow("N&otes", self.notes)

        layout = QVBoxLayout(self)
        layout.addLayout(form)

        if self.adding:
            self.automation.setText("&Join automatically - open the meeting link when it starts")
            self.automation.setToolTip("Sessionly opens the link when each session is about to start. "
                                       "Confirm with \"I'm in\" once you're in the meeting.")

            self.has_time = QGroupBox("Schedule")
            self.has_time.setCheckable(True)
            self.has_time.setChecked(True)
            self.times = ScheduleFields(multi=True)
            self.times.load(Schedule(id=None, meeting_id=None, day_of_week=date.today().weekday(),
                                     start_time=time(9, 0), duration_minutes=60, preparation_minutes=5))
            self.times.watch_conflicts(ctx)
            tform = QFormLayout(self.has_time)
            self.times.add_rows(tform)
            tform.addRow("", self.times.conflicts)
            tform.addRow("", _hint("Each ticked day repeats weekly at this time (your local time)."))
            layout.addWidget(self.has_time)

            link_box = QGroupBox("Meeting link")
            self.url = QLineEdit()
            self.url.setPlaceholderText("https://meet.google.com/abc-defg-hij  or  https://zoom.us/j/…")
            self.url_feedback = QLabel()
            self.url_feedback.setWordWrap(True)
            lform = QFormLayout(link_box)
            lform.addRow("Lin&k", self.url)
            lform.addRow("", self.url_feedback)
            self.passcode = _passcode_field()
            lform.addRow("Zoom pass&code", self.passcode)
            self.link_form = lform
            self.url.textChanged.connect(self._validate_link)
            self._validate_link()
            layout.addWidget(link_box)

        layout.addWidget(_buttons(self))

        c = meeting or Meeting(id=None, name="")
        self.name.setText(c.name)
        self.code.setText(c.short_code)
        self.host.setText(c.host_name)
        self.display_name.setText(c.preferred_display_name or "")
        self.automation.setChecked(c.automation_enabled)
        self.notifications.setChecked(c.notifications_enabled)
        self.notes.setPlainText(c.notes)

    def _validate_link(self) -> None:
        if self.url.text().strip():
            _link_feedback(self.url_feedback, self.url.text())
        else:
            self.url_feedback.setText("")
        self.link_form.setRowVisible(self.passcode, _is_zoom(self.url.text()))

    def accept(self) -> None:
        if self.adding:
            self._accept_new()
            return
        c = Meeting(
            id=self.meeting.id if self.meeting else None,
            name=self.name.text(),
            short_code=self.code.text(),
            host_name=self.host.text(),
            preferred_display_name=self.display_name.text(),
            automation_enabled=self.automation.isChecked(),
            notifications_enabled=self.notifications.isChecked(),
            notes=self.notes.toPlainText().strip(),
        )
        try:
            self.saved = self.ctx.meetings.update(c) if c.id else self.ctx.meetings.create(c)
        except ValidationError as exc:
            QMessageBox.warning(self, "Check the meeting details", str(exc))
            return
        super().accept()

    def _accept_new(self) -> None:
        c = Meeting(
            id=None, name=self.name.text(), short_code=self.code.text(), host_name=self.host.text(),
            preferred_display_name=self.display_name.text(), automation_enabled=self.automation.isChecked(),
            notifications_enabled=self.notifications.isChecked(), notes=self.notes.toPlainText().strip(),
        )
        url = self.url.text().strip()
        check = check_meeting_url(url) if url else None
        if check and not check.ok:
            QMessageBox.warning(self, "Check the link", check.error)
            return
        if url and not _confirm_shared_link(self, self.ctx, url, None, c.name.strip() or "this meeting"):
            return
        if self.has_time.isChecked() and not (self.times.check_days(self) and self.times.confirm_overlap(self)):
            return

        # Meeting, weekly time and link are saved together: if a later step fails, undo the meeting
        # so the user can fix the input without ending up with a half-created duplicate.
        try:
            saved = self.ctx.meetings.create(c)
        except ValidationError as exc:
            QMessageBox.warning(self, "Check the meeting details", str(exc))
            return
        try:
            if self.has_time.isChecked():
                for s in self.times.schedules(None, saved.id):
                    self.ctx.schedules.add(s)
            if url:
                self.ctx.links.set_current(saved.id, url, source="manual",
                                           passcode=self.passcode.text() if _is_zoom(url) else None)
        except ValidationError as exc:
            self.ctx.meetings.delete(saved.id)
            QMessageBox.warning(self, "Check the schedule and link", str(exc))
            return
        self.saved = saved

        if c.automation_enabled and url and self.has_time.isChecked():
            if not self.ctx.settings.get(AUTO_OPEN_LINKS, False):
                self.ctx.settings.set(AUTO_OPEN_LINKS, True)
                QMessageBox.information(
                    self, "Automatic joining is on",
                    f"Sessionly will open the {saved.title} link when each session starts.\n\n"
                    "This also turned on \"Open links automatically\" in Settings, so your other meetings "
                    "that allow automatic actions will open their links too. You can turn it off there.")
        super().accept()


class ScheduleDialog(QDialog):
    """Adding lets you tick any days; editing changes only the one weekly time that was selected,
    so a single day can still be adjusted."""

    def __init__(self, ctx: AppContext, meeting_id: int, schedule: Schedule | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.meeting_id = meeting_id
        self.schedule = schedule
        self.setWindowTitle("Edit weekly time" if schedule else "Add weekly time")

        self.fields = ScheduleFields(multi=schedule is None)
        self.day, self.start, self.duration, self.prep = (self.fields.day, self.fields.start,
                                                          self.fields.duration, self.fields.prep)
        self.conflicts = self.fields.conflicts
        self.enabled = QCheckBox("Active")

        form = QFormLayout()
        self.fields.add_rows(form)
        form.addRow("", self.enabled)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(_hint("Every ticked day gets the same time. Times are in your computer's local time."
                               if schedule is None else "Times are in your computer's local time."))
        layout.addWidget(self.conflicts)
        layout.addWidget(_buttons(self))

        s = schedule or Schedule(id=None, meeting_id=meeting_id, day_of_week=date.today().weekday(),
                                 start_time=time(9, 0), duration_minutes=60, preparation_minutes=5)
        self.fields.load(s)
        self.enabled.setChecked(s.enabled)
        self.fields.watch_conflicts(ctx, schedule.id if schedule else None)

    def accept(self) -> None:
        enabled = self.enabled.isChecked()
        if not self.fields.check_days(self) or (enabled and not self.fields.confirm_overlap(self)):
            return
        try:
            if self.schedule:
                self.ctx.schedules.update(self.fields.schedule(self.schedule.id, self.meeting_id, enabled))
            else:
                # One weekly time per ticked day, saved together or not at all.
                with self.ctx.db.transaction():
                    for s in self.fields.schedules(None, self.meeting_id, enabled):
                        self.ctx.schedules.add(s)
        except ValidationError as exc:
            QMessageBox.warning(self, "Check the time", str(exc))
            return
        super().accept()


def _next_weekday(day_of_week: int, from_day: date | None = None) -> date:
    d = from_day or date.today()
    return d + timedelta(days=(day_of_week - d.weekday()) % 7)


class ExceptionDialog(QDialog):
    """Cancel one session, move one session, or add a one-off extra session."""

    def __init__(self, ctx: AppContext, meeting_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.meeting_id = meeting_id
        self.schedules = ctx.schedules.for_meeting(meeting_id)
        self.setWindowTitle("Change the schedule")
        self.setMinimumWidth(440)

        self.kind_group = QButtonGroup(self)
        kinds = QHBoxLayout()
        for i, (kind, text) in enumerate([(ExceptionKind.CANCELLED, "&Cancel a session"),
                                          (ExceptionKind.RESCHEDULED, "&Move a session"),
                                          (ExceptionKind.EXTRA, "&Extra session")]):
            rb = QRadioButton(text)
            rb.setProperty("kind", kind.value)
            self.kind_group.addButton(rb, i)
            kinds.addWidget(rb)

        self.regular = QComboBox()
        for s in self.schedules:
            self.regular.addItem(s.describe(), s.id)
        self.original_date = QDateEdit()
        self.original_date.setCalendarPopup(True)
        self.original_date.setDisplayFormat("ddd dd MMM yyyy")
        self.new_start = QDateTimeEdit()
        self.new_start.setCalendarPopup(True)
        self.new_start.setDisplayFormat("ddd dd MMM yyyy  HH:mm")
        self.duration = QSpinBox()
        self.duration.setRange(1, 720)
        self.duration.setSingleStep(15)
        self.duration.setSuffix(" min")
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional, e.g. 'Host travelling'")

        self.form = QFormLayout()
        self.form.addRow("Regular &session", self.regular)
        self.form.addRow("On &date", self.original_date)
        self.form.addRow("&New date and time", self.new_start)
        self.form.addRow("D&uration", self.duration)
        self.form.addRow("N&ote", self.note)

        layout = QVBoxLayout(self)
        layout.addLayout(kinds)
        layout.addLayout(self.form)
        layout.addWidget(_buttons(self))

        tomorrow = datetime.combine(date.today() + timedelta(days=1), time(8, 0))
        self.new_start.setDateTime(QDateTime(QDate(tomorrow.year, tomorrow.month, tomorrow.day), QTime(8, 0)))
        self.duration.setValue(60)
        self.regular.currentIndexChanged.connect(self._sync_regular)
        self.kind_group.idToggled.connect(lambda *_: self._sync_kind())
        self.kind_group.button(0 if self.schedules else 2).setChecked(True)
        if not self.schedules:
            self.kind_group.button(0).setEnabled(False)
            self.kind_group.button(1).setEnabled(False)
        self._sync_regular()
        self._sync_kind()

    def _kind(self) -> ExceptionKind:
        return ExceptionKind(self.kind_group.checkedButton().property("kind"))

    def _selected_schedule(self) -> Schedule | None:
        sid = self.regular.currentData()
        return next((s for s in self.schedules if s.id == sid), None)

    def _sync_regular(self) -> None:
        s = self._selected_schedule()
        if s:
            d = _next_weekday(s.day_of_week)
            self.original_date.setDate(QDate(d.year, d.month, d.day))
            self.duration.setValue(s.duration_minutes)

    def _sync_kind(self) -> None:
        kind = self._kind()
        regular = kind != ExceptionKind.EXTRA
        for widget, visible in ((self.regular, regular), (self.original_date, regular),
                                (self.new_start, kind != ExceptionKind.CANCELLED),
                                (self.duration, kind != ExceptionKind.CANCELLED)):
            self.form.setRowVisible(widget, visible)
        self.adjustSize()

    def accept(self) -> None:
        kind = self._kind()
        s = self._selected_schedule()
        e = ScheduleException(
            id=None, meeting_id=self.meeting_id, kind=kind,
            schedule_id=s.id if s and kind != ExceptionKind.EXTRA else None,
            original_date=self.original_date.date().toPython() if kind != ExceptionKind.EXTRA else None,
            new_start=self.new_start.dateTime().toPython().replace(second=0, microsecond=0)
            if kind != ExceptionKind.CANCELLED else None,
            new_duration_minutes=self.duration.value() if kind != ExceptionKind.CANCELLED else None,
            note=self.note.text(),
        )
        try:
            self.ctx.schedules.add_exception(e)
        except ValidationError as exc:
            QMessageBox.warning(self, "Check the change", str(exc))
            return
        super().accept()


class LinkDialog(QDialog):
    """Paste a new or replacement meeting link for one meeting."""

    def __init__(self, ctx: AppContext, meeting: Meeting, replacing: MeetingLink | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.meeting = meeting
        self.setWindowTitle(f"Meeting link for {meeting.title}")
        self.setMinimumWidth(520)

        title = html.escape(meeting.title)
        intro = (f"Paste the latest link for <b>{title}</b>." if not replacing else
                 f"Paste the replacement link for <b>{title}</b>. The old link stays in the history.")
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://meet.google.com/abc-defg-hij  or  https://zoom.us/j/…")
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Optional, e.g. 'Same link every week'")

        form = QFormLayout()
        form.addRow("&Link", self.url)
        form.addRow("", self.feedback)
        self.passcode = _passcode_field()
        form.addRow("Zoom pass&code", self.passcode)
        form.addRow("&Notes", self.notes)
        self.form = form
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(intro))
        layout.addLayout(form)
        layout.addWidget(_hint("Sessionly checks that the link looks right. That does not prove the meeting "
                               "exists - mark the link as working once you have used it."))
        self.box = _buttons(self)
        layout.addWidget(self.box)

        self.url.textChanged.connect(self._validate)
        self._validate()

    def _validate(self) -> None:
        text = self.url.text()
        self.form.setRowVisible(self.passcode, _is_zoom(text))
        ok_button = self.box.button(QDialogButtonBox.StandardButton.Ok)
        if not text.strip():
            self.feedback.setText("")
            ok_button.setEnabled(False)
            return
        ok_button.setEnabled(_link_feedback(self.feedback, text))

    def accept(self) -> None:
        if not _confirm_shared_link(self, self.ctx, self.url.text(), self.meeting.id, self.meeting.title):
            return
        try:
            self.ctx.links.set_current(self.meeting.id, self.url.text(), source="manual", notes=self.notes.text(),
                                       passcode=self.passcode.text() if _is_zoom(self.url.text()) else None)
        except ValidationError as exc:
            QMessageBox.warning(self, "Check the link", str(exc))
            return
        super().accept()


class ProblemDialog(QDialog):
    """Ask what went wrong so a host who hasn't started yet isn't mistaken for a broken link."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("What happened?")
        self.group = QButtonGroup(self)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("What did you see when you tried the link?"))
        for i, reason in enumerate(FailureReason):
            rb = QRadioButton(reason.label)
            rb.setProperty("reason", reason.value)
            self.group.addButton(rb, i)
            layout.addWidget(rb)
        self.group.button(0).setChecked(True)
        layout.addWidget(_buttons(self, ok_text="Record problem"))

    @property
    def reason(self) -> FailureReason:
        return FailureReason(self.group.checkedButton().property("reason"))


class LinkHistoryDialog(QDialog):
    def __init__(self, ctx: AppContext, meeting: Meeting, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.meeting = meeting
        self.setWindowTitle(f"Link history - {meeting.title}")
        self.resize(820, 340)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Link", "Platform", "Status", "Added", "Last worked", "Current"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)

        restore = QPushButton("&Make current")
        restore.clicked.connect(self._restore)
        delete = QPushButton("&Delete from history")
        delete.clicked.connect(self._delete)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(restore)
        buttons.addWidget(delete)
        buttons.addStretch()
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self._load()

    def _load(self) -> None:
        self.links = self.ctx.links.history(self.meeting.id)
        self.table.setRowCount(len(self.links))
        for row, link in enumerate(self.links):
            values = [link.url, link.platform.label, link.status.label, local_time(link.created_at),
                      local_time(link.last_success_at), "Yes" if link.is_current else ""]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))

    def _selected(self) -> MeetingLink | None:
        rows = self.table.selectionModel().selectedRows()
        return self.links[rows[0].row()] if rows else None

    def _restore(self) -> None:
        if link := self._selected():
            self.ctx.links.make_current(link.id)
            self._load()

    def _delete(self) -> None:
        link = self._selected()
        if not link:
            return
        if QMessageBox.question(self, "Delete link", "Remove this old link from the history?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            self.ctx.links.delete_from_history(link.id)
        except ValidationError as exc:
            QMessageBox.information(self, "Cannot delete", str(exc))
        self._load()


def confirm(parent: QWidget, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text) == QMessageBox.StandardButton.Yes

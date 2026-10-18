"""First-run setup: display name, first meeting and its weekly time, and its meeting link.

Every step after the name can be skipped; advanced features are configured later.
"""

from __future__ import annotations

from datetime import date, time

from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget, QWizard, QWizardPage,
)

from sessionly.context import AppContext
from sessionly.models import Meeting, Schedule
from sessionly.services import ValidationError
from sessionly.services.link_validation import check_meeting_url
from sessionly.services.settings import SETUP_COMPLETED
from sessionly.ui.dialogs import ScheduleFields


class _NamePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Welcome to Sessionly")
        self.setSubTitle("Sessionly keeps your meetings, their schedules and links in one place.")
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Jane Doe")
        form = QFormLayout(self)
        form.addRow("Your &display name", self.name)
        note = QLabel("This is the name you use in online meetings. It is stored only on this computer.")
        note.setWordWrap(True)
        form.addRow("", note)


class _MeetingPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Your first meeting")
        self.setSubTitle("Add one meeting now, or skip and add meetings later.")
        self.skip = QCheckBox("&Skip - I'll add meetings later")
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Weekly team sync, Software Testing, Spanish class")
        self.code = QLineEdit()
        self.code.setPlaceholderText("Optional, e.g. SWE 320 or TEAM")
        self.times = ScheduleFields(multi=True)
        self.times.load(Schedule(id=None, meeting_id=None, day_of_week=date.today().weekday(),
                                 start_time=time(9, 0), duration_minutes=60, preparation_minutes=5))
        self.start, self.duration, self.prep = self.times.start, self.times.duration, self.times.prep

        self.fields = QWidget()
        form = QFormLayout(self.fields)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Meeting &name", self.name)
        form.addRow("Short &code", self.code)
        self.times.add_rows(form)
        hint = QLabel("Tick every day it happens - each gets the same start time. Use Quick pick for "
                      "common patterns like Weekdays or Mon & Wed.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        form.addRow("", hint)
        layout = QVBoxLayout(self)
        layout.addWidget(self.skip)
        layout.addWidget(self.fields)
        self.skip.toggled.connect(lambda on: self.fields.setEnabled(not on))

    def validatePage(self) -> bool:
        if not self.skip.isChecked() and not self.name.text().strip():
            QMessageBox.information(self, "Meeting name", "Enter a meeting name, or tick Skip.")
            return False
        return self.skip.isChecked() or self.times.check_days(self)


class _LinkPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Meeting link")
        self.setSubTitle("Paste the meeting's current Zoom or Google Meet link, if you have it. You can skip this.")
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://meet.google.com/abc-defg-hij")
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        form = QFormLayout(self)
        form.addRow("&Link", self.url)
        form.addRow("", self.feedback)
        self.url.textChanged.connect(self._check)

    def _check(self) -> None:
        text = self.url.text().strip()
        if not text:
            self.feedback.setText("")
            return
        check = check_meeting_url(text)
        self.feedback.setText(check.error if not check.ok else
                              f"Looks like a {check.platform.label} link. " + " ".join(check.warnings))

    def validatePage(self) -> bool:
        text = self.url.text().strip()
        if text and not check_meeting_url(text).ok:
            QMessageBox.information(self, "Meeting link", "Fix the link or clear the box to skip this step.")
            return False
        return True


class SetupWizard(QWizard):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Sessionly setup")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.name_page = _NamePage()
        self.meeting_page = _MeetingPage()
        self.link_page = _LinkPage()
        self.addPage(self.name_page)
        self.addPage(self.meeting_page)
        self.addPage(self.link_page)
        self.created_meeting_id: int | None = None

    def nextId(self) -> int:
        # No meeting -> no link to ask for.
        if self.currentPage() is self.meeting_page and self.meeting_page.skip.isChecked():
            return -1
        return super().nextId()

    def accept(self) -> None:
        try:
            self._save()
        except ValidationError as exc:
            QMessageBox.warning(self, "Setup", str(exc))
            return
        super().accept()

    def _save(self) -> None:
        ctx = self.ctx
        ctx.settings.display_name = self.name_page.name.text()
        p = self.meeting_page
        if not p.skip.isChecked():
            with ctx.db.transaction():
                meeting = ctx.meetings.create(Meeting(id=None, name=p.name.text(), short_code=p.code.text()))
                for s in p.times.schedules(None, meeting.id):
                    ctx.schedules.add(s)
                if self.link_page.url.text().strip():
                    ctx.links.set_current(meeting.id, self.link_page.url.text())
            self.created_meeting_id = meeting.id
        ctx.settings.set(SETUP_COMPLETED, True)

"""UI tests run offscreen (see conftest). Message boxes are stubbed so nothing blocks."""

from datetime import date, datetime, time, timedelta

import pytest
from PySide6.QtCore import QTime
from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

from sessionly.config import AppConfig
from sessionly.context import AppContext
from sessionly.models import DAY_PRESETS, Occurrence, Meeting, ExceptionKind, Schedule
from sessionly.services.settings import AUTO_OPEN_LINKS
from sessionly.ui.dashboard import class_state
from sessionly.ui.dialogs import MeetingDialog, ExceptionDialog, LinkDialog, ScheduleDialog
from sessionly.ui.main_window import MainWindow
from sessionly.ui.setup_wizard import SetupWizard


@pytest.fixture
def ctx(db, tmp_path):
    return AppContext.create(AppConfig(data_dir=tmp_path), db)


@pytest.fixture
def boxes(monkeypatch):
    """Record message boxes instead of showing them; questions answer Yes."""
    shown = []
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, _n=name, **k: shown.append((_n, a[2])))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: shown.append(("question", a[2])) or QMessageBox.StandardButton.Yes)
    return shown


@pytest.fixture
def meeting(ctx):
    return ctx.meetings.create(Meeting(id=None, name="Software Testing", short_code="SWE 320"))


def test_main_window_shows_meeting_and_todays_session(qtbot, ctx, meeting):
    ctx.schedules.add(Schedule(id=None, meeting_id=meeting.id, day_of_week=date.today().weekday(),
                               start_time=time(23, 0), duration_minutes=30))
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    assert [b.text() for b in window.nav_buttons] == ["Dashboard", "Meetings", "Settings"]
    assert window.meetings.list.count() == 1
    assert "SWE 320 - Software Testing" in window.dashboard.agenda.item(0).text()
    assert any(ev.text.endswith("SWE 320") for ev in window.dashboard.month.events[date.today()])
    attention = [window.dashboard.attention.item(i).text() for i in range(window.dashboard.attention.count())]
    assert any("no meeting link" in t for t in attention)


def test_empty_state(qtbot, ctx):
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.show()
    assert window.meetings.list.count() == 0
    window.show_page(1)
    assert window.meetings.empty.isVisible() and not window.meetings.details_scroll.isVisible()
    assert window.nav_buttons[1].isChecked()


def test_live_card_distinguishes_opened_from_joined(qtbot, ctx, meeting, monkeypatch):
    from sessionly.models import SessionStatus
    from sessionly.ui import dashboard as dash
    monkeypatch.setattr(dash, "open_meeting", lambda ctx, link: True)
    start = datetime(2026, 10, 19, 10, 0)
    ctx.schedules.add(Schedule(id=None, meeting_id=meeting.id, day_of_week=0, start_time=time(10), duration_minutes=120))
    ctx.links.set_current(meeting.id, "https://meet.google.com/abc-defg-hij")
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    d = window.dashboard
    d.now_override = start + timedelta(minutes=2)
    d.refresh()
    assert d.live.pill.text() == "In progress"
    d.live.open_link()
    assert "not confirmed" in d.live.pill.text()
    assert ctx.sessions.find(meeting.id, start).status == SessionStatus.LINK_OPENED
    d.live.confirm_joined()
    assert d.live.pill.text() == "✓ Joined"
    assert ctx.links.current(meeting.id).status.value == "worked"
    assert d.ring.value == 1.0


def test_tray_badges():
    from sessionly.models import SessionStatus
    from sessionly.services.automation import LiveInfo
    from sessionly.ui.tray import badge_for

    class S:  # minimal session stand-in
        def __init__(self, status):
            self.status = status
    assert badge_for(LiveInfo("paused")) == (None, True)
    assert badge_for(LiveInfo("idle")) == (None, False)
    assert badge_for(LiveInfo("soon")) == ("soon", False)
    assert badge_for(LiveInfo("live", session=S(SessionStatus.LINK_OPENED))) == ("live", False)
    assert badge_for(LiveInfo("live", session=S(SessionStatus.JOINED))) == ("joined", False)


def test_month_view_keyboard_navigation(qtbot):
    from PySide6.QtCore import Qt
    from sessionly.ui.widgets import MonthView
    view = MonthView()
    qtbot.addWidget(view)
    start = view.selected
    with qtbot.waitSignal(view.day_selected):
        qtbot.keyClick(view, Qt.Key.Key_Right)
    assert view.selected == start + timedelta(days=1)
    qtbot.keyClick(view, Qt.Key.Key_Down)
    assert view.selected == start + timedelta(days=8)


def test_icon_renders_all_states(qtbot):
    from sessionly.ui.icon import icon_pixmap
    for badge in (None, "soon", "live", "joined"):
        assert not icon_pixmap(32, badge).isNull()
    assert not icon_pixmap(16, paused=True).isNull()


def test_meeting_dialog_blocks_blank_name(qtbot, ctx, boxes):
    dialog = MeetingDialog(ctx)
    qtbot.addWidget(dialog)
    dialog.accept()
    assert dialog.saved is None and boxes[0][0] == "warning"
    dialog.name.setText("Databases")
    dialog.accept()
    assert dialog.saved.name == "Databases"


def test_add_meeting_dialog_saves_ticked_days_link_and_turns_on_auto_join(qtbot, ctx, boxes):
    dialog = MeetingDialog(ctx)
    qtbot.addWidget(dialog)
    dialog.name.setText("Databases")
    dialog.times.set_days((1, 3))  # Tue & Thu
    dialog.times.start.setTime(QTime(14, 30))
    dialog.times.duration.setValue(90)
    dialog.url.setText("https://meet.google.com/abc-defg-hij")
    assert dialog.automation.isChecked()
    dialog.accept()

    meeting = dialog.saved
    schedules = ctx.schedules.for_meeting(meeting.id)
    assert sorted((s.day_of_week, s.start_time, s.duration_minutes) for s in schedules) == [
        (1, time(14, 30), 90), (3, time(14, 30), 90)]
    assert ctx.links.current(meeting.id).url == "https://meet.google.com/abc-defg-hij"
    assert ctx.settings.get(AUTO_OPEN_LINKS) is True
    assert boxes and boxes[0][0] == "information"


def test_add_meeting_dialog_quick_pick_weekdays(qtbot, ctx, boxes):
    dialog = MeetingDialog(ctx)
    qtbot.addWidget(dialog)
    dialog.name.setText("Daily stand-up")
    labels = [dialog.times.presets.itemText(i) for i in range(dialog.times.presets.count())]
    assert labels == ["Quick pick…"] + [label for label, _ in DAY_PRESETS]
    dialog.times.presets.activated.emit(1)  # Weekdays
    assert dialog.times.days() == (0, 1, 2, 3, 4) and dialog.times.presets.currentIndex() == 0
    dialog.accept()
    assert sorted(s.day_of_week for s in ctx.schedules.for_meeting(dialog.saved.id)) == [0, 1, 2, 3, 4]


def test_add_meeting_dialog_needs_a_day(qtbot, ctx, boxes):
    dialog = MeetingDialog(ctx)
    qtbot.addWidget(dialog)
    dialog.name.setText("Book club")
    dialog.times.set_days(())
    dialog.accept()
    assert dialog.saved is None and boxes[0] == ("warning", "Tick at least one day of the week.")
    assert ctx.meetings.list() == []


def test_add_meeting_dialog_rejects_bad_link_without_saving(qtbot, ctx, boxes):
    dialog = MeetingDialog(ctx)
    qtbot.addWidget(dialog)
    dialog.name.setText("Databases")
    dialog.url.setText("not a link")
    dialog.accept()
    assert dialog.saved is None and boxes[0][0] == "warning"
    assert ctx.meetings.list() == []


def test_schedule_dialog_warns_about_overlap(qtbot, ctx, meeting, boxes):
    ctx.schedules.add(Schedule(id=None, meeting_id=meeting.id, day_of_week=0, start_time=time(10), duration_minutes=120))
    other = ctx.meetings.create(Meeting(id=None, name="Databases"))
    dialog = ScheduleDialog(ctx, other.id)
    qtbot.addWidget(dialog)
    dialog.fields.set_days((0, 2))
    dialog.start.setTime(QTime(11, 0))
    dialog.duration.setValue(60)
    assert "Software Testing" in dialog.conflicts.text()
    dialog.accept()  # stubbed question answers Yes
    assert boxes and boxes[0][0] == "question"
    assert sorted(s.day_of_week for s in ctx.schedules.for_meeting(other.id)) == [0, 2]


def test_add_weekly_time_any_single_day(qtbot, ctx, meeting):
    dialog = ScheduleDialog(ctx, meeting.id)
    qtbot.addWidget(dialog)
    assert [b.text() for b in dialog.fields.day_buttons] == ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    dialog.fields.set_days((6,))  # Sunday only
    dialog.start.setTime(QTime(18, 0))
    dialog.accept()
    [s] = ctx.schedules.for_meeting(meeting.id)
    assert (s.day_of_week, s.start_time) == (6, time(18))


def test_edit_weekly_time_changes_only_that_day(qtbot, ctx, meeting):
    mon = ctx.schedules.add(Schedule(id=None, meeting_id=meeting.id, day_of_week=0, start_time=time(8),
                                     duration_minutes=120))
    ctx.schedules.add(Schedule(id=None, meeting_id=meeting.id, day_of_week=2, start_time=time(8), duration_minutes=120))
    dialog = ScheduleDialog(ctx, meeting.id, mon)
    qtbot.addWidget(dialog)
    assert dialog.day.count() == 7 and dialog.day.currentIndex() == 0  # single days when editing
    dialog.start.setTime(QTime(10, 0))
    dialog.accept()
    assert sorted((s.day_of_week, s.start_time) for s in ctx.schedules.for_meeting(meeting.id)) == [
        (0, time(10)), (2, time(8))]


def test_link_dialog_validates_live_and_saves(qtbot, ctx, meeting):
    dialog = LinkDialog(ctx, meeting)
    qtbot.addWidget(dialog)
    ok = dialog.box.button(QDialogButtonBox.StandardButton.Ok)
    dialog.url.setText("http://meet.google.com/abc-defg-hij")
    assert not ok.isEnabled() and "insecure" in dialog.feedback.text()
    dialog.url.setText("https://meet.google.com/abc-defg-hij")
    assert ok.isEnabled() and "Google Meet" in dialog.feedback.text()
    dialog.accept()
    assert ctx.links.current(meeting.id).url == "https://meet.google.com/abc-defg-hij"


def test_link_dialog_confirms_when_link_belongs_to_other_meeting(qtbot, ctx, meeting, boxes):
    ctx.links.set_current(meeting.id, "https://meet.google.com/abc-defg-hij")
    other = ctx.meetings.create(Meeting(id=None, name="Databases"))
    dialog = LinkDialog(ctx, other)
    qtbot.addWidget(dialog)
    dialog.url.setText("https://meet.google.com/abc-defg-hij")
    dialog.accept()
    assert boxes[0][0] == "question" and "Software Testing" in boxes[0][1]


def test_exception_dialog_cancels_next_session(qtbot, ctx, meeting):
    s = ctx.schedules.add(Schedule(id=None, meeting_id=meeting.id, day_of_week=2, start_time=time(9), duration_minutes=60))
    dialog = ExceptionDialog(ctx, meeting.id)
    qtbot.addWidget(dialog)
    assert dialog._kind() == ExceptionKind.CANCELLED
    assert dialog.original_date.date().toPython().weekday() == 2
    dialog.accept()
    (e,) = ctx.schedules.exceptions_for_meeting(meeting.id)
    assert e.kind == ExceptionKind.CANCELLED and e.schedule_id == s.id


def test_exception_dialog_without_schedules_offers_only_extra(qtbot, ctx, meeting):
    dialog = ExceptionDialog(ctx, meeting.id)
    qtbot.addWidget(dialog)
    assert dialog._kind() == ExceptionKind.EXTRA
    assert not dialog.kind_group.button(0).isEnabled()


def test_setup_wizard_creates_meeting_schedule_and_link(qtbot, ctx):
    wizard = SetupWizard(ctx)
    qtbot.addWidget(wizard)
    wizard.name_page.name.setText("Jane Doe")
    wizard.meeting_page.name.setText("Software Testing")
    wizard.meeting_page.times.set_days((0, 2))
    wizard.link_page.url.setText("https://zoom.us/j/1234567890")
    wizard._save()
    assert ctx.settings.display_name == "Jane Doe"
    (c,) = ctx.meetings.list()
    assert sorted(s.day_of_week for s in ctx.schedules.for_meeting(c.id)) == [0, 2]
    assert ctx.links.current(c.id).platform.value == "zoom"
    assert ctx.settings.get("setup_completed") is True


def test_setup_wizard_skip(qtbot, ctx):
    wizard = SetupWizard(ctx)
    qtbot.addWidget(wizard)
    wizard.meeting_page.skip.setChecked(True)
    wizard._save()
    assert ctx.meetings.list() == [] and ctx.settings.get("setup_completed") is True


def test_class_state_labels():
    start = datetime(2026, 10, 19, 10, 0)
    o = Occurrence(1, "X", start, start + timedelta(hours=2), 5, "weekly")
    assert class_state(o, start - timedelta(hours=1)) == "Upcoming"
    assert class_state(o, start - timedelta(minutes=3)) == "Starting soon"
    assert class_state(o, start + timedelta(minutes=1)) == "In progress"
    assert class_state(o, start + timedelta(hours=3)) == "Finished"

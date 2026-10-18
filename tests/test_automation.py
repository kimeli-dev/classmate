from datetime import date, datetime, time, timedelta

import pytest

from sessionly.config import AppConfig
from sessionly.context import AppContext
from sessionly.models import Meeting, FailureReason, Schedule, SessionStatus
from sessionly.services.settings import AUTO_OPEN_LINKS, AUTOMATION_PAUSED

MONDAY = date(2026, 10, 19)
START = datetime(2026, 10, 19, 10, 0)
LINK = "https://meet.google.com/abc-defg-hij"


@pytest.fixture
def net():
    return {"up": True}


@pytest.fixture
def ctx(db, tmp_path, net):
    return AppContext.create(AppConfig(data_dir=tmp_path), db, online=lambda: net["up"])


@pytest.fixture
def meeting(ctx):
    c = ctx.meetings.create(Meeting(id=None, name="Software Testing", short_code="SWE 320"))
    ctx.schedules.add(Schedule(id=None, meeting_id=c.id, day_of_week=0, start_time=time(10), duration_minutes=120,
                               preparation_minutes=5))
    return c


def kinds(actions):
    return [a.kind for a in actions]


def test_nothing_before_preparation_time(ctx, meeting):
    assert ctx.engine.tick(START - timedelta(minutes=6)) == []


def test_reminds_once_at_preparation_time(ctx, meeting):
    ctx.links.set_current(meeting.id, LINK)
    actions = ctx.engine.tick(START - timedelta(minutes=5))
    assert kinds(actions) == ["remind"] and actions[0].url == LINK
    assert ctx.engine.tick(START - timedelta(minutes=4)) == []  # duplicate prevented
    assert ctx.sessions.find(meeting.id, START).status == SessionStatus.REMINDED


def test_no_duplicate_after_restart(ctx, meeting, db, tmp_path, net):
    ctx.engine.tick(START)
    restarted = AppContext.create(AppConfig(data_dir=tmp_path), db, online=lambda: net["up"])
    assert restarted.engine.tick(START + timedelta(minutes=1)) == []


def test_auto_open_when_enabled(ctx, meeting):
    ctx.links.set_current(meeting.id, LINK)
    ctx.settings.set(AUTO_OPEN_LINKS, True)
    (action,) = ctx.engine.tick(START - timedelta(minutes=5))
    assert action.kind == "open_link" and action.url == LINK
    assert ctx.sessions.find(meeting.id, START).status == SessionStatus.LINK_OPENED
    assert ctx.engine.tick(START) == []


def test_auto_open_respects_course_automation_switch(ctx, meeting):
    ctx.links.set_current(meeting.id, LINK)
    ctx.settings.set(AUTO_OPEN_LINKS, True)
    meeting.automation_enabled = False
    ctx.meetings.update(meeting)
    assert kinds(ctx.engine.tick(START)) == ["remind"]


def test_failed_link_is_not_opened(ctx, meeting):
    link, _ = ctx.links.set_current(meeting.id, LINK)
    ctx.links.report_problem(link.id, FailureReason.INVALID_LINK)
    ctx.settings.set(AUTO_OPEN_LINKS, True)
    (action,) = ctx.engine.tick(START)
    assert action.kind == "remind" and action.url is None and "replacing" in action.message


def test_offline_waits_then_opens(ctx, meeting, net):
    ctx.links.set_current(meeting.id, LINK)
    ctx.settings.set(AUTO_OPEN_LINKS, True)
    net["up"] = False
    assert kinds(ctx.engine.tick(START - timedelta(minutes=5))) == ["offline"]
    assert ctx.engine.tick(START - timedelta(minutes=4)) == []  # warned once only
    net["up"] = True
    assert kinds(ctx.engine.tick(START - timedelta(minutes=3))) == ["open_link"]


def test_late_start_reminds_instead_of_opening(ctx, meeting):
    ctx.links.set_current(meeting.id, LINK)
    ctx.settings.set(AUTO_OPEN_LINKS, True)
    (action,) = ctx.engine.tick(START + timedelta(minutes=30))
    assert action.kind == "remind" and "missed the start" in action.message


def test_class_that_passed_while_off_is_reported_missed(ctx, meeting):
    actions = ctx.engine.tick(START + timedelta(hours=3))
    assert kinds(actions) == ["missed"] and "SWE 320" in actions[0].message
    assert ctx.sessions.find(meeting.id, START).status == SessionStatus.MISSED
    assert ctx.engine.tick(START + timedelta(hours=4)) == []


def test_pause_stops_everything(ctx, meeting):
    ctx.settings.set(AUTOMATION_PAUSED, True)
    assert ctx.engine.tick(START) == []
    assert ctx.engine.live(START).kind == "paused"


def test_notifications_off_still_marks_handled(ctx, meeting):
    meeting.notifications_enabled = False
    ctx.meetings.update(meeting)
    assert ctx.engine.tick(START) == []
    assert ctx.sessions.find(meeting.id, START).status == SessionStatus.REMINDED


def test_live_states(ctx, meeting):
    assert ctx.engine.live(START - timedelta(hours=3)).kind == "idle"
    soon = ctx.engine.live(START - timedelta(minutes=30))
    assert soon.kind == "soon" and soon.occurrence.start == START
    live = ctx.engine.live(START + timedelta(minutes=1))
    assert live.kind == "live" and live.session is None
    ctx.sessions.confirm_joined(live.occurrence)
    assert ctx.engine.live(START + timedelta(minutes=2)).status == SessionStatus.JOINED


def test_joined_is_only_set_by_confirmation(ctx, meeting):
    ctx.links.set_current(meeting.id, LINK)
    ctx.settings.set(AUTO_OPEN_LINKS, True)
    ctx.engine.tick(START)
    assert ctx.engine.live(START).status == SessionStatus.LINK_OPENED


def test_cancelled_class_is_ignored(ctx, meeting):
    from sessionly.models import ExceptionKind, ScheduleException
    sched = ctx.schedules.for_meeting(meeting.id)[0]
    ctx.schedules.add_exception(ScheduleException(id=None, meeting_id=meeting.id, kind=ExceptionKind.CANCELLED,
                                                  schedule_id=sched.id, original_date=MONDAY))
    assert ctx.engine.tick(START) == []
    assert ctx.engine.live(START).kind != "live"


def test_startup_registry_round_trip():
    winreg = pytest.importorskip("winreg")
    from sessionly.services import startup
    key = r"Software\ClassmateTest\Run"
    try:
        startup.set_enabled(True, key)
        assert startup.is_enabled(key)
        assert "--background" in startup.launch_command()
        startup.set_enabled(False, key)
        assert not startup.is_enabled(key)
    finally:
        for sub in (r"Software\ClassmateTest\Run", r"Software\ClassmateTest"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass

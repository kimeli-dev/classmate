from datetime import date, datetime, time

import pytest

from sessionly.models import Meeting, ExceptionKind, Schedule, ScheduleException
from sessionly.services import ValidationError
from sessionly.services.schedules import find_overlaps

MONDAY = date(2026, 10, 19)


@pytest.fixture
def meeting(meetings):
    return meetings.create(Meeting(id=None, name="Software Testing", short_code="SWE 320"))


@pytest.fixture
def weekly(schedules, meeting):
    return schedules.add(Schedule(id=None, meeting_id=meeting.id, day_of_week=0, start_time=time(10, 0),
                                  duration_minutes=120, preparation_minutes=5))


def test_recurring_schedule_round_trip(schedules, weekly, meeting):
    stored = schedules.for_meeting(meeting.id)
    assert stored == [weekly]
    assert stored[0].start_time == time(10, 0)
    assert stored[0].end_time == time(12, 0)


def test_occurs_every_week(schedules, weekly):
    occ = schedules.occurrences(MONDAY, date(2026, 11, 1))
    assert [o.start for o in occ] == [datetime(2026, 10, 19, 10), datetime(2026, 10, 26, 10)]
    assert occ[0].end == datetime(2026, 10, 19, 12)
    assert occ[0].meeting_title == "SWE 320 - Software Testing"


def test_disabled_schedule_produces_nothing(schedules, weekly):
    weekly.enabled = False
    schedules.update(weekly)
    assert schedules.occurrences(MONDAY, MONDAY) == []


def test_cancelled_class_is_flagged(schedules, weekly, meeting):
    schedules.add_exception(ScheduleException(id=None, meeting_id=meeting.id, kind=ExceptionKind.CANCELLED,
                                              schedule_id=weekly.id, original_date=MONDAY, note="Host away"))
    (occ,) = schedules.occurrences(MONDAY, MONDAY)
    assert occ.cancelled and occ.note == "Host away"
    assert find_overlaps([occ, occ]) == []  # cancelled classes never clash


def test_rescheduled_class_moves(schedules, weekly, meeting):
    schedules.add_exception(ScheduleException(id=None, meeting_id=meeting.id, kind=ExceptionKind.RESCHEDULED,
                                              schedule_id=weekly.id, original_date=MONDAY,
                                              new_start=datetime(2026, 10, 21, 14, 0)))
    occ = schedules.occurrences(MONDAY, date(2026, 10, 25))
    assert len(occ) == 1
    assert occ[0].start == datetime(2026, 10, 21, 14, 0)
    assert occ[0].end == datetime(2026, 10, 21, 16, 0)  # keeps the regular duration
    assert occ[0].origin == "rescheduled"


def test_extra_session(schedules, meeting):
    schedules.add_exception(ScheduleException(id=None, meeting_id=meeting.id, kind=ExceptionKind.EXTRA,
                                              new_start=datetime(2026, 10, 24, 9, 0), new_duration_minutes=90))
    (occ,) = schedules.occurrences(MONDAY, date(2026, 10, 25))
    assert occ.origin == "extra" and occ.end == datetime(2026, 10, 24, 10, 30)


def test_exception_date_must_match_weekday(schedules, weekly, meeting):
    with pytest.raises(ValidationError, match="Tuesday"):
        schedules.add_exception(ScheduleException(id=None, meeting_id=meeting.id, kind=ExceptionKind.CANCELLED,
                                                  schedule_id=weekly.id, original_date=date(2026, 10, 20)))


def test_duplicate_exception_rejected(schedules, weekly, meeting):
    schedules.add_exception(ScheduleException(id=None, meeting_id=meeting.id, kind=ExceptionKind.CANCELLED,
                                              schedule_id=weekly.id, original_date=MONDAY))
    with pytest.raises(ValidationError, match="already has a change"):
        schedules.add_exception(ScheduleException(id=None, meeting_id=meeting.id, kind=ExceptionKind.CANCELLED,
                                                  schedule_id=weekly.id, original_date=MONDAY))


def test_invalid_duration_rejected(schedules, meeting):
    with pytest.raises(ValidationError):
        schedules.add(Schedule(id=None, meeting_id=meeting.id, day_of_week=0, start_time=time(9), duration_minutes=0))


def test_overlapping_weekly_classes_detected(schedules, meetings, weekly):
    other = meetings.create(Meeting(id=None, name="Databases"))
    clashes = schedules.weekly_conflicts(0, time(11, 0), 60)
    assert len(clashes) == 1 and "Software Testing" in clashes[0]
    assert schedules.weekly_conflicts(0, time(12, 0), 60) == []  # back-to-back is fine
    assert schedules.weekly_conflicts(0, time(11), 60, exclude_schedule_id=weekly.id) == []

    schedules.add(Schedule(id=None, meeting_id=other.id, day_of_week=0, start_time=time(11), duration_minutes=60))
    assert len(find_overlaps(schedules.occurrences(MONDAY, MONDAY))) == 1


def test_overlap_across_sunday_midnight(schedules, meeting):
    schedules.add(Schedule(id=None, meeting_id=meeting.id, day_of_week=6, start_time=time(23, 0), duration_minutes=120))
    assert schedules.weekly_conflicts(0, time(0, 30), 30)


def test_automation_off_still_shows_in_timetable(schedules, meetings, meeting, weekly):
    meeting.automation_enabled = False
    meetings.update(meeting)
    assert len(schedules.occurrences(MONDAY, MONDAY)) == 1

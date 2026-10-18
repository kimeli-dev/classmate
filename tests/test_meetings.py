from datetime import time

import pytest

from sessionly.models import Meeting, Schedule
from sessionly.services import ValidationError


def test_create_edit_delete_course(meetings):
    c = meetings.create(Meeting(id=None, name="  Software Testing ", short_code="swe  320", host_name="Dr. Otieno"))
    assert c.id is not None
    assert c.name == "Software Testing"
    assert c.short_code == "SWE 320"
    assert c.created_at and c.updated_at

    c.name = "Software Testing & QA"
    c.automation_enabled = False
    updated = meetings.update(c)
    assert updated.name == "Software Testing & QA"
    assert updated.automation_enabled is False

    meetings.delete(c.id)
    assert meetings.list() == []


def test_blank_name_rejected(meetings):
    with pytest.raises(ValidationError):
        meetings.create(Meeting(id=None, name="   "))


def test_duplicate_code_rejected_case_insensitively(meetings):
    meetings.create(Meeting(id=None, name="A", short_code="SWE 320"))
    with pytest.raises(ValidationError, match="already used"):
        meetings.create(Meeting(id=None, name="B", short_code="swe 320"))


def test_empty_codes_may_repeat(meetings):
    meetings.create(Meeting(id=None, name="A"))
    meetings.create(Meeting(id=None, name="B"))
    assert len(meetings.list()) == 2


def test_blank_display_name_stored_as_none(meetings):
    c = meetings.create(Meeting(id=None, name="A", preferred_display_name="   "))
    assert c.preferred_display_name is None


def test_delete_cascades(meetings, schedules, links, db):
    c = meetings.create(Meeting(id=None, name="A"))
    schedules.add(Schedule(id=None, meeting_id=c.id, day_of_week=0, start_time=time(10), duration_minutes=60))
    links.set_current(c.id, "https://meet.google.com/abc-defg-hij")
    meetings.delete(c.id)
    for table in ("schedules", "meeting_links"):
        assert db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

import sqlite3

import pytest

from sessionly.models import Meeting, FailureReason, LinkStatus
from sessionly.services import ValidationError

MEET = "https://meet.google.com/abc-defg-hij"
MEET2 = "https://meet.google.com/xyz-wxyz-xyz"


@pytest.fixture
def meeting(meetings):
    return meetings.create(Meeting(id=None, name="Software Testing"))


def test_link_saved_against_course(links, meeting, meetings):
    other = meetings.create(Meeting(id=None, name="Databases"))
    link, _ = links.set_current(meeting.id, MEET)
    assert link.meeting_id == meeting.id and link.is_current and link.status == LinkStatus.UNVERIFIED
    assert links.current(meeting.id).url == MEET
    assert links.current(other.id) is None


def test_replacement_keeps_history(links, meeting):
    links.set_current(meeting.id, MEET)
    second, _ = links.set_current(meeting.id, MEET2)
    assert links.current(meeting.id).id == second.id
    history = links.history(meeting.id)
    assert [l.url for l in history] == [MEET2, MEET]
    assert [l.is_current for l in history] == [True, False]


def test_reentering_old_link_revives_it_without_duplicate(links, meeting):
    first, _ = links.set_current(meeting.id, MEET)
    links.mark_worked(first.id)
    links.set_current(meeting.id, MEET2)
    revived, _ = links.set_current(meeting.id, MEET)
    assert revived.id == first.id and revived.status == LinkStatus.WORKED
    assert len(links.history(meeting.id)) == 2


def test_invalid_replacement_rejected_and_current_unchanged(links, meeting):
    links.set_current(meeting.id, MEET)
    with pytest.raises(ValidationError):
        links.set_current(meeting.id, "not a link at all")
    assert links.current(meeting.id).url == MEET


def test_shared_url_is_reported_for_confirmation(links, meeting, meetings):
    other = meetings.create(Meeting(id=None, name="Databases"))
    links.set_current(meeting.id, MEET)
    assert links.other_meetings_using(MEET, other.id) == [(meeting.id, "Software Testing")]
    assert links.other_meetings_using(MEET, meeting.id) == []


@pytest.mark.parametrize("reason", [FailureReason.HOST_NOT_STARTED, FailureReason.WAITING_ROOM,
                                    FailureReason.NO_INTERNET, FailureReason.AUTHENTICATION])
def test_non_link_problems_do_not_request_replacement(links, meeting, reason):
    link, _ = links.set_current(meeting.id, MEET)
    outcome = links.report_problem(link.id, reason)
    assert not outcome.needs_replacement
    current = links.current(meeting.id)
    assert current.status == LinkStatus.UNVERIFIED and current.failure_reason == reason


def test_invalid_link_problem_requests_replacement(links, meeting):
    link, _ = links.set_current(meeting.id, MEET)
    outcome = links.report_problem(link.id, FailureReason.INVALID_LINK)
    assert outcome.needs_replacement
    assert links.current(meeting.id).status == LinkStatus.FAILED
    replacement, _ = links.set_current(meeting.id, MEET2)
    assert replacement.status == LinkStatus.UNVERIFIED


def test_mark_worked_clears_failure(links, meeting):
    link, _ = links.set_current(meeting.id, MEET)
    links.report_problem(link.id, FailureReason.UNKNOWN)
    worked = links.mark_worked(link.id)
    assert worked.status == LinkStatus.WORKED and worked.last_success_at and worked.failure_reason is None


def test_current_link_cannot_be_deleted(links, meeting):
    link, _ = links.set_current(meeting.id, MEET)
    with pytest.raises(ValidationError):
        links.delete_from_history(link.id)


def test_only_one_current_link_enforced_by_schema(links, meeting, db):
    links.set_current(meeting.id, MEET)
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute("INSERT INTO meeting_links (meeting_id, url, platform, is_current, created_at, updated_at) "
                        "VALUES (?, ?, 'google_meet', 1, 'x', 'x')", (meeting.id, MEET2))

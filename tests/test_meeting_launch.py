from urllib.parse import parse_qs, urlsplit

import pytest

from sessionly.models import Meeting
from sessionly.services import ValidationError
from sessionly.services.meeting_launch import allowed_google_account, plan_launch
from sessionly.services.settings import GOOGLE_MEET_ACCOUNT, GOOGLE_MEET_ALLOWED


@pytest.fixture
def meeting(meetings):
    return meetings.create(Meeting(id=None, name="Software Testing"))


def _query(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_passcode_is_saved_with_the_link_and_kept_when_re_entered(links, meeting):
    link, _ = links.set_current(meeting.id, "https://us02web.zoom.us/j/12345678901", passcode=" 4kT9z ")
    assert link.passcode == "4kT9z"
    again, _ = links.set_current(meeting.id, "https://us02web.zoom.us/j/12345678901")
    assert again.passcode == "4kT9z"
    assert links.set_passcode(link.id, "").passcode == ""
    with pytest.raises(ValidationError):
        links.set_passcode(link.id, "has space")


def test_zoom_opens_the_app_with_meeting_id_passcode_and_name(links, meeting):
    link, _ = links.set_current(meeting.id, "https://us02web.zoom.us/j/12345678901", passcode="4kT9z")
    plan = plan_launch(link, "Kim Student")
    assert plan.primary.startswith("zoommtg://zoom.us/join?")
    assert _query(plan.primary) == {"action": "join", "confno": "12345678901", "pwd": "4kT9z", "uname": "Kim Student"}
    assert plan.fallback == link.url
    assert plan.copy_passcode == "4kT9z"


def test_zoom_uses_the_links_own_pwd_but_does_not_copy_it(links, meeting):
    link, _ = links.set_current(meeting.id, "https://zoom.us/j/12345678901?pwd=EnCoDeD123")
    plan = plan_launch(link)
    assert _query(plan.primary)["pwd"] == "EnCoDeD123"
    assert plan.copy_passcode == ""


def test_zoom_vanity_link_opens_in_browser_with_passcode_copied(links, meeting):
    link, _ = links.set_current(meeting.id, "https://zoom.us/my/drsmith", passcode="111222")
    plan = plan_launch(link)
    assert plan.primary == link.url and plan.copy_passcode == "111222"


def test_meet_uses_google_account_only_after_it_is_allowed(links, settings, meeting):
    link, _ = links.set_current(meeting.id, "https://meet.google.com/abc-defg-hij")
    settings.set(GOOGLE_MEET_ACCOUNT, "kim@students.example.ac.ke")
    assert allowed_google_account(settings) is None
    assert plan_launch(link, google_account=allowed_google_account(settings)).primary == link.url

    settings.set(GOOGLE_MEET_ALLOWED, True)
    plan = plan_launch(link, google_account=allowed_google_account(settings))
    assert _query(plan.primary) == {"authuser": "kim@students.example.ac.ke"}
    assert plan.fallback == link.url


def test_invalid_google_email_is_never_used(settings):
    settings.set(GOOGLE_MEET_ACCOUNT, "not-an-email")
    settings.set(GOOGLE_MEET_ALLOWED, True)
    assert allowed_google_account(settings) is None

import pytest

from sessionly.models import Platform
from sessionly.services.link_validation import check_meeting_url


@pytest.mark.parametrize("url, platform", [
    ("https://meet.google.com/abc-defg-hij", Platform.GOOGLE_MEET),
    ("meet.google.com/abc-defg-hij", Platform.GOOGLE_MEET),
    ("https://us02web.zoom.us/j/12345678901?pwd=abcDEF123", Platform.ZOOM),
    ("https://zoom.us/my/dr.otieno", Platform.ZOOM),
    ("https://teams.microsoft.com/l/meetup-join/19%3ameeting_x/0", Platform.TEAMS),
])
def test_known_platforms(url, platform):
    check = check_meeting_url(url)
    assert check.ok and check.platform == platform and not check.warnings


def test_meet_code_normalised_and_query_kept_for_zoom():
    assert check_meeting_url("  https://MEET.google.com/ABC-DEFG-HIJ ").url == "https://meet.google.com/abc-defg-hij"
    assert check_meeting_url("https://zoom.us/j/1234567890?pwd=XyZ").url == "https://zoom.us/j/1234567890?pwd=XyZ"


@pytest.mark.parametrize("url, message", [
    ("", "paste"),
    ("http://meet.google.com/abc-defg-hij", "insecure"),
    ("ftp://zoom.us/j/123", "https"),
    ("https://user:pw@zoom.us/j/1234567890", "user name"),
    ("https://meet.google.com/abc defg", "spaces"),
    ("https://localhost/x", "valid website"),
    ("https://zoom.us:8443/j/1234567890", "ports"),
])
def test_rejected(url, message):
    check = check_meeting_url(url)
    assert not check.ok and message in check.error


def test_lookalike_domain_is_not_zoom():
    check = check_meeting_url("https://zoom.us.evil-site.com/j/1234567890")
    assert check.ok and check.platform == Platform.OTHER and check.warnings


def test_unusual_paths_warn():
    assert check_meeting_url("https://meet.google.com/landing").warnings
    assert check_meeting_url("https://zoom.us/pricing").warnings

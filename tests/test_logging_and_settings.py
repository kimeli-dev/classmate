import logging

from sessionly.logging_setup import redact, setup_logging
from sessionly.models import Meeting


def test_redacts_urls_secrets_and_emails():
    text = redact("join https://us02web.zoom.us/j/12345678901?pwd=SECRET123 from student@uni.ac.ke")
    assert "SECRET123" not in text and "12345678901" not in text and "student@" not in text
    assert "<url:us02web.zoom.us>" in text and "<email>" in text


def test_redacts_bare_meeting_links():
    text = redact("link meet.google.com/abc-defg-hij saved")
    assert "abc-defg-hij" not in text and "<url:meet.google.com>" in text


def test_redacts_inline_secrets():
    assert "hunter2" not in redact("api_key=hunter2 token=abc")


def test_log_file_never_contains_meeting_link(tmp_path, links, meetings):
    log_file = setup_logging(tmp_path / "logs", "DEBUG")
    try:
        c = meetings.create(Meeting(id=None, name="A"))
        links.set_current(c.id, "https://zoom.us/j/1234567890?pwd=TOPSECRET")
        logging.getLogger("test").info("User pasted https://zoom.us/j/1234567890?pwd=TOPSECRET")
        for h in logging.getLogger().handlers:
            h.flush()
        content = log_file.read_text(encoding="utf-8")
        assert "TOPSECRET" not in content and "1234567890" not in content
        assert "link id=" in content  # the event itself is still logged
    finally:
        for h in list(logging.getLogger().handlers):
            h.close()
            logging.getLogger().removeHandler(h)


def test_settings_round_trip(settings):
    assert settings.display_name == ""
    settings.display_name = "  Jane D. "
    assert settings.display_name == "Jane D."
    settings.set("flag", True)
    assert settings.get("flag") is True

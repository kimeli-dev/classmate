"""Turns a saved meeting link into what Sessionly actually opens.

- Zoom: the Zoom desktop app's ``zoommtg://`` join link, carrying the meeting ID, the passcode
  the host shared and the user's display name. The app joins with whatever Zoom account
  the user is signed in to there. The normal https link is the fallback, and the passcode is
  also put on the clipboard in case Zoom still asks for it.
- Google Meet: the link with ``authuser=<email>`` once the user has allowed Sessionly to use
  that Google account, so the browser opens Meet as them instead of another signed-in account.
  Meet's own "Join" / "Ask to join" step and the host's admission are always left to the user.

Pure logic (no Qt) so it can be unit-tested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sessionly.models import MeetingLink, Platform
from sessionly.services.settings import GOOGLE_MEET_ACCOUNT, GOOGLE_MEET_ALLOWED, SettingsService

_ZOOM_ID = re.compile(r"^/(?:j|w|s|wc/join|wc)/(\d{9,11})(?:/|$)")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(text: str) -> bool:
    return bool(_EMAIL.match((text or "").strip()))


@dataclass
class LaunchPlan:
    primary: str                 # opened first
    fallback: str | None = None  # opened if the primary can't be (e.g. Zoom app not installed)
    copy_passcode: str = ""      # put on the clipboard so it can be pasted if asked
    note: str = ""               # one line telling the user what to expect


def _zoom_plan(link: MeetingLink, display_name: str) -> LaunchPlan:
    parts = urlsplit(link.url)
    query = dict(parse_qsl(parts.query))
    passcode = link.passcode or query.get("pwd", "")
    m = _ZOOM_ID.match(parts.path)
    copy = link.passcode  # a pwd= in the link is Zoom's encoded form - not something to paste
    if not m:  # vanity /my/<name> links have no meeting ID to hand to the app
        return LaunchPlan(link.url, copy_passcode=copy,
                          note="Passcode copied - paste it if Zoom asks." if copy else "")
    host = "zoomgov.com" if (parts.hostname or "").endswith("zoomgov.com") else "zoom.us"
    params = {"action": "join", "confno": m.group(1)}
    if passcode:
        params["pwd"] = passcode
    if display_name:
        params["uname"] = display_name
    note = "Zoom opens with the account you're signed in to in the Zoom app."
    if copy:
        note += " The passcode is on your clipboard if Zoom still asks for it."
    return LaunchPlan(f"zoommtg://{host}/join?{urlencode(params)}", fallback=link.url,
                      copy_passcode=copy, note=note)


def _meet_plan(link: MeetingLink, google_account: str | None) -> LaunchPlan:
    if not google_account:
        return LaunchPlan(link.url, note="Meet opens with the Google account your browser picks. "
                                         "Choose your account in Settings to always use it.")
    parts = urlsplit(link.url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "authuser"] + [("authuser", google_account)]
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return LaunchPlan(url, fallback=link.url,
                      note=f"Meet opens as {google_account}. Click Join (or Ask to join) and wait for the host.")


def plan_launch(link: MeetingLink, display_name: str = "", google_account: str | None = None) -> LaunchPlan:
    if link.platform == Platform.ZOOM:
        return _zoom_plan(link, display_name)
    if link.platform == Platform.GOOGLE_MEET:
        return _meet_plan(link, google_account)
    return LaunchPlan(link.url)


def allowed_google_account(settings: SettingsService) -> str | None:
    """The Google account for Meet, only once the user has explicitly allowed it."""
    email = (settings.get(GOOGLE_MEET_ACCOUNT, "") or "").strip()
    return email if settings.get(GOOGLE_MEET_ALLOWED, False) and valid_email(email) else None

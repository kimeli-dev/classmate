"""Meeting URL format checks.

A passing check means only that the URL *looks like* a meeting link for a known
platform. It is never treated as proof that the meeting exists or that the link works.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from sessionly.models import Platform

_MEET_CODE = re.compile(r"^/[a-z]{3}-[a-z]{4}-[a-z]{3}/?$")
_MEET_LOOKUP = re.compile(r"^/lookup/[\w-]+/?$")
_ZOOM_JOIN = re.compile(r"^/(?:j|w|s|wc/join|wc)/\d{9,11}(?:/[\w-]+)?/?$")
_ZOOM_VANITY = re.compile(r"^/my/[\w.-]+/?$")


@dataclass
class LinkCheck:
    ok: bool
    url: str = ""
    platform: Platform = Platform.OTHER
    error: str = ""
    warnings: list[str] = field(default_factory=list)


def _host_matches(host: str, domain: str) -> bool:
    # Exact or true subdomain - rejects look-alikes such as zoom.us.example.com.
    return host == domain or host.endswith("." + domain)


def check_meeting_url(raw: str) -> LinkCheck:
    text = (raw or "").strip()
    if not text:
        return LinkCheck(False, error="Please paste a meeting link.")
    if any(c.isspace() for c in text):
        return LinkCheck(False, error="The link contains spaces. Paste only the link itself.")
    if "://" not in text:
        text = "https://" + text

    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return LinkCheck(False, error="That does not look like a valid web address.")

    if parts.scheme.lower() == "http":
        return LinkCheck(False, error="The link uses insecure http://. Meeting links should start with https://.")
    if parts.scheme.lower() != "https":
        return LinkCheck(False, error="Only https:// meeting links are supported.")
    if parts.username or parts.password:
        return LinkCheck(False, error="Links containing a user name or password before the address are not accepted.")
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        return LinkCheck(False, error="The link is missing a valid website address.")
    if port not in (None, 443):
        return LinkCheck(False, error="Meeting links on unusual ports are not accepted.")

    netloc = host
    path = parts.path
    warnings: list[str] = []

    if _host_matches(host, "meet.google.com"):
        platform = Platform.GOOGLE_MEET
        path = path.lower()
        if not (_MEET_CODE.match(path) or _MEET_LOOKUP.match(path)):
            warnings.append("This Google Meet address does not have the usual abc-defg-hij meeting code.")
    elif _host_matches(host, "zoom.us") or _host_matches(host, "zoomgov.com"):
        platform = Platform.ZOOM
        if not (_ZOOM_JOIN.match(path) or _ZOOM_VANITY.match(path)):
            warnings.append("This Zoom address is not a standard join link (zoom.us/j/<meeting ID>).")
    elif _host_matches(host, "teams.microsoft.com") or _host_matches(host, "teams.live.com"):
        platform = Platform.TEAMS
    else:
        platform = Platform.OTHER
        warnings.append("This is not a Zoom, Google Meet or Teams address. Make sure it came from your host.")

    url = urlunsplit(("https", netloc, path, parts.query, parts.fragment))
    return LinkCheck(True, url=url, platform=platform, warnings=warnings)

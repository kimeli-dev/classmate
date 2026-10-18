"""Opening a meeting - shared by the tray (automatic), dashboard and Meetings page."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication

from sessionly.context import AppContext
from sessionly.models import MeetingLink
from sessionly.services.meeting_launch import LaunchPlan, allowed_google_account, plan_launch


def open_meeting(ctx: AppContext, link: MeetingLink) -> LaunchPlan | None:
    """Open the meeting the best way for its platform. Returns the plan used, or None if
    nothing could be opened."""
    meeting = ctx.meetings.get(link.meeting_id)
    name = meeting.preferred_display_name or ctx.settings.display_name
    plan = plan_launch(link, name, allowed_google_account(ctx.settings))
    if plan.copy_passcode:
        QGuiApplication.clipboard().setText(plan.copy_passcode)
    for url in (plan.primary, plan.fallback):
        if url and QDesktopServices.openUrl(QUrl(url)):
            return plan
    return None

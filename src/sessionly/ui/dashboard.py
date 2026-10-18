from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from sessionly.context import AppContext
from sessionly.models import Occurrence, LinkStatus, SessionStatus
from sessionly.services.automation import LiveInfo
from sessionly.services.schedules import find_overlaps
from sessionly.services.settings import AUTOMATION_PAUSED
from sessionly.ui import theme
from sessionly.ui.launch import open_meeting
from sessionly.ui.widgets import CalendarEvent, Card, MonthView, Pill, ProgressRing, month_title


def class_state(o: Occurrence, now: datetime) -> str:
    if o.cancelled:
        return "Cancelled"
    if now >= o.end:
        return "Finished"
    if now >= o.start:
        return "In progress"
    if now >= o.start - timedelta(minutes=o.preparation_minutes):
        return "Starting soon"
    return {"rescheduled": "Moved here", "extra": "Extra session"}.get(o.origin, "Upcoming")


def _dot(colour: str, size: int = 10) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(colour))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pix)


def _minutes(delta: timedelta) -> str:
    m = max(0, int(delta.total_seconds() // 60))
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d} min"


def _accent(button: QPushButton) -> QPushButton:
    button.setProperty("accent", True)
    return button


class LiveCard(Card):
    """The join indicator. 'Link opened' and 'Joined' are deliberately different states:
    Sessionly can open a link but cannot see inside the meeting, so joining is confirmed by you."""

    changed = Signal()
    problem = Signal(object)  # Occurrence

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__("Live session", parent)
        self.ctx = ctx
        self.info: LiveInfo | None = None
        self.pill = Pill()
        head = QHBoxLayout()
        head.addWidget(self.title)
        head.addStretch()
        head.addWidget(self.pill)
        self.body.removeWidget(self.title)
        self.body.addLayout(head)

        self.meeting = QLabel()
        self.meeting.setTextFormat(Qt.TextFormat.PlainText)
        font = self.meeting.font()
        font.setPointSizeF(13)
        font.setWeight(font.Weight.DemiBold)
        self.meeting.setFont(font)
        self.meeting.setWordWrap(True)
        self.detail = QLabel()
        self.detail.setObjectName("Muted")
        self.detail.setWordWrap(True)
        self.body.addWidget(self.meeting)
        self.body.addWidget(self.detail)

        self.open_btn = QPushButton("Open link")
        self.open_btn.clicked.connect(lambda: self.open_link())
        self.in_btn = _accent(QPushButton("I'm in"))
        self.in_btn.setToolTip("Confirm you've been admitted to the meeting.")
        self.in_btn.clicked.connect(lambda: self.confirm_joined())
        self.fail_btn = QPushButton("Couldn't join")
        self.fail_btn.clicked.connect(self._failed)
        self.resume_btn = _accent(QPushButton("Resume automation"))
        self.resume_btn.clicked.connect(self._resume)
        row = QHBoxLayout()
        for b in (self.in_btn, self.open_btn, self.fail_btn, self.resume_btn):
            row.addWidget(b)
        row.addStretch()
        self.body.addLayout(row)

    def show_info(self, info: LiveInfo, now: datetime) -> None:
        self.info = info
        occ = info.occurrence
        status = info.status
        for b in (self.open_btn, self.in_btn, self.fail_btn, self.resume_btn):
            b.hide()

        if info.kind == "paused":
            self.pill.setText("Paused")
            self.pill.set_kind("muted")
            self.meeting.setText("Automation is paused")
            self.detail.setText("No reminders and no links will be opened until you resume.")
            self.resume_btn.show()
            return
        if info.kind == "idle":
            self.pill.setText("No session now")
            self.pill.set_kind("muted")
            nxt = info.next_occurrence
            self.meeting.setText("You're free")
            self.detail.setText(f"Next: {nxt.meeting_title}, {nxt.start:%a %d %b at %H:%M}." if nxt
                                else "No sessions in the next 7 days.")
            return

        has_link = self.ctx.links.current(occ.meeting_id) is not None
        self.meeting.setText(occ.meeting_title)
        when = f"{occ.start:%H:%M}–{occ.end:%H:%M}"
        if info.kind == "soon":
            self.pill.setText(f"Starts in {_minutes(occ.start - now)}")
            self.pill.set_kind("info")
            self.detail.setText(f"{when}. Get ready - you can open the link early.")
            self.open_btn.setVisible(has_link)
            return

        # Live.
        if status == SessionStatus.JOINED:
            self.pill.setText("✓ Joined")
            self.pill.set_kind("accent")
            self.detail.setText(f"{when}. You confirmed you're in the meeting.")
            self.open_btn.setVisible(has_link)
        elif status == SessionStatus.NOT_JOINED:
            self.pill.setText("Couldn't join")
            self.pill.set_kind("danger")
            self.detail.setText(f"{when}. Try the link again or check for a new one.")
            self.open_btn.setVisible(has_link)
            self.in_btn.show()
        elif status == SessionStatus.LINK_OPENED:
            self.pill.setText("Link opened · not confirmed")
            self.pill.set_kind("warn")
            self.detail.setText(f"{when}. Sessionly opened the link but can't see inside the meeting. "
                                "Tap \"I'm in\" once you've been admitted.")
            self.in_btn.show()
            self.fail_btn.show()
            self.open_btn.setVisible(has_link)
        else:
            started = now >= occ.start
            self.pill.setText("In progress" if started else "Starting now")
            self.pill.set_kind("warn")
            self.detail.setText(f"{when}. " + ("Open the link to join." if has_link
                                               else "No meeting link saved for this meeting."))
            self.open_btn.setVisible(has_link)
            self.in_btn.show()

    def open_link(self, occ: Occurrence | None = None) -> None:
        occ = occ or self.info.occurrence
        link = self.ctx.links.current(occ.meeting_id)
        if link and open_meeting(self.ctx, link):
            session = self.ctx.sessions.ensure(occ)
            if session.status in (SessionStatus.SCHEDULED, SessionStatus.REMINDED, SessionStatus.NOT_JOINED):
                self.ctx.sessions.transition(session.id, SessionStatus.LINK_OPENED)
        self.changed.emit()

    def confirm_joined(self, occ: Occurrence | None = None) -> None:
        occ = occ or self.info.occurrence
        self.ctx.sessions.confirm_joined(occ)
        link = self.ctx.links.current(occ.meeting_id)
        if link and link.status != LinkStatus.WORKED:
            self.ctx.links.mark_worked(link.id)  # getting in proves the link works
        self.changed.emit()

    def _failed(self) -> None:
        self.ctx.sessions.mark_not_joined(self.info.occurrence)
        self.changed.emit()
        self.problem.emit(self.info.occurrence)

    def _resume(self) -> None:
        self.ctx.settings.set(AUTOMATION_PAUSED, False)
        self.changed.emit()


class Dashboard(QWidget):
    meeting_selected = Signal(int)
    new_meeting = Signal()
    state_changed = Signal()   # something the tray icon should reflect
    report_problem = Signal(object)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.now_override: datetime | None = None  # tests
        # ---- header ----
        self.greeting = QLabel()
        self.greeting.setObjectName("Muted")
        self.greeting.setTextFormat(Qt.TextFormat.PlainText)
        self.title = QLabel()
        self.title.setObjectName("Title")
        add = _accent(QPushButton("+  New meeting"))
        add.clicked.connect(self.new_meeting.emit)
        prev_btn = QPushButton("‹")
        prev_btn.setToolTip("Previous month (Page Up)")
        prev_btn.setAccessibleName("Previous month")
        prev_btn.clicked.connect(lambda: self._shift_month(-1))
        next_btn = QPushButton("›")
        next_btn.setToolTip("Next month (Page Down)")
        next_btn.setAccessibleName("Next month")
        next_btn.clicked.connect(lambda: self._shift_month(1))
        today_btn = QPushButton("Today")
        today_btn.clicked.connect(self.go_today)
        for b in (prev_btn, next_btn):
            b.setFixedWidth(36)
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(self.greeting)
        title_col.addWidget(self.title)
        header = QHBoxLayout()
        header.addLayout(title_col)
        header.addSpacing(16)
        header.addWidget(add, 0, Qt.AlignmentFlag.AlignBottom)
        header.addStretch()
        for w in (prev_btn, today_btn, next_btn):
            header.addWidget(w, 0, Qt.AlignmentFlag.AlignBottom)

        # ---- calendar ----
        self.month = MonthView()
        self.month.day_selected.connect(self._day_selected)
        self.month.day_activated.connect(self._day_activated)

        # ---- right column ----
        self.live = LiveCard(ctx)
        self.live.changed.connect(self._live_changed)
        self.live.problem.connect(self.report_problem.emit)

        week = Card("This week")
        self.ring = ProgressRing()
        self.week_stats = QLabel()
        self.week_stats.setWordWrap(True)
        wrow = QHBoxLayout()
        wrow.addWidget(self.ring)
        wrow.addSpacing(8)
        wrow.addWidget(self.week_stats, 1)
        week.body.addLayout(wrow)

        self.day_card = Card("Today")
        self.agenda = QListWidget()
        self.agenda.setObjectName("Plain")
        self.agenda.setAccessibleName("Sessions on the selected day")
        self.agenda.setWordWrap(True)
        self.agenda.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.agenda.setMinimumHeight(80)
        self.agenda.setMaximumHeight(170)
        self.agenda.itemActivated.connect(self._activate_item)
        self.day_card.body.addWidget(self.agenda)

        attention = Card("Needs your attention")
        self.attention = QListWidget()
        self.attention.setObjectName("Plain")
        self.attention.setAccessibleName("Needs your attention")
        self.attention.setWordWrap(True)
        self.attention.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.attention.setSpacing(2)
        self.attention.setMinimumHeight(110)
        self.attention.itemActivated.connect(self._activate_item)
        attention.body.addWidget(self.attention)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 4, 0)
        rv.setSpacing(12)
        for w in (self.live, week, self.day_card, attention):
            rv.addWidget(w)
        rv.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(350)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self.month, 1)
        body.addWidget(scroll)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 18, 18)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addLayout(body, 1)

        # Keeps "starts in" / live state accurate while the window is open.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30_000)
        self.refresh()

    # ---- helpers --------------------------------------------------------------------

    def now(self) -> datetime:
        return self.now_override or datetime.now()

    def _shift_month(self, delta: int) -> None:
        y, m = self.month.year, self.month.month + delta
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        self.month.year, self.month.month = y, m
        self.refresh()

    def go_today(self) -> None:
        self.month.select(self.now().date())

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_PageUp:
            self._shift_month(-1)
        elif e.key() == Qt.Key.Key_PageDown:
            self._shift_month(1)
        else:
            super().keyPressEvent(e)

    def _day_selected(self, _d: date) -> None:
        self.refresh()

    def _day_activated(self, d: date) -> None:
        occ = [o for o in self._occurrences if o.start.date() == d]
        if occ:
            self.meeting_selected.emit(occ[0].meeting_id)

    def _activate_item(self, item: QListWidgetItem) -> None:
        meeting_id = item.data(Qt.ItemDataRole.UserRole)
        if meeting_id is not None:
            self.meeting_selected.emit(meeting_id)

    def _live_changed(self) -> None:
        self.refresh()
        self.state_changed.emit()

    # ---- refresh ------------------------------------------------------------------

    def refresh(self) -> None:
        now = self.now()
        today = now.date()
        name = self.ctx.settings.display_name
        part = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening"
        self.greeting.setText(f"Good {part}{', ' + name if name else ''} · {today:%A %d %B}")
        self.title.setText(month_title(self.month.year, self.month.month))

        first, last = self.month.visible_range()
        first = min(first, today - timedelta(days=today.weekday()))
        last = max(last, today + timedelta(days=7))
        self._occurrences = self.ctx.schedules.occurrences(first, last)
        sessions = self.ctx.sessions.between(datetime.combine(first, datetime.min.time()),
                                             datetime.combine(last, datetime.max.time()))

        events: dict[date, list[CalendarEvent]] = {}
        for o in self._occurrences:
            code = o.meeting_title.split(" - ")[0]
            events.setdefault(o.start.date(), []).append(
                CalendarEvent(theme.meeting_colour(o.meeting_id), f"{o.start:%H:%M} {code}", o.cancelled, o.meeting_id))
        self.month.set_month(self.month.year, self.month.month, events)

        self.live.show_info(self.ctx.engine.live(now), now)
        self._fill_week(now, sessions)
        self._fill_agenda(self.month.selected, now, sessions)
        self._fill_attention(now)

    def _fill_week(self, now: datetime, sessions) -> None:
        monday = now.date() - timedelta(days=now.weekday())
        week = [o for o in self._occurrences
                if monday <= o.start.date() < monday + timedelta(days=7) and not o.cancelled]
        held = [o for o in week if o.start <= now]
        joined = sum(1 for o in held if (s := sessions.get((o.meeting_id, o.start))) and s.status == SessionStatus.JOINED)
        self.ring.set_value(joined / len(held) if held else None)
        self.week_stats.setText(
            f"<b>{len(week)}</b> sessions this week<br>"
            f"<span style='color:{theme.ACCENT}'>●</span> {joined} joined (confirmed)<br>"
            f"<span style='color:{theme.MUTED}'>●</span> {len(week) - len(held)} still to come"
        )

    def _fill_agenda(self, day: date, now: datetime, sessions) -> None:
        self.day_card.title.setText("Today" if day == now.date() else f"{day:%A %d %B}")
        self.agenda.clear()
        for o in [o for o in self._occurrences if o.start.date() == day]:
            session = sessions.get((o.meeting_id, o.start))
            state = session.status.label if session and session.status != SessionStatus.SCHEDULED \
                else class_state(o, now)
            if o.note:
                state += f" ({o.note})"
            link = self.ctx.links.current(o.meeting_id)
            link_text = f"{link.platform.label} · {link.status.label}" if link else "No link saved"
            item = QListWidgetItem(_dot(theme.meeting_colour(o.meeting_id) if not o.cancelled else theme.DIM),
                                   f"{o.start:%H:%M}–{o.end:%H:%M}  {o.meeting_title}\n{state} · {link_text}")
            item.setData(Qt.ItemDataRole.UserRole, o.meeting_id)
            if o.cancelled:
                f = item.font()
                f.setStrikeOut(True)
                item.setFont(f)
            self.agenda.addItem(item)
        if self.agenda.count() == 0:
            item = QListWidgetItem("No sessions on this day.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.agenda.addItem(item)

    def _fill_attention(self, now: datetime) -> None:
        self.attention.clear()
        upcoming = [o for o in self._occurrences if now.date() <= o.start.date() <= now.date() + timedelta(days=7)]
        for a, b in find_overlaps(upcoming):
            self._add_attention(f"Overlap {a.start:%a %d %b}: {a.meeting_title} ({a.start:%H:%M}–{a.end:%H:%M}) "
                                f"and {b.meeting_title} ({b.start:%H:%M}–{b.end:%H:%M}). Decide which to attend.",
                                a.meeting_id, theme.WARN)
        for meeting in self.ctx.meetings.list():
            has_classes = bool(self.ctx.schedules.for_meeting(meeting.id))
            link = self.ctx.links.current(meeting.id)
            if link is None and has_classes:
                self._add_attention(f"{meeting.title}: no meeting link saved.", meeting.id, theme.WARN)
            elif link is not None and link.status == LinkStatus.FAILED:
                self._add_attention(f"{meeting.title}: the link needs replacing.", meeting.id, theme.DANGER)
            if not has_classes:
                self._add_attention(f"{meeting.title}: no weekly times entered.", meeting.id, theme.MUTED)
        if self.attention.count() == 0:
            item = QListWidgetItem(_dot(theme.OK), "All good - nothing needs your attention.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.attention.addItem(item)

    def _add_attention(self, text: str, meeting_id: int, colour: str) -> None:
        item = QListWidgetItem(_dot(colour), text)
        item.setData(Qt.ItemDataRole.UserRole, meeting_id)
        item.setToolTip("Press Enter or double-click to open the meeting.")
        self.attention.addItem(item)

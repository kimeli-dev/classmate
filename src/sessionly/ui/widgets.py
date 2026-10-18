"""Custom-painted widgets for the dashboard: month calendar, progress ring, status pill, cards."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QKeyEvent, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from sessionly.ui import theme

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def glyph_icon(code: str, size: int = 22, colour: str = theme.MUTED, checked_colour: str = theme.ACCENT) -> QIcon:
    """Icon from the Windows icon font (Segoe Fluent Icons / MDL2), normal + checked colours."""
    icon = QIcon()
    for col, state in ((colour, QIcon.State.Off), (checked_colour, QIcon.State.On)):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(theme.icon_font(int(size * 0.8)))
        p.setPen(QColor(col))
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, code)
        p.end()
        icon.addPixmap(pix, QIcon.Mode.Normal, state)
        icon.addPixmap(pix, QIcon.Mode.Active, state)
    return icon


class GlassBackdrop(QWidget):
    """Window background for the glass look: a deep gradient with soft colour glows that the
    translucent panels let show through. Rendered once per size into a pixmap, so repaints
    under hovering or scrolling widgets are just a blit."""

    # (relative centre x, y, radius as a share of the larger side, rgb, alpha)
    GLOWS = [
        (0.10, 0.08, 0.50, (212, 242, 122), 58),
        (0.92, 0.22, 0.45, (122, 217, 201), 50),
        (0.55, 1.00, 0.55, (185, 166, 242), 44),
        (0.02, 0.85, 0.32, (142, 197, 242), 30),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)  # we cover every pixel
        self._cache: QPixmap | None = None

    def resizeEvent(self, event) -> None:
        self._cache = None
        super().resizeEvent(event)

    def _render(self) -> QPixmap:
        ratio = self.devicePixelRatioF()
        pix = QPixmap(int(self.width() * ratio), int(self.height() * ratio))
        pix.setDevicePixelRatio(ratio)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0, QColor("#0E1A14"))
        base.setColorAt(1, QColor(theme.BG))
        p.fillRect(QRectF(0, 0, w, h), base)
        side = max(w, h)
        for cx, cy, rad, rgb, alpha in self.GLOWS:
            g = QRadialGradient(QPointF(cx * w, cy * h), rad * side)
            g.setColorAt(0.0, QColor(*rgb, alpha))
            g.setColorAt(0.6, QColor(*rgb, alpha // 3))
            g.setColorAt(1.0, QColor(*rgb, 0))
            p.fillRect(QRectF(0, 0, w, h), g)
        p.end()
        return pix

    def paintEvent(self, _event) -> None:
        if self._cache is None or self._cache.devicePixelRatio() != self.devicePixelRatioF():
            self._cache = self._render()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)  # Qt clips to the dirty region
        p.end()


class Card(QFrame):
    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(8)
        if title:
            self.title = QLabel(title)
            self.title.setObjectName("CardTitle")
            self.body.addWidget(self.title)


class Pill(QLabel):
    """Small rounded status label."""

    STYLES = {
        "accent": (theme.ACCENT, theme.ACCENT_TEXT),
        "warn": ("rgba(242, 196, 107, 40)", theme.WARN),
        "danger": ("rgba(242, 139, 130, 40)", theme.DANGER),
        "info": ("rgba(142, 197, 242, 36)", "#8EC5F2"),
        "muted": (theme.rgba(theme.GLASS_HI), theme.MUTED),
        "ok": ("rgba(155, 224, 122, 36)", theme.OK),
    }

    def __init__(self, text: str = "", kind: str = "muted", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.set_kind(kind)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_kind(self, kind: str) -> None:
        bg, fg = self.STYLES[kind]
        self.setStyleSheet(f"background: {bg}; color: {fg}; border-radius: 10px; padding: 3px 10px;"
                           f" font-size: 8.5pt; font-weight: 600;")


class ProgressRing(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.value: float | None = None
        self.setFixedSize(96, 96)

    def set_value(self, value: float | None) -> None:
        self.value = value
        self.setAccessibleName(f"{round(value * 100)} percent" if value is not None else "No data")
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = 9
        r = QRectF(w / 2 + 2, w / 2 + 2, self.width() - w - 4, self.height() - w - 4)
        p.setPen(QPen(QColor(*theme.GLASS_HI), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawEllipse(r)
        if self.value:
            p.setPen(QPen(QColor(theme.ACCENT), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(r, 90 * 16, -int(360 * 16 * min(self.value, 1.0)))
        font = QFont(self.font())
        font.setPointSizeF(15)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(theme.TEXT))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                   f"{round(self.value * 100)}%" if self.value is not None else "—")
        p.end()


@dataclass
class CalendarEvent:
    colour: str
    text: str
    cancelled: bool = False
    meeting_id: int | None = None


class MonthView(QWidget):
    """Month grid of rounded day tiles with coloured session chips. Keyboard: arrows move, Enter opens."""

    day_selected = Signal(date)
    day_activated = Signal(date)

    GAP = 6
    HEADER = 26

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(560, 420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Month calendar")
        today = date.today()
        self.year, self.month = today.year, today.month
        self.selected = today
        self.events: dict[date, list[CalendarEvent]] = {}
        self._hover: date | None = None

    def sizeHint(self) -> QSize:
        return QSize(720, 520)

    # ---- data ---------------------------------------------------------------------

    def set_month(self, year: int, month: int, events: dict[date, list[CalendarEvent]]) -> None:
        self.year, self.month, self.events = year, month, events
        self.update()

    def days(self) -> list[date]:
        first = date(self.year, self.month, 1)
        start = first - timedelta(days=first.weekday())
        return [start + timedelta(days=i) for i in range(42)]

    def visible_range(self) -> tuple[date, date]:
        d = self.days()
        return d[0], d[-1]

    # ---- geometry -------------------------------------------------------------------

    def _cell_rect(self, index: int) -> QRectF:
        cols, rows = 7, 6
        w = (self.width() - self.GAP * (cols - 1)) / cols
        h = (self.height() - self.HEADER - self.GAP * (rows - 1)) / rows
        r, c = divmod(index, 7)
        return QRectF(c * (w + self.GAP), self.HEADER + r * (h + self.GAP), w, h)

    def _day_at(self, pos: QPointF) -> date | None:
        for i, d in enumerate(self.days()):
            if self._cell_rect(i).contains(pos):
                return d
        return None

    # ---- painting -------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QFont(self.font())
        small = QFont(base)
        small.setPointSizeF(8.5)
        bold = QFont(base)
        bold.setPointSizeF(9.5)
        bold.setWeight(QFont.Weight.DemiBold)
        today = date.today()

        p.setFont(small)
        p.setPen(QColor(theme.MUTED))
        for c, name in enumerate(WEEKDAYS):
            r = self._cell_rect(c)
            p.drawText(QRectF(r.left(), 0, r.width(), self.HEADER - 6), Qt.AlignmentFlag.AlignCenter, name)

        fm = QFontMetrics(small)
        line_h = fm.height() + 3
        for i, d in enumerate(self.days()):
            r = self._cell_rect(i)
            in_month = d.month == self.month
            path = QPainterPath()
            path.addRoundedRect(r, 12, 12)
            fill = theme.GLASS_CARD if in_month else theme.GLASS_FIELD
            if d == self.selected:
                fill = theme.GLASS_HI
            elif d == self._hover:
                fill = theme.GLASS_HOVER
            p.fillPath(path, QColor(*fill))
            p.setBrush(Qt.BrushStyle.NoBrush)  # chip dots below set a brush; don't let it fill tiles
            if d == today:
                p.setPen(QPen(QColor(theme.ACCENT), 1.6))
            elif d == self.selected and self.hasFocus():
                p.setPen(QPen(QColor(theme.MUTED), 1.2))
            else:
                p.setPen(QPen(QColor(*theme.GLASS_BORDER), 1))
            p.drawPath(path)

            # Day number - today gets a lime disc like the reference design.
            num_rect = QRectF(r.right() - 30, r.top() + 6, 24, 22)
            p.setFont(bold)
            if d == today:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(theme.ACCENT))
                p.drawEllipse(num_rect.center(), 11, 11)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QColor(theme.ACCENT_TEXT))
            else:
                p.setPen(QColor(theme.TEXT if in_month else theme.DIM))
            p.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, str(d.day))

            events = self.events.get(d, [])
            if not events:
                continue
            p.setFont(small)
            top = r.top() + 30
            capacity = max(0, int((r.bottom() - 6 - top) // line_h))
            shown = events if len(events) <= capacity else events[:max(0, capacity - 1)]
            for ev in shown:
                row = QRectF(r.left() + 8, top, r.width() - 14, line_h)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(ev.colour if not ev.cancelled else theme.DIM))
                p.drawEllipse(QPointF(row.left() + 3, row.center().y()), 3, 3)
                f = QFont(small)
                f.setStrikeOut(ev.cancelled)
                p.setFont(f)
                p.setPen(QColor(theme.DIM if ev.cancelled or not in_month else theme.TEXT))
                text = fm.elidedText(ev.text, Qt.TextElideMode.ElideRight, int(row.width() - 12))
                p.drawText(row.adjusted(10, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
                top += line_h
            if len(shown) < len(events):
                p.setFont(small)
                p.setPen(QColor(theme.MUTED))
                p.drawText(QRectF(r.left() + 18, top, r.width() - 20, line_h),
                           Qt.AlignmentFlag.AlignVCenter, f"+{len(events) - len(shown)} more")
        p.end()

    # ---- interaction ----------------------------------------------------------------

    def select(self, d: date) -> None:
        self.selected = d
        if (d.year, d.month) != (self.year, self.month):
            self.year, self.month = d.year, d.month
        self.update()
        self.day_selected.emit(d)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if (d := self._day_at(e.position())) is not None:
            self.select(d)

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if (d := self._day_at(e.position())) is not None:
            self.day_activated.emit(d)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        d = self._day_at(e.position())
        if d != self._hover:
            self._hover = d
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = None
        self.update()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -7, Qt.Key.Key_Down: 7}.get(e.key())
        if step:
            self.select(self.selected + timedelta(days=step))
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.day_activated.emit(self.selected)
        else:
            super().keyPressEvent(e)


def month_title(year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"

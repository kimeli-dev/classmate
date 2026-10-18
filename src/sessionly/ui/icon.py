"""The Sessionly icon, drawn in code so the tray can add live status badges.

Design: a lime squircle (the app's accent) holding a dark calendar page whose body is
a check mark - "your sessions, handled". The check doubles as the join-confirmed symbol.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from sessionly.ui import theme

INK = QColor("#0F2A1C")

# Badge colours for tray states.
BADGES = {
    "soon": QColor("#8EC5F2"),     # sky: a session starts within the hour
    "live": QColor("#2EE05A"),     # bright green: the meeting is on right now
    "joined": QColor("#2EE05A"),   # green with a check: you confirmed you're in
}
# The "meeting is on" dot is drawn larger so it stands out in the 16 px hidden-icons tray.
BADGE_RADIUS = {"live": 0.27, "joined": 0.25}


def paint_icon(p: QPainter, size: float, badge: str | None = None, paused: bool = False) -> None:
    s = size
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Squircle background with a soft diagonal gradient.
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(0.02 * s, 0.02 * s, 0.96 * s, 0.96 * s), 0.26 * s, 0.26 * s)
    grad = QLinearGradient(0, 0, s, s)
    if paused:
        grad.setColorAt(0, QColor("#B7C2BB"))
        grad.setColorAt(1, QColor("#7D8A82"))
    else:
        grad.setColorAt(0, QColor("#E6FA9E"))
        grad.setColorAt(1, QColor("#A6D650"))
    p.fillPath(bg, QBrush(grad))
    # Gloss highlight across the top for depth.
    gloss = QLinearGradient(0, 0, 0, s * 0.5)
    gloss.setColorAt(0, QColor(255, 255, 255, 70))
    gloss.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillPath(bg, QBrush(gloss))

    tiny = s < 24  # simplify for 16-20 px tray sizes
    stroke = max(1.6, (0.085 if tiny else 0.07) * s)
    pen = QPen(INK, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

    # Calendar page.
    body = QRectF(0.22 * s, 0.28 * s, 0.56 * s, 0.50 * s)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(body, 0.09 * s, 0.09 * s)
    # Header band.
    header = QPainterPath()
    header.addRoundedRect(QRectF(body.left(), body.top(), body.width(), 0.14 * s), 0.09 * s, 0.09 * s)
    header.addRect(QRectF(body.left(), body.top() + 0.07 * s, body.width(), 0.07 * s))
    p.fillPath(header, INK)
    if not tiny:
        # Binder rings.
        ring_pen = QPen(INK, stroke * 0.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(ring_pen)
        for x in (0.37, 0.63):
            p.drawLine(QPointF(x * s, 0.19 * s), QPointF(x * s, 0.30 * s))
    # Check mark inside the page.
    p.setPen(pen)
    check = QPainterPath(QPointF(0.36 * s, 0.58 * s))
    check.lineTo(0.46 * s, 0.68 * s)
    check.lineTo(0.65 * s, 0.49 * s)
    p.drawPath(check)

    if badge in BADGES:
        r = BADGE_RADIUS.get(badge, 0.21) * s
        centre = QPointF(s - r - 0.01 * s, s - r - 0.01 * s)
        p.setPen(QPen(QColor(theme.BG), max(1.0, 0.05 * s)))
        p.setBrush(BADGES[badge])
        p.drawEllipse(centre, r, r)
        if badge == "joined" and s >= 20:
            p.setPen(QPen(QColor("#0B2410"), max(1.2, 0.05 * s), Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            tick = QPainterPath(QPointF(centre.x() - 0.45 * r, centre.y()))
            tick.lineTo(centre.x() - 0.1 * r, centre.y() + 0.35 * r)
            tick.lineTo(centre.x() + 0.5 * r, centre.y() - 0.35 * r)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(tick)


def icon_pixmap(size: int, badge: str | None = None, paused: bool = False) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    paint_icon(p, size, badge, paused)
    p.end()
    return pix


def app_icon(badge: str | None = None, paused: bool = False) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(icon_pixmap(size, badge, paused))
    return icon

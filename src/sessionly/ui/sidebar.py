"""Glassmorphic vertical navigation.

A frosted-glass panel (translucent fill, light-catching gradient edge, gloss and a soft shadow)
over the window's colour glows. The active page is marked by a glowing lime glass pill with a
neon accent bar that glides between items; hovered items get a faint frosted highlight.
Everything is painted here, so the nav buttons themselves stay transparent.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, Qt, Property
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget

LIME = (212, 242, 122)
TEAL = (122, 217, 201)
SHADOW = 10        # px reserved around the panel for its shadow
RADIUS = 24.0
PILL_RADIUS = 18.0


def _rgba(rgb: tuple[int, int, int], alpha: int) -> QColor:
    return QColor(*rgb, alpha)


class GlassSidebar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAccessibleName("Navigation")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(SHADOW + 8, SHADOW + 14, SHADOW + 8, SHADOW + 14)
        self.layout_.setSpacing(8)
        self.buttons: list[QToolButton] = []
        self._active: QToolButton | None = None
        self._hover: QToolButton | None = None
        self._pill = QRectF()
        self._anim = QPropertyAnimation(self, b"pill", self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ---- the animated pill ----------------------------------------------------------

    def _get_pill(self) -> QRectF:
        return self._pill

    def _set_pill(self, rect: QRectF) -> None:
        self._pill = QRectF(rect)
        self.update()

    pill = Property(QRectF, _get_pill, _set_pill)

    def _target(self, button: QToolButton) -> QRectF:
        return QRectF(button.geometry()).adjusted(-4, -2, 4, 2)

    def set_active(self, button: QToolButton, animate: bool = True) -> None:
        self._active = button
        target = self._target(button)
        if animate and not self._pill.isNull() and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._pill)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_pill(target)

    # ---- items ----------------------------------------------------------------------

    def add_button(self, button: QToolButton) -> None:
        button.installEventFilter(self)
        self.buttons.append(button)
        self.layout_.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Enter and obj in self.buttons:
            self._hover = obj
            self.update()
        elif event.type() == QEvent.Type.Leave and obj is self._hover:
            self._hover = None
            self.update()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._active is not None:  # keep the pill on its item when the layout moves
            self._anim.stop()
            self._set_pill(self._target(self._active))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._active is not None:
            self._set_pill(self._target(self._active))

    # ---- painting ---------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel = QRectF(self.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)
        self._paint_shadow(p, panel)
        self._paint_glass(p, panel)
        if self._hover is not None and self._hover is not self._active:
            self._paint_hover(p, self._target(self._hover))
        if not self._pill.isNull():
            self._paint_pill(p, self._pill)
        p.end()

    def _paint_shadow(self, p: QPainter, panel: QRectF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(SHADOW, 0, -2):  # stacked translucent layers = soft blur
            path = QPainterPath()
            path.addRoundedRect(panel.adjusted(-i, -i + 4, i, i + 4), RADIUS + i, RADIUS + i)
            p.fillPath(path, QColor(0, 0, 0, 7))

    def _paint_glass(self, p: QPainter, panel: QRectF) -> None:
        path = QPainterPath()
        path.addRoundedRect(panel, RADIUS, RADIUS)
        # Frosted body: brighter at the top, a hint of lime/teal tint, mostly see-through.
        body = QLinearGradient(panel.topLeft(), panel.bottomRight())
        body.setColorAt(0.0, QColor(255, 255, 255, 34))
        body.setColorAt(0.45, _rgba(LIME, 12))
        body.setColorAt(1.0, _rgba(TEAL, 10))
        p.fillPath(path, body)
        # Gloss: a diagonal sheen over the upper part of the panel.
        gloss = QLinearGradient(panel.topLeft(), QPointF(panel.right(), panel.top() + panel.height() * 0.35))
        gloss.setColorAt(0.0, QColor(255, 255, 255, 30))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, gloss)
        # Light-catching edge: bright at the top, fading down.
        edge = QLinearGradient(panel.topLeft(), panel.bottomLeft())
        edge.setColorAt(0.0, QColor(255, 255, 255, 90))
        edge.setColorAt(0.5, QColor(255, 255, 255, 28))
        edge.setColorAt(1.0, QColor(255, 255, 255, 14))
        p.setPen(QPen(edge, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def _paint_hover(self, p: QPainter, rect: QRectF) -> None:
        path = QPainterPath()
        path.addRoundedRect(rect, PILL_RADIUS, PILL_RADIUS)
        p.fillPath(path, QColor(255, 255, 255, 16))
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawPath(path)

    def _paint_pill(self, p: QPainter, rect: QRectF) -> None:
        # Halo behind the pill.
        halo = QRadialGradient(rect.center(), rect.width() * 0.85)
        halo.setColorAt(0.0, _rgba(LIME, 70))
        halo.setColorAt(0.55, _rgba(LIME, 22))
        halo.setColorAt(1.0, _rgba(LIME, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(rect.center(), rect.width() * 0.85, rect.height() * 0.85)

        path = QPainterPath()
        path.addRoundedRect(rect, PILL_RADIUS, PILL_RADIUS)
        fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
        fill.setColorAt(0.0, _rgba(LIME, 78))
        fill.setColorAt(1.0, _rgba(TEAL, 34))
        p.fillPath(path, fill)
        shine = QLinearGradient(rect.topLeft(), rect.bottomLeft())  # glassy top highlight
        shine.setColorAt(0.0, QColor(255, 255, 255, 60))
        shine.setColorAt(0.45, QColor(255, 255, 255, 0))
        p.fillPath(path, shine)
        p.setPen(QPen(_rgba(LIME, 190), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Neon accent bar on the panel's left edge, with a glow.
        bar = QRectF(SHADOW + 3, rect.center().y() - 14, 4, 28)
        for spread, alpha in ((7, 30), (4, 60), (2, 110)):
            glow = QPainterPath()
            glow.addRoundedRect(bar.adjusted(-spread, -spread, spread, spread), 4 + spread, 4 + spread)
            p.fillPath(glow, _rgba(LIME, alpha))
        solid = QPainterPath()
        solid.addRoundedRect(bar, 2, 2)
        p.fillPath(solid, _rgba(LIME, 255))

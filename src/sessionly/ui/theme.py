"""Dark forest-green glass theme with a lime accent: frosted translucent panels over a softly
glowing backdrop (see ``widgets.GlassBackdrop``), rounded cards, one bright colour."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0B1410"
SURFACE = "#101C16"
CARD = "#16241D"
CARD_HI = "#1F3128"
FIELD = "#0F1A15"
BORDER = "#25392F"
TEXT = "#E8F0EA"
MUTED = "#8DA295"
DIM = "#55695D"
ACCENT = "#D4F27A"
ACCENT_TEXT = "#10200F"
WARN = "#F2C46B"
DANGER = "#F28B82"
OK = "#9BE07A"

# Glassmorphism: panels are translucent (r, g, b, alpha 0-255) over the glowing GlassBackdrop
# behind the main window, with thin light edges. Pop-ups (menus, tooltips, combo lists) are
# separate windows with nothing behind them, so they stay solid.
GLASS_CARD = (30, 50, 40, 115)
GLASS_HI = (60, 90, 74, 120)
GLASS_FIELD = (10, 20, 15, 95)
GLASS_HOVER = (45, 70, 57, 125)
GLASS_BORDER = (255, 255, 255, 30)
GLASS_EDGE = (255, 255, 255, 46)   # slightly brighter rim for raised panels


def rgba(c: tuple[int, int, int, int]) -> str:
    return f"rgba({c[0]}, {c[1]}, {c[2]}, {c[3]})"


# Raised panel fill: lighter at the top like light catching frosted glass.
PANEL = ("qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(52, 80, 65, 135), "
         "stop:1 rgba(20, 34, 27, 105))")
DIALOG_BG = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #15281E, stop:1 {BG})"

# Per-meeting colours for calendar chips (cycled by meeting id).
MEETING_COLOURS = ["#D4F27A", "#7AD9C9", "#B9A6F2", "#F2C46B", "#F29C82", "#8EC5F2", "#E7A6D8"]

ICON_FONTS = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]


def meeting_colour(meeting_id: int) -> str:
    return MEETING_COLOURS[(meeting_id - 1) % len(MEETING_COLOURS)]


STYLESHEET = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI"; font-size: 10pt; }}
QWidget {{ color: {TEXT}; }}
QMainWindow {{ background: {BG}; }}
QDialog, QWizard, QWizardPage, QMessageBox {{ background: {DIALOG_BG}; }}
QFrame#Content {{ background: rgba(12, 22, 17, 105); border: 1px solid {rgba(GLASS_BORDER)}; border-radius: 18px; }}
QFrame#Sidebar {{ background: rgba(255, 255, 255, 10); border: 1px solid {rgba(GLASS_BORDER)}; border-radius: 18px; }}
QFrame#Card {{ background: {PANEL}; border: 1px solid {rgba(GLASS_EDGE)}; border-radius: 16px; }}
QLabel {{ background: transparent; }}
QLabel#Title {{ font-size: 22pt; font-weight: 600; }}
QLabel#CardTitle {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#Muted {{ color: {MUTED}; }}
QGroupBox {{ background: {PANEL}; border: 1px solid {rgba(GLASS_EDGE)}; border-radius: 14px; margin-top: 18px;
             padding: 12px 10px 10px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 4px; color: {MUTED}; }}
QGroupBox::indicator {{ width: 14px; height: 14px; border-radius: 4px; border: 1.5px solid {MUTED};
                        background: {rgba(GLASS_FIELD)}; }}
QGroupBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QPushButton {{ background: rgba(255, 255, 255, 16); border: 1px solid {rgba(GLASS_EDGE)}; border-radius: 10px;
               padding: 6px 14px; }}
QPushButton:hover {{ background: rgba(255, 255, 255, 28); border-color: {ACCENT}; }}
QPushButton:pressed {{ background: rgba(255, 255, 255, 8); }}
QPushButton:focus {{ border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ color: {DIM}; background: rgba(255, 255, 255, 6); border-color: {rgba(GLASS_BORDER)}; }}
QPushButton[accent="true"] {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E6FA9E, stop:1 {ACCENT});
    color: {ACCENT_TEXT}; border: 1px solid rgba(255, 255, 255, 90); font-weight: 600; }}
QPushButton[accent="true"]:hover {{ background: #E8FBA6; }}
QPushButton[flat="true"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[flat="true"]:hover {{ border-color: {rgba(GLASS_EDGE)}; }}

/* Sidebar buttons are transparent: GlassSidebar paints the hover glass and the gliding active pill. */
QToolButton#Nav {{ background: transparent; border: 1px solid transparent; border-radius: 16px; color: {MUTED};
                   padding: 8px 4px; font-size: 8.5pt; }}
QToolButton#Nav:hover {{ color: {TEXT}; }}
QToolButton#Nav:checked {{ color: #FFFFFF; font-weight: 600; }}
QToolButton#Nav:focus {{ border: 1px solid rgba(255, 255, 255, 70); }}
QToolButton#DayToggle {{ background: {FIELD}; border: 1px solid {BORDER}; border-radius: 9px;
                         min-width: 34px; min-height: 28px; color: {MUTED}; font-weight: 600; }}
QToolButton#DayToggle:hover {{ border-color: {ACCENT}; color: {TEXT}; }}
QToolButton#DayToggle:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: {ACCENT_TEXT}; }}

QLineEdit, QComboBox, QSpinBox, QTimeEdit, QDateEdit, QDateTimeEdit, QPlainTextEdit {{
    background: {rgba(GLASS_FIELD)}; border: 1px solid {rgba(GLASS_EDGE)}; border-radius: 9px; padding: 5px 8px;
    selection-background-color: {ACCENT}; selection-color: {ACCENT_TEXT}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus, QDateEdit:focus, QDateTimeEdit:focus,
QPlainTextEdit:focus {{ border-color: {ACCENT}; background: rgba(10, 20, 15, 140); }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER}; selection-background-color: {CARD_HI}; }}

QTableWidget, QTreeWidget, QListWidget {{ background: {rgba(GLASS_FIELD)}; border: 1px solid {rgba(GLASS_BORDER)};
    border-radius: 12px; alternate-background-color: rgba(255, 255, 255, 6); gridline-color: {rgba(GLASS_BORDER)};
    outline: none; }}
QTableWidget::item, QListWidget::item {{ padding: 4px; border-radius: 6px; }}
QListWidget::item:hover {{ background: rgba(255, 255, 255, 12); }}
QTableWidget::item:selected, QListWidget::item:selected, QTreeWidget::item:selected {{
    background: rgba(212, 242, 122, 38); color: {TEXT}; }}
QListWidget#Plain {{ background: transparent; border: none; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: rgba(255, 255, 255, 10); color: {MUTED}; border: none;
    border-bottom: 1px solid {rgba(GLASS_BORDER)}; padding: 6px; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QSplitter > QWidget, QStackedWidget, QStackedWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255, 255, 255, 40); border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(255, 255, 255, 40); border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: rgba(212, 242, 122, 110); }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; background: {rgba(GLASS_FIELD)};
    border: 1.5px solid {MUTED}; }}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
    stop:0 {ACCENT}, stop:0.45 {ACCENT}, stop:0.55 {FIELD}, stop:1 {FIELD}); border-color: {ACCENT}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {DIM}; }}

QToolTip {{ background: {CARD_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {CARD_HI}; }}
QMenu::item:disabled {{ color: {MUTED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ background: transparent; color: {MUTED}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")  # draws check boxes, radios and spin arrows consistently from the palette
    pal = QPalette()
    for role, colour in [
        (QPalette.ColorRole.Window, SURFACE), (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, FIELD), (QPalette.ColorRole.AlternateBase, "#132019"),
        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, CARD_HI),
        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, ACCENT_TEXT), (QPalette.ColorRole.ToolTipBase, CARD_HI),
        (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, DIM),
        (QPalette.ColorRole.Link, ACCENT), (QPalette.ColorRole.Mid, BORDER), (QPalette.ColorRole.Dark, BG),
    ]:
        pal.setColor(role, QColor(colour))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(DIM))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(DIM))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(DIM))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)


def icon_font(pixel_size: int) -> QFont:
    font = QFont()
    font.setFamilies(ICON_FONTS)
    font.setPixelSize(pixel_size)
    return font

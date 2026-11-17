"""مظهر البرنامج: الخط والألوان والاتجاه من اليمين إلى اليسار."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPalette, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication

PREFERRED_FONTS = ["Segoe UI", "Tahoma", "Noto Sans Arabic", "Arial", "DejaVu Sans"]
BASE_POINT_SIZE = 11

PRIMARY = "#1565c0"
PRIMARY_DARK = "#0d47a1"
ERROR = "#d32f2f"

QSS = f"""
QWidget {{ color: #1f2933; }}
QMainWindow, QDialog {{ background: #f4f6f9; }}
QWidget#page {{ background: #f4f6f9; }}

QFrame#sidebar {{ background: #0d3c61; }}
QPushButton#navButton {{
    background: transparent; color: #e3edf7; border: none; text-align: right;
    padding: 12px 18px; font-size: {BASE_POINT_SIZE + 1}pt; border-radius: 6px;
}}
QPushButton#navButton:hover {{ background: #15507e; }}
QPushButton#navButton:checked {{ background: #ffffff; color: #0d3c61; font-weight: bold; }}
QLabel#appTitle {{ color: #ffffff; font-size: {BASE_POINT_SIZE + 3}pt; font-weight: bold; }}
QLabel#appSubtitle {{ color: #b9cde0; font-size: {BASE_POINT_SIZE - 1}pt; }}

QLabel#pageTitle {{ font-size: {BASE_POINT_SIZE + 5}pt; font-weight: bold; color: #0d3c61; }}
QLabel#hint {{ color: #5f6b7a; }}
QLabel#okText {{ color: #1b5e20; }}
QLabel#errorText {{ color: {ERROR}; }}

QGroupBox {{
    background: #ffffff; border: 1px solid #d5dde7; border-radius: 8px;
    margin-top: 16px; padding: 14px 10px 10px 10px; font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top right; right: 12px;
    padding: 0 6px; color: #0d3c61; font-size: {BASE_POINT_SIZE + 1}pt;
}}
QGroupBox:disabled {{ background: #f0f2f5; }}
QGroupBox QLabel {{ font-weight: normal; }}

QLineEdit, QComboBox, QPlainTextEdit, QSpinBox {{
    background: #ffffff; border: 1px solid #b8c4d2; border-radius: 5px; padding: 5px 7px;
    min-height: 22px; selection-background-color: {PRIMARY};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border: 2px solid {PRIMARY}; }}
QLineEdit:disabled, QComboBox:disabled {{ background: #eceff3; color: #8a96a3; }}
QLineEdit[error="true"], QComboBox[error="true"], QPlainTextEdit[error="true"], QWidget[error="true"] {{
    border: 2px solid {ERROR}; background: #fff5f5;
}}
QComboBox QAbstractItemView {{ selection-background-color: {PRIMARY}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center left; width: 26px; border: none; }}
QComboBox::down-arrow {{ image: url(__ARROW__); width: 12px; height: 8px; }}
QComboBox::down-arrow:disabled {{ image: url(__ARROW_OFF__); }}

QPushButton {{
    background: #ffffff; border: 1px solid #aebbc9; border-radius: 6px; padding: 7px 16px;
}}
QPushButton:hover {{ background: #eef4fb; }}
QPushButton:disabled {{ color: #9aa5b1; background: #f1f3f5; }}
QPushButton#primary {{ background: {PRIMARY}; color: #ffffff; border: none; font-weight: bold; }}
QPushButton#primary:hover {{ background: {PRIMARY_DARK}; }}
QPushButton#danger {{ color: {ERROR}; border-color: #e3a3a3; }}
QPushButton#newOrder {{
    background: #2e7d32; color: #ffffff; border: none; font-weight: bold;
    padding: 12px; font-size: {BASE_POINT_SIZE + 1}pt;
}}
QPushButton#newOrder:hover {{ background: #1b5e20; }}

QTableWidget, QTableView {{
    background: #ffffff; alternate-background-color: #f7f9fc; gridline-color: #e1e7ef;
    border: 1px solid #d5dde7; selection-background-color: #cfe3fa; selection-color: #0b1f33;
}}
QHeaderView::section {{
    background: #e4ebf3; padding: 6px; border: none; border-left: 1px solid #d0d9e4;
    font-weight: bold; color: #0d3c61;
}}

QFrame#card {{ background: #ffffff; border: 1px solid #d5dde7; border-radius: 10px; }}
QFrame#card:hover {{ border: 2px solid {PRIMARY}; }}
QLabel#cardNumber {{ font-size: 26pt; font-weight: bold; }}
QLabel#cardLabel {{ color: #3b4754; }}

QLabel#statusChip {{ border-radius: 10px; padding: 4px 12px; font-weight: bold; }}
QTabWidget::pane {{ border: 1px solid #d5dde7; background: #ffffff; border-radius: 6px; }}
QTabBar::tab {{ padding: 8px 18px; background: #e4ebf3; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-left: 2px; }}
QTabBar::tab:selected {{ background: #ffffff; font-weight: bold; color: #0d3c61; }}
QTextBrowser {{ background: #ffffff; border: 1px solid #d5dde7; }}
QListWidget#reportList {{ background: #ffffff; border: 1px solid #d5dde7; border-radius: 6px; }}
QListWidget#reportList::item {{ padding: 8px; }}
QListWidget#reportList::item:selected {{ background: #cfe3fa; color: #0b1f33; }}
QCheckBox {{ spacing: 8px; }}
QToolTip {{ background: #fffde7; color: #1f2933; border: 1px solid #c9b458; }}
"""


def _arrow_image(color: str, name: str) -> str:
    """رسم سهم القائمة المنسدلة وحفظه مؤقتاً لاستخدامه في ملف التنسيق."""
    folder = Path(tempfile.gettempdir()) / "workorders_ui"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    pm = QPixmap(24, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPolygon(QPolygonF([QPointF(2, 3), QPointF(22, 3), QPointF(12, 14)]))
    p.end()
    pm.save(str(path), "PNG")
    return path.as_posix()


def pick_font_family() -> str:
    families = set(QFontDatabase.families())
    for name in PREFERRED_FONTS:
        if name in families:
            return name
    return QApplication.font().family()


def apply_style(app: QApplication) -> str:
    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.RightToLeft)
    try:  # إجبار المظهر الفاتح حتى لو كان الويندوز بالوضع الداكن
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#f4f6f9"))
    palette.setColor(QPalette.WindowText, QColor("#1f2933"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#f7f9fc"))
    palette.setColor(QPalette.Text, QColor("#1f2933"))
    palette.setColor(QPalette.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ButtonText, QColor("#1f2933"))
    palette.setColor(QPalette.Highlight, QColor(PRIMARY))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor("#fffde7"))
    palette.setColor(QPalette.ToolTipText, QColor("#1f2933"))
    palette.setColor(QPalette.PlaceholderText, QColor("#8a96a3"))
    app.setPalette(palette)
    family = pick_font_family()
    font = QFont(family, BASE_POINT_SIZE)
    app.setFont(font)
    qss = QSS.replace("__ARROW__", _arrow_image("#3d4f63", "arrow"))
    qss = qss.replace("__ARROW_OFF__", _arrow_image("#a7b1bc", "arrow_off"))
    app.setStyleSheet(qss)
    return family


def set_error(widget, on: bool) -> None:
    """تلوين الحقل بالأحمر عند وجود خطأ."""
    if widget.property("error") == on:
        return
    widget.setProperty("error", on)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()

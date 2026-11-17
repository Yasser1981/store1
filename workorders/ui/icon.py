"""أيقونة البرنامج مرسومة برمجياً (ملف أمر عمل مع رمز الكهرباء)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


def draw_icon(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    s = size / 256
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    # الخلفية
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0d3c61"))
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 44 * s, 44 * s)
    # الورقة
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(58 * s, 36 * s, 140 * s, 184 * s), 14 * s, 14 * s)
    p.setPen(QPen(QColor("#b9cde0"), 9 * s, Qt.SolidLine, Qt.RoundCap))
    for y in (78, 104, 130):
        p.drawLine(QPointF(84 * s, y * s), QPointF(172 * s, y * s))
    # رمز الكهرباء
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#f9a825"))
    bolt = QPolygonF([QPointF(x * s, y * s) for x, y in
                      [(142, 136), (100, 196), (128, 196), (114, 240), (170, 170), (140, 170), (156, 136)]])
    p.drawPolygon(bolt)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(draw_icon(size))
    return icon

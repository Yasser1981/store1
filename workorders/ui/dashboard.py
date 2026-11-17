"""الشاشة الرئيسية: ملخص سريع بأعداد أوامر العمل حسب الحالة."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..constants import ORDER_TYPES, STATUS_COLORS, STATUS_LABELS
from ..models import compute_status, rolled_to_year
from ..reports import OrderFilter
from ..repository import Repository
from ..validation import allowed_years
from .widgets import combo_value, make_combo


def _wrap(text: str, width: int = 14) -> str:
    """تقسيم عنوان العمود الطويل إلى عدة أسطر."""
    lines, current = [], ""
    for word in text.replace("–", "").split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return "\n".join(lines)


class Card(QFrame):
    clicked = Signal()

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(110)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.number = QLabel("0")
        self.number.setObjectName("cardNumber")
        self.number.setStyleSheet(f"color: {color};")
        self.number.setAlignment(Qt.AlignCenter)
        self.label = QLabel(label)
        self.label.setObjectName("cardLabel")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        bar = QFrame()
        bar.setFixedHeight(4)
        bar.setStyleSheet(f"background: {color}; border-radius: 2px;")
        lay.addWidget(bar)
        lay.addWidget(self.number)
        lay.addWidget(self.label)
        self.setToolTip("انقر لعرض أوامر العمل")

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class DashboardPage(QWidget):
    open_list = Signal(object)  # OrderFilter

    def __init__(self, repo: Repository, today: date, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.today = today
        self.setObjectName("page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(14)

        top = QHBoxLayout()
        title = QLabel("الرئيسية – ملخص أوامر العمل")
        title.setObjectName("pageTitle")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(QLabel("السنة:"))
        self.year_combo = make_combo([(None, "كل السنوات")] + [(y, str(y)) for y in allowed_years(today)])
        self.year_combo.setCurrentIndex(0)
        self.year_combo.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.year_combo)
        lay.addLayout(top)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards: dict[str, Card] = {}
        specs = [("total", "إجمالي أوامر العمل", "#0d3c61")]
        specs += [(code, label, STATUS_COLORS[code][0]) for code, label in STATUS_LABELS.items()]
        specs += [("rolled", "المدوّرة", "#6a1b9a")]
        for i, (key, label, color) in enumerate(specs):
            card = Card(label, color)
            card.clicked.connect(lambda k=key: self._card_clicked(k))
            self.cards[key] = card
            grid.addWidget(card, i // 5, i % 5)
        lay.addLayout(grid)

        sub = QLabel("توزيع أوامر العمل حسب النوع والحالة")
        sub.setStyleSheet("font-weight: bold; color: #0d3c61; font-size: 12pt;")
        lay.addWidget(sub)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.table, 1)
        hint = QLabel("انقر على أي بطاقة لعرض أوامر العمل الخاصة بها.")
        hint.setObjectName("hint")
        lay.addWidget(hint)

    def _card_clicked(self, key: str):
        f = OrderFilter(year=combo_value(self.year_combo))
        if key == "rolled":
            f.rolled_only = True
        elif key != "total":
            f.status = key
        self.open_list.emit(f)

    def refresh(self, *_):
        year = combo_value(self.year_combo)
        orders = [o for o in self.repo.all_orders() if year is None or o.order_year == year]
        statuses = {o.id: compute_status(o, self.today) for o in orders}
        counts = {code: 0 for code in STATUS_LABELS}
        for o in orders:
            counts[statuses[o.id]] += 1
        self.cards["total"].number.setText(str(len(orders)))
        for code, n in counts.items():
            self.cards[code].number.setText(str(n))
        self.cards["rolled"].number.setText(str(sum(rolled_to_year(o, self.today) is not None for o in orders)))

        headers = ["نوع أمر العمل", "المجموع"] + [_wrap(v) for v in STATUS_LABELS.values()]
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        rows = list(ORDER_TYPES.items()) + [(None, "المجموع")]
        self.table.setRowCount(len(rows))
        for r, (code, label) in enumerate(rows):
            subset = orders if code is None else [o for o in orders if o.order_type == code]
            values = [label, len(subset)] + [sum(statuses[o.id] == s for o in subset) for s in STATUS_LABELS]
            for c, v in enumerate(values):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignCenter)
                if code is None or c == 1:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                if code is None:
                    item.setBackground(QColor("#eef2f7"))
                self.table.setItem(r, c, item)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.resizeRowsToContents()
        self.table.setMaximumHeight(self.table.horizontalHeader().height() + sum(
            self.table.rowHeight(i) for i in range(self.table.rowCount())) + 6)


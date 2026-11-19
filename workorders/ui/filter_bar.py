"""شريط الفلاتر المشترك بين شاشة أوامر العمل وشاشة التقارير."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from ..constants import ORDER_TYPES, VOLTAGES, WORK_TYPES
from ..reports import STATUS_FILTERS, OrderFilter
from ..repository import Repository
from ..validation import allowed_years
from .widgets import combo_value, fill_combo, make_combo, set_combo_value

ALL = "الكل"


def _with_all(options, all_label=ALL):
    items = list(options.items()) if isinstance(options, dict) else list(options)
    return [(None, all_label)] + items


class FilterBar(QWidget):
    changed = Signal()

    def __init__(self, repo: Repository, today: date, columns: int = 4, show_search: bool = True, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.today = today
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        self.year = make_combo(_with_all([(y, str(y)) for y in allowed_years(today)], "كل السنوات"))
        self.order_type = make_combo(_with_all(ORDER_TYPES))
        self.work_type = make_combo(_with_all(WORK_TYPES))
        self.voltage = make_combo(_with_all(VOLTAGES))
        self.sector = make_combo([])
        self.status = make_combo(_with_all(STATUS_FILTERS, "كل الحالات"))
        self.head = make_combo([])
        self.rolled = QCheckBox("المدوّرة فقط")
        self.early = QCheckBox("⚠ المباشرة قبل الموافقة فقط")
        self.early.setToolTip("أوامر العمل التي تاريخ مباشرتها يسبق تاريخ كتاب الموافقة (حالات استثنائية للمراجعة)")
        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث برقم أمر العمل (مثل 10 أو 10/2026) أو بجزء من اسم المشروع")
        self.search.setClearButtonEnabled(True)
        self.clear_btn = QPushButton("مسح الفلاتر")
        self.reload_lookups()

        pairs = [
            ("السنة", self.year), ("نوع الأمر", self.order_type), ("نوع العمل", self.work_type),
            ("الجهد", self.voltage), ("القطاع", self.sector), ("الحالة", self.status),
            ("رئيس اللجنة", self.head),
        ]
        for i, (label, widget) in enumerate(pairs):
            row, col = divmod(i, columns)
            grid.addWidget(QLabel(label), row, col * 2)
            grid.addWidget(widget, row, col * 2 + 1)
        last = len(pairs)
        row, col = divmod(last, columns)
        checks = QHBoxLayout()
        checks.setContentsMargins(0, 0, 0, 0)
        checks.addWidget(self.rolled)
        checks.addWidget(self.early)
        checks.addStretch(1)
        grid.addLayout(checks, row, col * 2, 1, max(2, (columns - col) * 2))
        next_row = row + 1
        if show_search:
            grid.addWidget(QLabel("بحث"), next_row, 0)
            grid.addWidget(self.search, next_row, 1, 1, columns * 2 - 2)
            grid.addWidget(self.clear_btn, next_row, columns * 2 - 1)
        else:
            self.search.hide()
            grid.addWidget(self.clear_btn, next_row, columns * 2 - 1)
        for c in range(columns):
            grid.setColumnStretch(c * 2 + 1, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.changed)
        for combo in (self.year, self.order_type, self.work_type, self.voltage, self.sector, self.status, self.head):
            combo.currentIndexChanged.connect(self._on_change)
        self.rolled.toggled.connect(self._on_change)
        self.early.toggled.connect(self._on_change)
        self.search.textChanged.connect(lambda *_: self._timer.start())
        self.clear_btn.clicked.connect(self.reset)
        self.reset(emit=False)

    def _on_change(self, *_):
        self.changed.emit()

    def reload_lookups(self):
        sector = combo_value(self.sector)
        head = combo_value(self.head)
        fill_combo(self.sector, _with_all([(s.id, s.name) for s in self.repo.sectors(include_inactive=True)]))
        fill_combo(self.head, _with_all([(h.id, h.name) for h in self.repo.committee_heads(include_inactive=True)]))
        set_combo_value(self.sector, sector)
        set_combo_value(self.head, head)
        if self.sector.currentIndex() < 0:
            self.sector.setCurrentIndex(0)
        if self.head.currentIndex() < 0:
            self.head.setCurrentIndex(0)

    def reset(self, emit=True):
        widgets = (self.year, self.order_type, self.work_type, self.voltage, self.sector, self.status, self.head)
        for combo in widgets:
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        for box in (self.rolled, self.early):
            box.blockSignals(True)
            box.setChecked(False)
            box.blockSignals(False)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        if emit:
            self.changed.emit()

    def set_filter(self, f: OrderFilter):
        self.blockSignals(True)
        self.reset(emit=False)
        set_combo_value(self.year, f.year)
        set_combo_value(self.order_type, f.order_type)
        set_combo_value(self.work_type, f.work_type)
        set_combo_value(self.voltage, f.voltage)
        set_combo_value(self.sector, f.sector_id)
        set_combo_value(self.status, f.status)
        set_combo_value(self.head, f.committee_head_id)
        for combo in (self.year, self.order_type, self.work_type, self.voltage, self.sector, self.status, self.head):
            if combo.currentIndex() < 0:
                combo.setCurrentIndex(0)
        self.rolled.setChecked(f.rolled_only)
        self.early.setChecked(f.early_start_only)
        self.search.setText(f.text)
        self.blockSignals(False)
        self.changed.emit()

    def current(self) -> OrderFilter:
        return OrderFilter(
            year=combo_value(self.year),
            order_type=combo_value(self.order_type),
            work_type=combo_value(self.work_type),
            voltage=combo_value(self.voltage),
            sector_id=combo_value(self.sector),
            status=combo_value(self.status),
            committee_head_id=combo_value(self.head),
            rolled_only=self.rolled.isChecked(),
            early_start_only=self.early.isChecked(),
            text=self.search.text(),
        )

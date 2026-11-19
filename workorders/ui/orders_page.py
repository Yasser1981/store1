"""شاشة استعراض أوامر العمل والبحث فيها."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..constants import STATUS_COLORS, STATUS_LABELS
from ..export import report_to_xlsx
from ..models import WorkOrder, compute_status, rolled_to_year
from ..reports import ReportContext, apply_filter, describe_filter, report_detail
from ..repository import Repository
from ..textutil import fmt_date
from . import messages
from .filter_bar import FilterBar
from .printing import safe_filename


class SortItem(QTableWidgetItem):
    """خلية جدول تُرتَّب حسب قيمة رقمية/تاريخية وليس حسب النص."""

    def __init__(self, text: str, key=None):
        super().__init__(text)
        self.key = key if key is not None else text

    def __lt__(self, other):  # noqa: D105
        a, b = self.key, getattr(other, "key", other.text())
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


COLUMNS = [
    "رقم الأمر", "السنة", "نوع الأمر", "الحالة", "اسم المشروع", "نوع العمل", "القطاع",
    "تاريخ الرفع", "تاريخ الموافقة", "رئيس اللجنة", "تاريخ المباشرة", "تاريخ الغلق", "التدوير",
]
COL_STATUS, COL_PROJECT, COL_WORK, COL_HEAD = 3, 4, 5, 9


class OrdersPage(QWidget):
    data_changed = Signal()
    request_new = Signal()
    request_open = Signal(int)

    def __init__(self, repo: Repository, today: date, backups_dir: Path, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.today = today
        self.backups_dir = backups_dir
        self.setObjectName("page")
        self.orders: list[WorkOrder] = []
        self.visible: list[WorkOrder] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)
        title = QLabel("أوامر العمل")
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        self.filters = FilterBar(repo, today)
        self.filters.changed.connect(self.apply)
        lay.addWidget(self.filters)

        bar = QHBoxLayout()
        self.new_btn = QPushButton("+ أمر عمل جديد")
        self.new_btn.setObjectName("primary")
        self.open_btn = QPushButton("فتح / تعديل")
        self.delete_btn = QPushButton("حذف")
        self.delete_btn.setObjectName("danger")
        self.export_btn = QPushButton("تصدير القائمة إلى Excel")
        self.count_label = QLabel()
        self.count_label.setObjectName("hint")
        for b in (self.new_btn, self.open_btn, self.delete_btn, self.export_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self.count_label)
        lay.addLayout(bar)

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_PROJECT, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_WORK, QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(COL_PROJECT, 320)
        self.table.setColumnWidth(COL_WORK, 210)
        lay.addWidget(self.table, 1)
        hint = QLabel("انقر نقراً مزدوجاً على أمر العمل لفتحه. انقر على عنوان أي عمود للترتيب حسبه.")
        hint.setObjectName("hint")
        lay.addWidget(hint)

        self.new_btn.clicked.connect(self.request_new)
        self.open_btn.clicked.connect(self._open_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.export_btn.clicked.connect(self._export)
        self.table.cellDoubleClicked.connect(lambda r, c: self._open_selected())
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self._update_buttons()

    # ------------------------------------------------------------------
    def refresh(self):
        self.filters.reload_lookups()
        self.orders = self.repo.all_orders()
        self.apply()

    def apply(self, *_):
        f = self.filters.current()
        self.visible = apply_filter(self.orders, f, self.today)
        selected = self.selected_id()
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(self.visible))
        for r, o in enumerate(self.visible):
            rolled = rolled_to_year(o, self.today)
            status = compute_status(o, self.today)
            values = [
                SortItem(str(o.order_no), o.order_no),
                SortItem(str(o.order_year), o.order_year),
                SortItem(o.order_type_label),
                SortItem(STATUS_LABELS[status] + ("  ⚠" if o.started_before_approval else "")),
                SortItem(o.project_name),
                SortItem(o.work_description),
                SortItem(o.sector_name or "" if o.needs_sector else ""),
                SortItem(fmt_date(o.submit_date), o.submit_date or date.min),
                SortItem(fmt_date(o.response_date) if o.response == "approved" else "",
                         o.response_date if o.response == "approved" and o.response_date else date.min),
                SortItem(o.committee_head_name or ""),
                SortItem(fmt_date(o.commencement_date), o.commencement_date or date.min),
                SortItem(fmt_date(o.close_date), o.close_date or date.min),
                SortItem(f"إلى {rolled}" if rolled else "", rolled or 0),
            ]
            for c, item in enumerate(values):
                item.setData(Qt.UserRole, o.id)
                if c not in (COL_PROJECT, COL_WORK, COL_HEAD):
                    item.setTextAlignment(Qt.AlignCenter)
                if c in (COL_PROJECT, COL_WORK):
                    item.setToolTip(item.text())
                if c == COL_STATUS and o.started_before_approval:
                    item.setToolTip("⚠ تاريخ المباشرة يسبق تاريخ كتاب الموافقة (حالة استثنائية – للمراجعة)")
                if c == COL_STATUS:
                    fg, bg = STATUS_COLORS[status]
                    item.setForeground(QColor(fg))
                    item.setBackground(QColor(bg))
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        total = len(self.orders)
        shown = len(self.visible)
        self.count_label.setText(f"المعروض: {shown} من أصل {total} أمر عمل" if shown != total
                                 else f"عدد أوامر العمل: {total}")
        if selected is not None:
            self.select_order(selected)
        self._update_buttons()

    def selected_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item else None

    def select_order(self, order_id: int):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.UserRole) == order_id:
                self.table.selectRow(r)
                self.table.scrollToItem(item)
                return

    def _update_buttons(self):
        has = self.selected_id() is not None
        self.open_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        self.export_btn.setEnabled(bool(self.visible))

    def _open_selected(self):
        order_id = self.selected_id()
        if order_id is not None:
            self.request_open.emit(order_id)

    def _delete_selected(self):
        order_id = self.selected_id()
        if order_id is None:
            return
        o = self.repo.get_order(order_id)
        if o is None:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("حذف أمر العمل")
        box.setText(f"سيتم حذف أمر العمل {o.ref} ({o.order_type_label})\n«{o.project_name}»\nنهائياً من الأرشيف.")
        box.setInformativeText("هل أنت متأكد من الحذف؟ (ستُحفظ نسخة احتياطية قبل الحذف)")
        yes = box.addButton("نعم، احذف", QMessageBox.DestructiveRole)
        box.addButton("لا، تراجع", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        from ..backup import make_backup, prune_backups
        make_backup(self.repo.conn, self.backups_dir, "before_delete")
        prune_backups(self.backups_dir, "before_delete_", 30)
        self.repo.delete_order(order_id)
        self.data_changed.emit()

    def _export(self):
        ctx = ReportContext(self.repo.sectors(True), self.repo.committee_heads(True),
                            self.repo.materials(True), self.today)
        report = report_detail(self.visible, ctx, describe_filter(self.filters.current(), ctx))
        default = str(Path.home() / f"{safe_filename('قائمة أوامر العمل')} {self.today.isoformat()}.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "حفظ ملف Excel", default, "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            report_to_xlsx(report, Path(path))
        except OSError as exc:
            messages.critical(self, "خطأ", f"تعذر حفظ الملف. قد يكون مفتوحاً في Excel.\n\n{exc}")
            return
        messages.information(self, "تم", f"تم حفظ الملف:\n{path}")

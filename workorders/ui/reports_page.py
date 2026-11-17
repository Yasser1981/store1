"""شاشة التقارير: اختيار التقرير والفلاتر، ثم المعاينة والطباعة والتصدير."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QLocale, Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..export import report_to_html, report_to_xlsx
from ..reports import GROUP_BY, GROUPED_REPORTS, REPORT_TYPES, Report, ReportContext, build_report
from ..repository import Repository
from .filter_bar import FilterBar
from .printing import print_preview, safe_filename, save_pdf
from .widgets import combo_value, make_combo


class ReportsPage(QWidget):
    def __init__(self, repo: Repository, today: date, font_family: str, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.today = today
        self.font_family = font_family
        self.report: Report | None = None
        self.setObjectName("page")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)
        title = QLabel("التقارير")
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        splitter = QSplitter(Qt.Horizontal)
        lay.addWidget(splitter, 1)

        # ---------------- لوحة الاختيارات
        side = QWidget()
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        box1 = QGroupBox("1. اختر التقرير")
        b1 = QVBoxLayout(box1)
        self.report_list = QListWidget()
        self.report_list.setObjectName("reportList")
        for key, label in REPORT_TYPES.items():
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            self.report_list.addItem(item)
        self.report_list.setCurrentRow(0)
        self.report_list.setWordWrap(True)
        self.report_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.report_list.setMinimumHeight(300)
        b1.addWidget(self.report_list)

        self.group_row = QWidget()
        g = QHBoxLayout(self.group_row)
        g.setContentsMargins(0, 0, 0, 0)
        g.addWidget(QLabel("حسب:"))
        self.group_combo = make_combo(GROUP_BY)
        self.group_combo.setCurrentIndex(0)
        g.addWidget(self.group_combo, 1)
        b1.addWidget(self.group_row)

        self.days_row = QWidget()
        d = QHBoxLayout(self.days_row)
        d.setContentsMargins(0, 0, 0, 0)
        d.addWidget(QLabel("مرفوعة منذ (يوم) فأكثر:"))
        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 3650)
        self.days_spin.setValue(30)
        self.days_spin.setLocale(QLocale.c())
        d.addWidget(self.days_spin)
        d.addStretch(1)
        b1.addWidget(self.days_row)
        side_lay.addWidget(box1)

        box2 = QGroupBox("2. حدد أوامر العمل المشمولة (اختياري)")
        b2 = QVBoxLayout(box2)
        self.filters = FilterBar(repo, today, columns=1, show_search=False)
        b2.addWidget(self.filters)
        side_lay.addWidget(box2)
        side_lay.addStretch(1)
        splitter.addWidget(side)

        # ---------------- المعاينة
        right = QWidget()
        r = QVBoxLayout(right)
        r.setContentsMargins(0, 0, 0, 0)
        buttons = QHBoxLayout()
        self.print_btn = QPushButton("معاينة وطباعة")
        self.print_btn.setObjectName("primary")
        self.pdf_btn = QPushButton("حفظ PDF")
        self.xlsx_btn = QPushButton("تصدير إلى Excel")
        for b in (self.print_btn, self.pdf_btn, self.xlsx_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        r.addLayout(buttons)
        self.preview = QTextBrowser()
        self.preview.setOpenLinks(False)
        r.addWidget(self.preview, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 900])

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.generate)
        self.report_list.currentRowChanged.connect(lambda *_: self._timer.start())
        self.group_combo.currentIndexChanged.connect(lambda *_: self._timer.start())
        self.days_spin.valueChanged.connect(lambda *_: self._timer.start())
        self.filters.changed.connect(self._timer.start)
        self.print_btn.clicked.connect(self._print)
        self.pdf_btn.clicked.connect(self._pdf)
        self.xlsx_btn.clicked.connect(self._excel)

    def refresh(self):
        self.filters.reload_lookups()
        self.generate()

    def current_kind(self) -> str:
        item = self.report_list.currentItem()
        return item.data(Qt.UserRole) if item else "progress"

    def generate(self):
        kind = self.current_kind()
        self.group_row.setVisible(kind in GROUPED_REPORTS)
        self.days_row.setVisible(kind == "overdue")
        ctx = ReportContext(self.repo.sectors(True), self.repo.committee_heads(True),
                            self.repo.materials(True), self.today)
        self.report = build_report(
            kind, self.repo.all_orders(), ctx, self.filters.current(),
            group_by=combo_value(self.group_combo) or "order_type", overdue_days=self.days_spin.value())
        self.preview.setHtml(report_to_html(self.report, self.font_family, base_pt=10))

    # ------------------------------------------------------------------
    def _default_path(self, ext: str) -> str:
        name = f"{safe_filename(self.report.title)} {self.today.isoformat()}.{ext}"
        return str(Path.home() / name)

    def _print(self):
        if self.report:
            print_preview(self.report, self.font_family, self)

    def _pdf(self):
        if not self.report:
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ PDF", self._default_path("pdf"), "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            save_pdf(self.report, Path(path), self.font_family)
        except OSError as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ الملف.\n\n{exc}")
            return
        QMessageBox.information(self, "تم", f"تم حفظ الملف:\n{path}")

    def _excel(self):
        if not self.report:
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ ملف Excel", self._default_path("xlsx"), "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            report_to_xlsx(self.report, Path(path))
        except OSError as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ الملف. قد يكون مفتوحاً في Excel.\n\n{exc}")
            return
        QMessageBox.information(self, "تم", f"تم حفظ الملف:\n{path}")

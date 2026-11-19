"""حفظ التقارير بصيغة PDF و Excel ونافذة عرض تقرير مستقلة."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout

from ..export import report_to_xlsx
from ..reports import Report
from . import messages
from .printing import print_preview, safe_filename, save_pdf, show_in_browser


def _default_path(report: Report, today: date, ext: str) -> str:
    return str(Path.home() / f"{safe_filename(report.title)} {today.isoformat()}.{ext}")


def save_report_pdf(parent, report: Report, font_family: str, today: date) -> None:
    path, _ = QFileDialog.getSaveFileName(parent, "حفظ PDF", _default_path(report, today, "pdf"), "PDF (*.pdf)")
    if not path:
        return
    if not path.lower().endswith(".pdf"):
        path += ".pdf"
    try:
        save_pdf(report, Path(path), font_family)
    except OSError as exc:
        messages.critical(parent, "خطأ", f"تعذر حفظ الملف.\n\n{exc}")
        return
    messages.information(parent, "تم", f"تم حفظ الملف:\n{path}")


def save_report_excel(parent, report: Report, today: date) -> None:
    path, _ = QFileDialog.getSaveFileName(
        parent, "حفظ ملف Excel", _default_path(report, today, "xlsx"), "Excel (*.xlsx)")
    if not path:
        return
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"
    try:
        report_to_xlsx(report, Path(path))
    except OSError as exc:
        messages.critical(parent, "خطأ", f"تعذر حفظ الملف. قد يكون مفتوحاً في Excel.\n\n{exc}")
        return
    messages.information(parent, "تم", f"تم حفظ الملف:\n{path}")


class ReportDialog(QDialog):
    """نافذة تعرض تقريراً مع أزرار الطباعة وحفظ PDF والتصدير إلى Excel."""

    def __init__(self, report: Report, font_family: str, today: date, parent=None):
        super().__init__(parent)
        self.report = report
        self.font_family = font_family
        self.today = today
        self.setWindowTitle(report.title)
        self.resize(1200, 820)
        lay = QVBoxLayout(self)
        buttons = QHBoxLayout()
        self.print_btn = QPushButton("معاينة وطباعة")
        self.print_btn.setObjectName("primary")
        self.pdf_btn = QPushButton("حفظ PDF")
        self.xlsx_btn = QPushButton("تصدير إلى Excel")
        self.close_btn = QPushButton("إغلاق")
        for b in (self.print_btn, self.pdf_btn, self.xlsx_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(self.close_btn)
        lay.addLayout(buttons)
        self.preview = QTextBrowser()
        show_in_browser(self.preview, report, font_family)
        lay.addWidget(self.preview, 1)
        self.print_btn.clicked.connect(lambda: print_preview(self.report, self.font_family, self))
        self.pdf_btn.clicked.connect(lambda: save_report_pdf(self, self.report, self.font_family, self.today))
        self.xlsx_btn.clicked.connect(lambda: save_report_excel(self, self.report, self.today))
        self.close_btn.clicked.connect(self.accept)

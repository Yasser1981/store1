"""الطباعة وحفظ PDF للتقارير."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QMarginsF, Qt
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument, QTextOption
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog

from ..export import report_to_html
from ..reports import Report


def make_document(report: Report, font_family: str) -> QTextDocument:
    doc = QTextDocument()
    option = QTextOption()
    option.setTextDirection(Qt.RightToLeft)
    option.setAlignment(Qt.AlignRight)
    doc.setDefaultTextOption(option)
    doc.setDefaultFont(QFont(font_family, 9))
    doc.setHtml(report_to_html(report, font_family))
    return doc


def _setup_printer(printer: QPrinter, report: Report) -> None:
    layout = QPageLayout(
        QPageSize(QPageSize.A4),
        QPageLayout.Landscape if report.landscape else QPageLayout.Portrait,
        QMarginsF(10, 10, 10, 12),
        QPageLayout.Millimeter,
    )
    printer.setPageLayout(layout)
    # اسم المستند بالإنكليزية: بعض قارئات PDF تنزعج من العنوان العربي في بيانات الملف
    printer.setDocName("Work Orders Report")


def save_pdf(report: Report, path: Path, font_family: str) -> Path:
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(path))
    _setup_printer(printer, report)
    make_document(report, font_family).print_(printer)
    return Path(path)


def print_preview(report: Report, font_family: str, parent=None) -> None:
    printer = QPrinter(QPrinter.HighResolution)
    _setup_printer(printer, report)
    doc = make_document(report, font_family)
    dialog = QPrintPreviewDialog(printer, parent)
    dialog.setWindowTitle(f"معاينة الطباعة – {report.title}")
    dialog.paintRequested.connect(doc.print_)
    dialog.resize(1100, 800)
    dialog.exec()


def safe_filename(text: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', " ", text).strip()
    return name[:80] or "تقرير"

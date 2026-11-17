"""تحويل التقارير إلى HTML (للمعاينة والطباعة وPDF) وإلى ملف Excel."""

from __future__ import annotations

from html import escape
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import __version__
from .constants import APP_NAME, EDITION_NAME, ORG_LINE, STATUS_COLORS, STATUS_LABELS
from .reports import Column, Report, Table
from .textutil import fmt_date, fmt_int


def format_cell(col: Column, value) -> str:
    if value is None or value == "":
        return ""
    if col.kind in ("int", "money"):
        return fmt_int(value)
    if col.kind == "date":
        return fmt_date(value)
    if col.kind == "status":
        return STATUS_LABELS.get(value, str(value))
    return str(value)


# ======================================================================
# HTML
# ======================================================================
def _print_widths(cols: list[Column]) -> list[int]:
    """توزيع عرض الأعمدة: المحدد مسبقاً يُستخدم، والباقي يُقسم بالتساوي."""
    fixed = sum(c.pct for c in cols if c.pct)
    free = [c for c in cols if not c.pct]
    share = max(3, int((100 - fixed) / len(free))) if free else 0
    return [c.pct or share for c in cols]


def _html_table(table: Table) -> str:
    cols = [c for c in table.columns if c.in_print]
    out = []
    if table.title:
        out.append(f'<p class="ttitle">{escape(table.title)}</p>')
    if not table.rows:
        out.append(f'<p class="empty">{escape(table.empty_text)}</p>')
        return "\n".join(out)
    out.append('<table class="data" width="100%" border="1" cellspacing="0" cellpadding="3">')
    widths = _print_widths(cols)
    out.append("<thead><tr>" + "".join(
        f'<th width="{w}%">{escape(c.label)}</th>' for c, w in zip(cols, widths)) + "</tr></thead>")
    out.append("<tbody>")
    for row in table.rows:
        cells = []
        for c in cols:
            value = row.get(c.key)
            text = escape(format_cell(c, value)).replace("\n", "<br/>")
            if c.kind == "status" and value in STATUS_COLORS:
                fg, bg = STATUS_COLORS[value]
                cells.append(f'<td align="center" style="color:{fg}; background-color:{bg};">{text}</td>')
            elif c.kind in ("int", "money", "date"):
                cells.append(f'<td align="center">{text}</td>')
            else:
                cells.append(f"<td>{text}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    if table.total_row:
        cells = []
        for c in cols:
            value = table.total_row.get(c.key)
            text = escape(format_cell(c, value) if c.total else (value or ""))
            cells.append(f'<td align="center" class="total">{text}</td>')
        out.append('<tr class="total">' + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def report_to_html(report: Report, font_family: str = "Segoe UI", base_pt: float | None = None) -> str:
    if base_pt is None:
        base_pt = 8.5 if report.landscape else 10
    css = f"""
        body {{ font-family: '{font_family}'; font-size: {base_pt}pt; }}
        p.org {{ font-size: {base_pt + 2}pt; font-weight: bold; text-align: center; margin: 0; }}
        p.title {{ font-size: {base_pt + 4}pt; font-weight: bold; text-align: center; margin-top: 6px; }}
        p.meta {{ font-size: {base_pt - 0.5}pt; color: #333333; text-align: center; margin: 0; }}
        p.ttitle {{ font-size: {base_pt + 1}pt; font-weight: bold; margin-top: 12px; color: #0d3c61; }}
        p.empty {{ color: #777777; }}
        p.note {{ font-size: {base_pt - 0.5}pt; color: #444444; margin: 0; }}
        table.data {{ border-collapse: collapse; border-color: #7f8c9d; }}
        table.data th {{ background-color: #dbe5f1; font-weight: bold; border: 1px solid #7f8c9d; }}
        table.data td {{ border: 1px solid #7f8c9d; }}
        td.total {{ background-color: #eeeeee; font-weight: bold; }}
    """
    parts = [
        f'<html dir="rtl"><head><meta charset="utf-8"><style>{css}</style></head><body dir="rtl">',
        f'<p class="org">{escape(ORG_LINE)}</p>',
        f'<p class="title">{escape(report.title)}</p>',
        f'<p class="meta">{escape(report.filters_text)}</p>',
        f'<p class="meta">تاريخ إعداد التقرير: {report.generated_at.strftime("%d/%m/%Y %H:%M")}'
        f' — {escape(APP_NAME)} ({escape(EDITION_NAME)}) الإصدار {__version__}</p>',
        "<br/>",
    ]
    for table in report.tables:
        parts.append(_html_table(table))
    if report.notes:
        parts.append("<br/>")
        for note in report.notes:
            parts.append(f'<p class="note">• {escape(note)}</p>')
    parts.append("</body></html>")
    return "\n".join(parts)


# ======================================================================
# Excel
# ======================================================================
_THIN = Side(style="thin", color="7F8C9D")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill("solid", fgColor="DBE5F1")
_TOTAL_FILL = PatternFill("solid", fgColor="EEEEEE")


def report_to_xlsx(report: Report, path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "التقرير"
    ws.sheet_view.rightToLeft = True

    tables = report.tables
    max_cols = max((len([c for c in t.columns if c.in_excel]) for t in tables), default=1)
    widths: dict[int, int] = {}

    def title_row(r, text, size=12, bold=True):
        ws.cell(row=r, column=1, value=text).font = Font(size=size, bold=bold)
        ws.cell(row=r, column=1).alignment = Alignment(horizontal="center")
        if max_cols > 1:
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=max_cols)

    title_row(1, ORG_LINE, 12)
    title_row(2, report.title, 14)
    title_row(3, report.filters_text, 10, bold=False)
    title_row(4, f"تاريخ إعداد التقرير: {report.generated_at.strftime('%d/%m/%Y %H:%M')}", 9, bold=False)
    r = 6
    first_header_row = None

    for table in tables:
        cols = [c for c in table.columns if c.in_excel]
        if table.title:
            ws.cell(row=r, column=1, value=table.title).font = Font(bold=True, size=11, color="0D3C61")
            r += 1
        if not table.rows:
            ws.cell(row=r, column=1, value=table.empty_text)
            r += 2
            continue
        for ci, c in enumerate(cols, start=1):
            cell = ws.cell(row=r, column=ci, value=c.label)
            cell.font = Font(bold=True)
            cell.fill = _HEADER_FILL
            cell.border = _BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            widths[ci] = max(widths.get(ci, 0), c.width)
        if first_header_row is None:
            first_header_row = r
        r += 1
        for row in table.rows:
            for ci, c in enumerate(cols, start=1):
                value = row.get(c.key)
                if c.kind == "status":
                    value = STATUS_LABELS.get(value, value)
                    cell = ws.cell(row=r, column=ci, value=value)
                    if row.get(c.key) in STATUS_COLORS:
                        fg, bg = STATUS_COLORS[row[c.key]]
                        cell.font = Font(color=fg.lstrip("#").upper())
                        cell.fill = PatternFill("solid", fgColor=bg.lstrip("#").upper())
                else:
                    cell = ws.cell(row=r, column=ci, value=value if value != "" else None)
                if c.kind == "money":
                    cell.number_format = "#,##0"
                elif c.kind == "int":
                    cell.number_format = "#,##0" if c.total else "0"
                elif c.kind == "date":
                    cell.number_format = "DD/MM/YYYY"
                cell.border = _BORDER
                cell.alignment = Alignment(
                    horizontal="center" if c.kind != "text" else "right", vertical="center", wrap_text=True)
            r += 1
        if table.total_row:
            for ci, c in enumerate(cols, start=1):
                value = table.total_row.get(c.key)
                cell = ws.cell(row=r, column=ci, value=value if value != "" else None)
                cell.font = Font(bold=True)
                cell.fill = _TOTAL_FILL
                cell.border = _BORDER
                cell.alignment = Alignment(horizontal="center")
                if c.kind in ("money", "int"):
                    cell.number_format = "#,##0"
            r += 1
        r += 1

    for note in report.notes:
        ws.cell(row=r, column=1, value=f"• {note}").font = Font(size=9, color="444444")
        r += 1

    for ci, w in widths.items():
        ws.column_dimensions[get_column_letter(ci)].width = w
    if len(tables) == 1 and first_header_row:
        ws.freeze_panes = ws.cell(row=first_header_row + 1, column=1)
    ws.page_setup.orientation = "landscape" if report.landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    path = Path(path)
    wb.save(path)
    return path

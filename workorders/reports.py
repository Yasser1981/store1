"""بناء التقارير والفلاتر (بدون واجهة) حتى يمكن اختبارها وتصديرها بعدة صيغ."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .constants import (
    FINISHED_STATUSES,
    ORDER_TYPES,
    STATUS_LABELS,
    VOID_STATUSES,
    VOLTAGES,
    WORK_TYPES,
    Status,
)
from .models import LookupItem, WorkOrder, compute_status, rolled_to_year
from .textutil import fmt_date, normalize_digits, normalize_for_compare

NOT_APPLICABLE = "لا ينطبق"


# ======================================================================
# الفلاتر
# ======================================================================
STATUS_FILTERS = {
    "not_void": "كل الحالات عدا الملغاة والمرفوضة",
    "open": "غير المنتهية (لم تُغلق ولم تُلغَ ولم تُرفض)",
    **STATUS_LABELS,
}


@dataclass
class OrderFilter:
    year: int | None = None
    order_type: str | None = None
    work_type: str | None = None
    voltage: str | None = None
    sector_id: int | None = None
    status: str | None = None
    committee_head_id: int | None = None
    rolled_only: bool = False
    early_start_only: bool = False  # المباشرة قبل الموافقة (للمراجعة)
    text: str = ""
    # مجموعة أوامر مختارة: أرقام أوامر العمل (None = الكل) واسم المجموعة للعرض
    order_ids: frozenset | None = None
    group_name: str = ""

    def is_empty(self) -> bool:
        return self == OrderFilter()


def _status_matches(o: WorkOrder, status: str | None, today: date) -> bool:
    if status is None:
        return True
    s = compute_status(o, today)
    if status == "not_void":
        return s not in VOID_STATUSES
    if status == "open":
        return s not in FINISHED_STATUSES
    return s == status


def _text_matches(o: WorkOrder, text: str) -> bool:
    """البحث: رقم فقط ← رقم أمر العمل، (10/2026) ← رقم وسنة، غير ذلك ← جزء من اسم المشروع."""
    t = normalize_digits(text).strip()
    if not t:
        return True
    if "/" in t:
        parts = [p.strip() for p in t.split("/")]
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            a, b = int(parts[0]), int(parts[1])
            return (o.order_no, o.order_year) in ((a, b), (b, a))
    if t.isdigit():
        return o.order_no == int(t)
    return normalize_for_compare(t) in normalize_for_compare(o.project_name)


def apply_filter(orders: list[WorkOrder], f: OrderFilter, today: date) -> list[WorkOrder]:
    result = []
    for o in orders:
        if f.order_ids is not None and o.id not in f.order_ids:
            continue
        if f.year is not None and o.order_year != f.year:
            continue
        if f.order_type and o.order_type != f.order_type:
            continue
        if f.work_type and o.work_type != f.work_type:
            continue
        if f.voltage and not (o.is_network and o.voltage == f.voltage):
            continue
        if f.sector_id is not None and not (o.needs_sector and o.sector_id == f.sector_id):
            continue
        if f.committee_head_id is not None and o.committee_head_id != f.committee_head_id:
            continue
        if not _status_matches(o, f.status, today):
            continue
        if f.rolled_only and rolled_to_year(o, today) is None:
            continue
        if f.early_start_only and not o.started_before_approval:
            continue
        if not _text_matches(o, f.text):
            continue
        result.append(o)
    return result


@dataclass
class ReportContext:
    """القوائم المساعدة اللازمة لبناء التقارير."""

    sectors: list[LookupItem]
    heads: list[LookupItem]
    materials: list[LookupItem]
    today: date

    def sector_name(self, sector_id):
        return next((s.name for s in self.sectors if s.id == sector_id), "")

    def head_name(self, head_id):
        return next((h.name for h in self.heads if h.id == head_id), "")


def describe_filter(f: OrderFilter, ctx: ReportContext) -> str:
    parts = []
    if f.order_ids is not None:
        parts.append(f"المجموعة: {f.group_name}" if f.group_name else f"أوامر عمل مختارة ({len(f.order_ids)})")
    if f.year is not None:
        parts.append(f"السنة: {f.year}")
    if f.order_type:
        parts.append(f"نوع الأمر: {ORDER_TYPES[f.order_type]}")
    if f.work_type:
        parts.append(f"نوع العمل: {WORK_TYPES[f.work_type]}")
    if f.voltage:
        parts.append(f"الجهد: {VOLTAGES[f.voltage]}")
    if f.sector_id is not None:
        parts.append(f"القطاع: {ctx.sector_name(f.sector_id)}")
    if f.status:
        parts.append(f"الحالة: {STATUS_FILTERS[f.status]}")
    if f.committee_head_id is not None:
        parts.append(f"رئيس اللجنة: {ctx.head_name(f.committee_head_id)}")
    if f.early_start_only:
        parts.append("المباشرة قبل تاريخ الموافقة (للمراجعة)")
    if f.rolled_only:
        parts.append("المدوّرة فقط")
    if f.text.strip():
        parts.append(f"بحث: {f.text.strip()}")
    return " | ".join(parts) if parts else "جميع أوامر العمل"


# ======================================================================
# هيكل التقرير
# ======================================================================
@dataclass
class Column:
    key: str
    label: str
    kind: str = "text"  # text | int | money | date | status
    in_print: bool = True
    in_excel: bool = True
    total: bool = False
    width: int = 14  # عرض العمود في Excel
    pct: int | None = None  # عرض العمود في الطباعة (نسبة مئوية)


@dataclass
class Table:
    columns: list[Column]
    rows: list[dict]
    title: str = ""
    total_row: dict | None = None
    empty_text: str = "لا توجد بيانات مطابقة."

    def compute_totals(self, label_key: str, label: str = "المجموع") -> None:
        if not any(c.total for c in self.columns):
            return
        totals = {label_key: label}
        for c in self.columns:
            if c.total:
                totals[c.key] = sum((r.get(c.key) or 0) for r in self.rows)
        self.total_row = totals


@dataclass
class Report:
    title: str
    filters_text: str
    tables: list[Table]
    notes: list[str] = field(default_factory=list)
    landscape: bool = False
    generated_at: datetime = field(default_factory=datetime.now)


# ======================================================================
# التجميع حسب التصنيف
# ======================================================================
GROUP_BY = {
    "order_type": "نوع أمر العمل",
    "work_type": "نوع العمل",
    "voltage": "مستوى الجهد",
    "sector": "قطاع التوزيع",
    "year": "سنة أمر العمل",
    "committee_head": "رئيس لجنة التنفيذ",
}


def _group_key(o: WorkOrder, dim: str, ctx: ReportContext) -> tuple:
    """يرجع (مفتاح الترتيب، التسمية)."""
    if dim == "order_type":
        return (list(ORDER_TYPES).index(o.order_type), o.order_type_label)
    if dim == "work_type":
        return (list(WORK_TYPES).index(o.work_type), o.work_type_label)
    if dim == "voltage":
        if not o.is_network or not o.voltage:
            return (99, f"{NOT_APPLICABLE} (ليست شبكة كهربائية)")
        return (list(VOLTAGES).index(o.voltage), o.voltage_label)
    if dim == "sector":
        if not o.needs_sector:
            return (10_000, f"{NOT_APPLICABLE} (33 ك.ف أو ليست شبكة)")
        order = next((s.sort_order for s in ctx.sectors if s.id == o.sector_id), 9_999)
        return (order, o.sector_name or ctx.sector_name(o.sector_id))
    if dim == "year":
        return (o.order_year, str(o.order_year))
    if dim == "committee_head":
        if o.committee_head_id is None:
            return ((1, ""), "لم يُحدد بعد")
        return ((0, o.committee_head_name or ""), o.committee_head_name or "")
    raise ValueError(dim)


def _groups(orders: list[WorkOrder], dim: str, ctx: ReportContext):
    buckets: dict[tuple, list[WorkOrder]] = {}
    for o in orders:
        buckets.setdefault(_group_key(o, dim, ctx), []).append(o)
    for key in sorted(buckets, key=lambda k: k[0]):
        yield key[1], buckets[key]


def _ensure_all_groups(dim: str):
    """التصنيفات الثابتة تظهر كلها حتى لو كان عددها صفراً."""
    if dim == "order_type":
        return list(ORDER_TYPES.values())
    if dim == "work_type":
        return list(WORK_TYPES.values())
    if dim == "voltage":
        return list(VOLTAGES.values())
    return []


# ======================================================================
# التقارير
# ======================================================================
REPORT_TYPES = {
    "progress": "ملخص سير العمل (المرفوعة / الموافق عليها / المباشر بها / المغلقة)",
    "status": "توزيع أوامر العمل حسب حالتها الحالية",
    "detail": "قائمة تفصيلية بأوامر العمل",
    "money": "المبالغ المخصصة (أجور العمل وشراء المواد)",
    "materials": "المواد الحاكمة (الكميات الإجمالية)",
    "overdue": "المتأخرة: مرفوعة ولم ترد موافقتها منذ مدة",
    "group": "كلف ومواد مجموعة أوامر عمل (اختر المجموعة من الفلاتر)",
}

# التقارير التي تحتاج اختيار (حسب ...)
GROUPED_REPORTS = ("progress", "status", "money")


def _grouped_table(orders, dim, ctx, columns, row_builder) -> Table:
    rows = []
    seen = set()
    for label, items in _groups(orders, dim, ctx):
        seen.add(label)
        rows.append({"group": label, **row_builder(items)})
    for label in _ensure_all_groups(dim):
        if label not in seen:
            rows.append({"group": label, **row_builder([])})
    if dim in ("order_type", "work_type", "voltage"):
        order = _ensure_all_groups(dim)
        rows.sort(key=lambda r: order.index(r["group"]) if r["group"] in order else 99)
    table = Table(columns=columns, rows=rows)
    table.compute_totals("group")
    return table


def report_progress(orders, dim, ctx, filters_text) -> Report:
    today = ctx.today
    columns = [
        Column("group", GROUP_BY[dim], width=30, pct=16),
        Column("total", "العدد الكلي", "int", total=True),
        Column("draft", "لم تُرفع بعد", "int", total=True),
        Column("submitted", "المرفوعة", "int", total=True),
        Column("pending", "لم ترد الموافقة", "int", total=True),
        Column("approved", "الموافق عليها", "int", total=True),
        Column("rejected", "المرفوضة", "int", total=True),
        Column("started", "المباشر بها", "int", total=True),
        Column("in_progress", "قيد التنفيذ", "int", total=True),
        Column("closed", "المغلقة", "int", total=True),
        Column("cancelled", "الملغاة بكتاب", "int", total=True),
        Column("auto_cancelled", "الملغاة تلقائياً", "int", total=True),
        Column("rolled", "المدوّرة", "int", total=True),
    ]

    def build(items):
        statuses = [compute_status(o, today) for o in items]
        return {
            "total": len(items),
            "draft": statuses.count(Status.DRAFT),
            "submitted": sum(o.has_submit for o in items),
            "pending": statuses.count(Status.SUBMITTED),
            "approved": sum(o.response == "approved" for o in items),
            "rejected": statuses.count(Status.REJECTED),
            "started": sum(o.has_start for o in items),
            "in_progress": statuses.count(Status.STARTED),
            "closed": statuses.count(Status.CLOSED),
            "cancelled": statuses.count(Status.CANCELLED),
            "auto_cancelled": statuses.count(Status.AUTO_CANCELLED),
            "rolled": sum(rolled_to_year(o, today) is not None for o in items),
        }

    table = _grouped_table(orders, dim, ctx, columns, build)
    notes = [
        "الأعمدة (المرفوعة، الموافق عليها، المباشر بها) تراكمية: تشمل الأوامر التي تجاوزت تلك المرحلة إلى ما بعدها.",
        "الأعمدة (لم تُرفع بعد، لم ترد الموافقة، قيد التنفيذ، المغلقة، المرفوضة، الملغاة بكتاب، الملغاة تلقائياً) "
        "تمثل الحالة الحالية.",
        "الملغاة تلقائياً: أوامر العمل التي لم يُباشر بها حتى نهاية سنتها.",
        "المدوّرة: أوامر العمل المباشر بها التي لم تُغلق خلال سنة المباشرة.",
    ]
    return Report(f"ملخص سير العمل حسب {GROUP_BY[dim]}", filters_text, [table], notes, landscape=True)


def report_status(orders, dim, ctx, filters_text) -> Report:
    columns = [Column("group", GROUP_BY[dim], width=30), Column("total", "العدد الكلي", "int", total=True)]
    for code, label in STATUS_LABELS.items():
        columns.append(Column(code, label, "int", total=True))

    def build(items):
        row = {"total": len(items)}
        statuses = [compute_status(o, ctx.today) for o in items]
        for code in STATUS_LABELS:
            row[code] = statuses.count(code)
        return row

    table = _grouped_table(orders, dim, ctx, columns, build)
    return Report(f"توزيع أوامر العمل حسب الحالة الحالية و{GROUP_BY[dim]}", filters_text, [table],
                  ["كل أمر عمل يظهر في عمود واحد فقط (حالته الحالية)."], landscape=True)


def report_money(orders, dim, ctx, filters_text) -> Report:
    approved = [o for o in orders if o.response == "approved"]
    columns = [
        Column("group", GROUP_BY[dim], width=30),
        Column("count", "عدد الأوامر الموافق عليها", "int", total=True),
        Column("labor", "أجور العمل", "money", total=True, width=20),
        Column("materials", "كلفة المواد غير المتوفرة", "money", total=True, width=20),
        Column("sum", "مجموع التخصيص (أجور + مواد غير متوفرة)", "money", total=True, width=24),
        Column("total_materials", "الكلفة الكلية للمواد", "money", total=True, width=20),
        Column("estimated", "الكلفة الكلية التخمينية", "money", total=True, width=22),
    ]

    def build(items):
        labor = sum(o.labor_alloc or 0 for o in items)
        mats = sum(o.materials_alloc or 0 for o in items)
        return {"count": len(items), "labor": labor, "materials": mats, "sum": labor + mats,
                "total_materials": sum(o.total_materials_cost or 0 for o in items),
                "estimated": sum(o.estimated_total or 0 for o in items)}

    table = _grouped_table(approved, dim, ctx, columns, build)
    return Report(f"المبالغ المخصصة حسب {GROUP_BY[dim]}", filters_text, [table],
                  ["يشمل التقرير أوامر العمل الحاصلة على موافقة المدير العام فقط (المبالغ بالدينار العراقي).",
                   "الكلفة الكلية التخمينية = الكلفة الكلية للمواد + أجور العمل."], landscape=True)


def _detail_columns(material_items: list[LookupItem]) -> list[Column]:
    """أعمدة القائمة التفصيلية: أعمدة مختصرة للطباعة، وأعمدة مفصّلة لملف Excel."""
    cols = [
        Column("seq", "ت", "int", width=6, pct=3),
        Column("ref", "أمر العمل", in_excel=False, pct=5),
        Column("order_no", "رقم أمر العمل", "int", in_print=False, width=10),
        Column("order_year", "السنة", "int", in_print=False, width=8),
        Column("order_type", "نوع الأمر", width=12, pct=5),
        Column("project_name", "اسم المشروع", width=40, pct=12),
        Column("work", "نوع العمل", in_excel=False, pct=9),
        Column("work_type", "نوع العمل", in_print=False, width=20),
        Column("voltage", "مستوى الجهد", in_print=False, width=10),
        Column("tech_class", "التصنيف الفني", in_print=False, width=18),
        Column("sector", "القطاع", width=14, pct=5),
        Column("submit", "كتاب الرفع", in_excel=False, pct=6),
        Column("submit_no", "رقم كتاب الرفع", in_print=False, width=12),
        Column("submit_date", "تاريخ كتاب الرفع", "date", in_print=False, width=12),
        Column("response_print", "رد الشركة العامة", in_excel=False, pct=6),
        Column("response", "رد الشركة العامة", in_print=False, width=14),
        Column("response_no", "رقم كتاب الرد", in_print=False, width=12),
        Column("response_date", "تاريخ كتاب الرد", "date", in_print=False, width=12),
        Column("labor_alloc", "أجور العمل", "money", total=True, width=16, pct=7),
        Column("materials_alloc", "كلفة المواد غير المتوفرة", "money", total=True, width=18, pct=7),
        Column("total_materials_cost", "الكلفة الكلية للمواد", "money", total=True, width=18, in_print=False),
        Column("estimated_total", "الكلفة التخمينية الكلية", "money", total=True, width=18, pct=7),
        Column("head", "رئيس اللجنة", width=20, pct=6),
        Column("start", "أمر المباشرة", in_excel=False, pct=6),
        Column("start_no", "رقم أمر المباشرة", in_print=False, width=12),
        Column("start_date", "تاريخ الأمر الإداري بالمباشرة", "date", in_print=False, width=14),
        Column("actual_start_date", "تاريخ المباشرة الفعلي", "date", in_print=False, width=14),
        Column("end", "الغلق / الإلغاء", in_excel=False, pct=6),
        Column("close_no", "رقم كتاب الغلق", in_print=False, width=12),
        Column("close_date", "تاريخ الغلق", "date", in_print=False, width=12),
        Column("cancel_no", "رقم كتاب الإلغاء", in_print=False, width=12),
        Column("cancel_date", "تاريخ الإلغاء", "date", in_print=False, width=12),
        Column("status", "الحالة", "status", width=22, pct=6),
        Column("rolled", "التدوير", width=14, pct=4),
    ]
    for m in material_items:
        cols.append(Column(f"mat_{m.id}", f"{m.name} ({m.unit})", "int", in_print=False, total=True, width=16))
    cols.append(Column("notes", "ملاحظات", in_print=False, width=30))
    return cols


def _book_lines(prefix: str, number: str | None, when: date | None) -> str:
    """نص الكتاب للطباعة على أسطر: (موافق / الرقم / التاريخ)."""
    lines = [prefix] if prefix else []
    if number:
        lines.append(str(number))
    if when:
        lines.append(fmt_date(when))
    return "\n".join(lines) if (number or when) else ""


def _start_lines(o: WorkOrder) -> str:
    """أمر المباشرة للطباعة: رقمه وتاريخه، وتاريخ المباشرة الفعلي إذا اختلف عنه."""
    text = _book_lines("", o.start_no, o.start_date)
    if o.actual_start_date and o.actual_start_date != o.start_date:
        text += f"\nالمباشرة الفعلية {fmt_date(o.actual_start_date)}"
    return text


def report_detail(orders, ctx, filters_text) -> Report:
    used_ids = {mid for o in orders for mid in o.effective_materials}
    material_items = [m for m in ctx.materials if m.id in used_ids]
    columns = _detail_columns(material_items)
    rows = []
    ordered = sorted(orders, key=lambda o: (o.order_year, o.order_no))
    response_words = {"pending": "لم ترد", "approved": "موافق", "rejected": "مرفوض"}
    for i, o in enumerate(ordered, start=1):
        if o.has_close:
            end = _book_lines("غلق", o.close_no, o.close_date)
        elif o.has_cancel:
            end = _book_lines("إلغاء", o.cancel_no, o.cancel_date)
        else:
            end = ""
        responded = o.response != "pending"
        response_word = response_words[o.response] if o.has_submit else ""
        row = {
            "seq": i,
            "ref": f"{o.order_no}/{o.order_year}",
            "order_no": o.order_no,
            "order_year": o.order_year,
            "order_type": o.order_type_label,
            "project_name": o.project_name,
            "work": o.work_description,
            "work_type": o.work_type_label,
            "voltage": o.voltage_label,
            "tech_class": o.tech_class_label,
            "sector": o.sector_name if o.needs_sector else "",
            "submit": _book_lines("", o.submit_no, o.submit_date),
            "submit_no": o.submit_no or "",
            "submit_date": o.submit_date,
            "response_print": (_book_lines(response_word, o.response_no, o.response_date)
                               if responded else response_word),
            "response": response_word,
            "response_no": (o.response_no or "") if responded else "",
            "response_date": o.response_date if responded else None,
            "labor_alloc": o.labor_alloc,
            "materials_alloc": o.materials_alloc,
            "total_materials_cost": o.total_materials_cost,
            "estimated_total": o.estimated_total,
            "head": o.committee_head_name or "",
            "start": _start_lines(o),
            "start_no": o.start_no or "",
            "start_date": o.start_date,
            "actual_start_date": o.actual_start_date,
            "end": end,
            "close_no": o.close_no or "",
            "close_date": o.close_date,
            "cancel_no": o.cancel_no or "",
            "cancel_date": o.cancel_date,
            "status": compute_status(o, ctx.today),
            "rolled": (f"إلى {y}" if (y := rolled_to_year(o, ctx.today)) else ""),
            "notes": o.notes,
        }
        for m in material_items:
            row[f"mat_{m.id}"] = o.effective_materials.get(m.id)
        rows.append(row)
    table = Table(columns=columns, rows=rows)
    table.compute_totals("project_name")
    return Report("قائمة تفصيلية بأوامر العمل", filters_text, [table],
                  [f"عدد أوامر العمل: {len(rows)}"], landscape=True)


def report_materials(orders, ctx, filters_text) -> Report:
    summary_cols = [
        Column("seq", "ت", "int", width=6),
        Column("name", "المادة", width=36),
        Column("unit", "الوحدة", width=10),
        Column("orders", "عدد أوامر العمل", "int", width=14),
        Column("qty", "الكمية الإجمالية", "int", width=18),
    ]
    summary_rows = []
    details: list[Table] = []
    for i, m in enumerate(ctx.materials, start=1):
        using = [o for o in orders if m.id in o.effective_materials]
        qty = sum(o.effective_materials[m.id] for o in using)
        summary_rows.append({"seq": i, "name": m.name, "unit": m.unit, "orders": len(using), "qty": qty})
        if using:
            rows = []
            for j, o in enumerate(sorted(using, key=lambda w: (w.order_year, w.order_no)), start=1):
                rows.append({
                    "seq": j,
                    "ref": f"{o.order_no}/{o.order_year}",
                    "order_type": o.order_type_label,
                    "project_name": o.project_name,
                    "status": compute_status(o, ctx.today),
                    "qty": o.effective_materials[m.id],
                })
            t = Table(
                title=f"{m.name} ({m.unit})",
                columns=[
                    Column("seq", "ت", "int", width=6),
                    Column("ref", "أمر العمل", width=12),
                    Column("order_type", "نوع الأمر", width=12),
                    Column("project_name", "اسم المشروع", width=40),
                    Column("status", "الحالة", "status", width=22),
                    Column("qty", f"الكمية ({m.unit})", "int", total=True, width=14),
                ],
                rows=rows,
            )
            t.compute_totals("project_name")
            details.append(t)
    summary = Table(columns=summary_cols, rows=summary_rows, title="الكميات الإجمالية")
    return Report("المواد الحاكمة الداخلة في أوامر العمل", filters_text, [summary] + details,
                  ["القابلوات والأسلاك بالمتر، والأعمدة والمحولات بالعدد.",
                   "المواد الحاكمة تخص أوامر عمل الشبكة الكهربائية فقط."])


def report_overdue(orders, ctx, filters_text, days: int) -> Report:
    rows = []
    for o in orders:
        if compute_status(o, ctx.today) != Status.SUBMITTED or o.submit_date is None:
            continue
        elapsed = (ctx.today - o.submit_date).days
        if elapsed >= days:
            rows.append((elapsed, o))
    rows.sort(key=lambda t: (-t[0], t[1].order_year, t[1].order_no))
    table = Table(
        columns=[
            Column("seq", "ت", "int", width=6),
            Column("ref", "أمر العمل", width=12),
            Column("order_type", "نوع الأمر", width=12),
            Column("project_name", "اسم المشروع", width=40),
            Column("submit_no", "رقم كتاب الرفع", width=14),
            Column("submit_date", "تاريخ كتاب الرفع", "date", width=14),
            Column("days", "عدد الأيام منذ الرفع", "int", width=16),
        ],
        rows=[{
            "seq": i, "ref": f"{o.order_no}/{o.order_year}", "order_type": o.order_type_label,
            "project_name": o.project_name, "submit_no": o.submit_no, "submit_date": o.submit_date,
            "days": elapsed,
        } for i, (elapsed, o) in enumerate(rows, start=1)],
        empty_text="لا توجد أوامر عمل متأخرة حسب المدة المحددة.",
    )
    return Report(f"أوامر العمل المرفوعة التي لم ترد موافقتها منذ {days} يوماً أو أكثر",
                  filters_text, [table], [f"العدد: {len(rows)}"])


def report_group(orders, ctx, filters_text, title_name: str = "") -> Report:
    """كلف (مبالغ التخصيص) ومواد مجموعة أوامر عمل مختارة: المجموع والتفصيل."""
    ordered = sorted(orders, key=lambda o: (o.order_year, o.order_no))
    # 1) الكلف
    cost_rows = []
    for i, o in enumerate(ordered, start=1):
        cost_rows.append({
            "seq": i, "ref": f"{o.order_no}/{o.order_year}", "order_type": o.order_type_label,
            "project_name": o.project_name, "work": o.work_description,
            "status": compute_status(o, ctx.today),
            "labor": o.labor_alloc, "materials": o.materials_alloc,
            "total_materials": o.total_materials_cost, "estimated": o.estimated_total,
        })
    costs = Table(
        title="الكلف (بالدينار العراقي)",
        columns=[
            Column("seq", "ت", "int", width=6, pct=3),
            Column("ref", "أمر العمل", width=12, pct=6),
            Column("order_type", "نوع الأمر", width=12, pct=7),
            Column("project_name", "اسم المشروع", width=40, pct=20),
            Column("work", "نوع العمل", width=26, pct=12),
            Column("status", "الحالة", "status", width=22, pct=11),
            Column("labor", "أجور العمل", "money", total=True, width=18, pct=10),
            Column("materials", "كلفة المواد غير المتوفرة", "money", total=True, width=18, pct=10),
            Column("total_materials", "الكلفة الكلية للمواد", "money", total=True, width=18, pct=10),
            Column("estimated", "الكلفة الكلية التخمينية", "money", total=True, width=20, pct=11),
        ],
        rows=cost_rows,
        empty_text="لا توجد أوامر عمل في المجموعة.",
    )
    costs.compute_totals("project_name")

    # 2) مجموع المواد
    used = [m for m in ctx.materials if any(m.id in o.effective_materials for o in ordered)]
    totals_rows = []
    for i, m in enumerate(used, start=1):
        using = [o for o in ordered if m.id in o.effective_materials]
        totals_rows.append({"seq": i, "name": m.name, "unit": m.unit, "orders": len(using),
                            "qty": sum(o.effective_materials[m.id] for o in using)})
    mat_totals = Table(
        title="مجموع المواد الحاكمة",
        columns=[
            Column("seq", "ت", "int", width=6, pct=5),
            Column("name", "المادة", width=36, pct=45),
            Column("unit", "الوحدة", width=10, pct=12),
            Column("orders", "عدد أوامر العمل", "int", width=14, pct=18),
            Column("qty", "الكمية الإجمالية", "int", width=18, pct=20),
        ],
        rows=totals_rows,
        empty_text="لا توجد مواد حاكمة مسجلة لأوامر العمل هذه.",
    )

    # 3) تفصيل المواد لكل أمر عمل
    tables = [costs, mat_totals]
    with_materials = [o for o in ordered if o.effective_materials]
    if used and with_materials:
        share = max(4, int(66 / len(used)))
        detail_cols = [
            Column("ref", "أمر العمل", width=12, pct=8),
            Column("project_name", "اسم المشروع", width=40, pct=26),
        ] + [Column(f"mat_{m.id}", f"{m.name} ({m.unit})", "int", total=True, width=16, pct=share) for m in used]
        detail_rows = []
        for o in with_materials:
            row = {"ref": f"{o.order_no}/{o.order_year}", "project_name": o.project_name}
            for m in used:
                row[f"mat_{m.id}"] = o.effective_materials.get(m.id)
            detail_rows.append(row)
        detail = Table(title="تفصيل المواد الحاكمة لكل أمر عمل", columns=detail_cols, rows=detail_rows)
        detail.compute_totals("project_name")
        tables.append(detail)

    title = f"كلف ومواد مجموعة أوامر العمل: {title_name}" if title_name else "كلف ومواد أوامر العمل المختارة"
    notes = [
        f"عدد أوامر العمل: {len(ordered)}",
        "الكلفة الكلية التخمينية = الكلفة الكلية للمواد + أجور العمل.",
        "مبالغ أوامر العمل التي لم ترد موافقتها هي المبالغ المطلوبة عند الإعداد؛ وبعد الموافقة هي المبالغ المعتمدة.",
        "المواد الحاكمة تخص أوامر عمل الشبكة الكهربائية فقط. القابلوات والأسلاك بالمتر، والأعمدة والمحولات بالعدد.",
    ]
    return Report(title, filters_text, tables, notes, landscape=True)


def build_report(kind: str, orders: list[WorkOrder], ctx: ReportContext, f: OrderFilter,
                 group_by: str = "order_type", overdue_days: int = 30) -> Report:
    filtered = apply_filter(orders, f, ctx.today)
    filters_text = describe_filter(f, ctx)
    if kind == "progress":
        return report_progress(filtered, group_by, ctx, filters_text)
    if kind == "status":
        return report_status(filtered, group_by, ctx, filters_text)
    if kind == "money":
        return report_money(filtered, group_by, ctx, filters_text)
    if kind == "detail":
        return report_detail(filtered, ctx, filters_text)
    if kind == "materials":
        return report_materials(filtered, ctx, filters_text)
    if kind == "overdue":
        return report_overdue(filtered, ctx, filters_text, overdue_days)
    if kind == "group":
        return report_group(filtered, ctx, filters_text, f.group_name)
    raise ValueError(kind)

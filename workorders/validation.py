"""قواعد التحقق ومنع الأخطاء قبل حفظ أمر العمل."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .constants import FIRST_YEAR, ORDER_TYPES, RESPONSES, TECH_CLASSES, VOLTAGES, WORK_TYPES
from .models import WorkOrder
from .textutil import fmt_date

MAX_PROJECT_NAME = 300


@dataclass
class Issue:
    field: str  # اسم الحقل (لتحديده باللون الأحمر في الشاشة)
    message: str


def allowed_years(today: date) -> list[int]:
    """السنوات المتاحة: من 2026 حتى السنة القادمة."""
    return list(range(FIRST_YEAR, max(FIRST_YEAR, today.year) + 2))


def number_conflicts(o: WorkOrder, others: list[WorkOrder]) -> list[str]:
    """قواعد رقم أمر العمل:
    - لا يتكرر الرقم في نفس السنة أبداً، حتى لو اختلف نوع الأمر.
    - لا يُستخدم الرقم ما دام أمر العمل الذي يحمله (من سنة سابقة) غير منتهٍ.
      المنتهي: المغلق أو الملغى أو المرفوض.
    `others`: أوامر العمل الأخرى التي تحمل نفس الرقم.
    """
    messages = []
    if o.order_no is None or o.order_year is None:
        return messages
    for x in sorted(others, key=lambda w: w.order_year or 0):
        if o.id is not None and x.id == o.id:
            continue
        if x.order_no != o.order_no:
            continue
        if x.order_year == o.order_year:
            messages.append(
                f"رقم أمر العمل {o.order_no} مستخدم مسبقاً لسنة {x.order_year} "
                f"({x.order_type_label}) في مشروع «{x.project_name}». "
                "لا يجوز تكرار الرقم في نفس السنة حتى لو اختلف نوع الأمر."
            )
        elif x.order_year < o.order_year:
            if not x.is_finished:
                messages.append(
                    f"لا يمكن استخدام الرقم {o.order_no} لأن أمر العمل {x.ref} "
                    f"(«{x.project_name}») ما زال غير مغلق ({x.status_label})."
                )
        else:  # أمر لاحق يحمل نفس الرقم
            if not o.is_finished:
                messages.append(
                    f"الرقم {o.order_no} مستخدم في أمر عمل لاحق ({x.ref} – «{x.project_name}»)، "
                    "لذلك يجب أن يكون هذا الأمر مغلقاً أو ملغى أو مرفوضاً."
                )
    return messages


def _check_pair(issues, no, when, field_prefix, title):
    if bool(no) != bool(when):
        missing = "التاريخ" if no else "الرقم"
        issues.append(Issue(f"{field_prefix}_{'date' if no else 'no'}",
                            f"{title}: أدخل {missing} أيضاً (الرقم والتاريخ معاً)."))
    if no is not None and no != "" and not str(no).isdigit():
        issues.append(Issue(f"{field_prefix}_no", f"{title}: الرقم يجب أن يحتوي أرقاماً فقط."))


def validate(o: WorkOrder, others_same_no: list[WorkOrder], today: date) -> list[Issue]:
    issues: list[Issue] = []
    add = lambda f, m: issues.append(Issue(f, m))  # noqa: E731

    # ---------------- البيانات الأساسية ----------------
    if o.order_no is None:
        add("order_no", "أدخل رقم أمر العمل.")
    elif o.order_no <= 0:
        add("order_no", "رقم أمر العمل يجب أن يكون أكبر من صفر.")
    if o.order_year is None:
        add("order_year", "اختر سنة أمر العمل.")
    elif o.order_year not in allowed_years(today):
        add("order_year", "سنة أمر العمل خارج المدى المسموح.")
    if o.order_type not in ORDER_TYPES:
        add("order_type", "اختر نوع أمر العمل (استثماري / تشغيلي / تنفيذ أمانة).")
    if not o.project_name.strip():
        add("project_name", "أدخل اسم المشروع.")
    elif len(o.project_name) > MAX_PROJECT_NAME:
        add("project_name", f"اسم المشروع طويل جداً (الحد {MAX_PROJECT_NAME} حرف).")
    if o.work_type not in WORK_TYPES:
        add("work_type", "اختر نوع العمل.")
    if o.is_network:
        if o.voltage not in VOLTAGES:
            add("voltage", "اختر مستوى الجهد.")
        if o.needs_tech_class and o.tech_class not in TECH_CLASSES:
            add("tech_class", "اختر التصنيف الفني (استحداث مغذي جديد / تأهيل مغذي موجود).")
        if o.needs_sector and o.sector_id is None:
            add("sector_id", "اختر قطاع التوزيع.")

    for msg in number_conflicts(o, others_same_no):
        add("order_no", msg)

    # ---------------- الكتب الرسمية (رقم + تاريخ) ----------------
    _check_pair(issues, o.submit_no, o.submit_date, "submit", "كتاب الرفع إلى الشركة العامة")
    if o.response not in RESPONSES:
        add("response", "اختر رد الشركة العامة.")
    if o.response != "pending":
        _check_pair(issues, o.response_no, o.response_date, "response", "كتاب رد الشركة العامة")
        if not o.response_no and not o.response_date:
            add("response_no", "أدخل رقم وتاريخ كتاب رد الشركة العامة.")
    _check_pair(issues, o.start_no, o.start_date, "start", "الأمر الإداري بالمباشرة")
    _check_pair(issues, o.close_no, o.close_date, "close", "كتاب غلق أمر العمل")
    _check_pair(issues, o.cancel_no, o.cancel_date, "cancel", "كتاب إلغاء أمر العمل")

    # ---------------- تسلسل المراحل ----------------
    if o.response != "pending" and not o.has_submit:
        add("response", "لا يمكن إدخال رد الشركة العامة قبل إدخال كتاب الرفع.")
    if o.response == "rejected":
        if o.labor_alloc is not None or o.materials_alloc is not None:
            add("labor_alloc", "أمر العمل المرفوض لا يكون له تخصيص مالي.")
        if o.committee_head_id is not None or o.has_start:
            add("start_no", "أمر العمل المرفوض لا يمكن المباشرة به. احذف بيانات التنفيذ أو غيّر الرد.")
        if o.has_close:
            add("close_no", "أمر العمل المرفوض لا يمكن غلقه. احذف بيانات الغلق أو غيّر الرد.")
        if o.has_cancel:
            add("cancel_no", "أمر العمل المرفوض لا يحتاج إلى إلغاء.")
    if o.response != "approved":
        if o.response == "pending" and (o.labor_alloc is not None or o.materials_alloc is not None):
            add("labor_alloc", "مبالغ التخصيص تُدخل بعد ورود الموافقة.")
        if o.response == "pending" and (o.has_start or o.committee_head_id is not None):
            add("start_no", "لا يمكن إدخال بيانات التنفيذ قبل ورود الموافقة.")
    if o.has_start and o.committee_head_id is None:
        add("committee_head", "اختر اسم رئيس لجنة التنفيذ قبل إدخال أمر المباشرة.")
    if o.has_close and not o.has_start:
        add("close_no", "لا يمكن غلق أمر العمل قبل إدخال الأمر الإداري بالمباشرة.")
    if o.has_close and o.has_cancel:
        add("cancel_no", "لا يمكن أن يكون أمر العمل مغلقاً وملغى في نفس الوقت.")

    for name, value in (("labor_alloc", o.labor_alloc), ("materials_alloc", o.materials_alloc)):
        if value is not None and value < 0:
            add(name, "المبلغ لا يمكن أن يكون سالباً.")
    for qty in o.materials.values():
        if qty is None or qty <= 0:
            add("materials", "كمية المادة يجب أن تكون أكبر من صفر.")
            break

    # ---------------- التواريخ ----------------
    dated = [
        ("submit_date", "تاريخ كتاب الرفع", o.submit_date),
        ("response_date", "تاريخ كتاب رد الشركة العامة", o.response_date if o.response != "pending" else None),
        ("start_date", "تاريخ أمر المباشرة", o.start_date),
        ("close_date", "تاريخ الغلق", o.close_date),
        ("cancel_date", "تاريخ الإلغاء", o.cancel_date),
    ]
    for fname, title, d in dated:
        if d is not None and d > today:
            add(fname, f"{title} ({fmt_date(d)}) لا يمكن أن يكون بعد تاريخ اليوم.")

    sequence = dated[:4]  # الرفع ← الرد ← المباشرة ← الغلق
    previous = None
    for fname, title, d in sequence:
        if d is None:
            continue
        if previous is not None and d < previous[2]:
            add(fname, f"{title} ({fmt_date(d)}) لا يمكن أن يسبق {previous[1]} ({fmt_date(previous[2])}).")
        previous = (fname, title, d)
    if o.cancel_date is not None:
        for fname, title, d in sequence:
            if d is not None and o.cancel_date < d:
                add("cancel_date", f"تاريخ الإلغاء ({fmt_date(o.cancel_date)}) لا يمكن أن يسبق {title} ({fmt_date(d)}).")
                break

    return issues

"""قواعد التحقق ومنع الأخطاء قبل حفظ أمر العمل."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .constants import (
    FINISHED_STATUSES,
    FIRST_YEAR,
    ORDER_TYPES,
    RESPONSES,
    STATUS_LABELS,
    TECH_CLASSES,
    VOLTAGES,
    WORK_TYPES,
)
from .models import WorkOrder, compute_status
from .textutil import fmt_date

MAX_PROJECT_NAME = 300


@dataclass
class Issue:
    field: str  # اسم الحقل (لتحديده باللون الأحمر في الشاشة)
    message: str


def allowed_years(today: date) -> list[int]:
    """السنوات المتاحة: من 2026 حتى السنة القادمة."""
    return list(range(FIRST_YEAR, max(FIRST_YEAR, today.year) + 2))


def number_conflicts(o: WorkOrder, others: list[WorkOrder], today: date | None = None) -> list[str]:
    """قواعد رقم أمر العمل:
    - لا يتكرر الرقم في نفس السنة أبداً، حتى لو اختلف نوع الأمر.
    - لا يُستخدم الرقم ما دام أمر العمل الذي يحمله (من سنة سابقة) غير منتهٍ.
      المنتهي: المغلق أو الملغى (بكتاب أو تلقائياً) أو المرفوض.
    `others`: أوامر العمل الأخرى التي تحمل نفس الرقم.
    """
    messages = []

    def finished(w: WorkOrder) -> bool:
        return compute_status(w, today) in FINISHED_STATUSES

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
            if not finished(x):
                messages.append(
                    f"لا يمكن استخدام الرقم {o.order_no} لأن أمر العمل {x.ref} "
                    f"(«{x.project_name}») ما زال غير مغلق ({STATUS_LABELS[compute_status(x, today)]})."
                )
        else:  # أمر لاحق يحمل نفس الرقم
            if not finished(o):
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

    for msg in number_conflicts(o, others_same_no, today):
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
    if (o.start_no or o.start_date) and o.actual_start_date is None:
        add("actual_start_date", "أدخل تاريخ المباشرة الفعلي (يؤخذ افتراضياً من تاريخ الأمر الإداري).")
    if o.actual_start_date is not None and not (o.start_no or o.start_date):
        add("start_no", "أدخل رقم وتاريخ الأمر الإداري بالمباشرة مع تاريخ المباشرة الفعلي.")
    actual = o.actual_start_date
    if actual is not None and o.order_year is not None and actual.year > o.order_year:
        add("actual_start_date",
            f"تاريخ المباشرة الفعلي ({fmt_date(actual)}) يجب أن يكون ضمن سنة أمر العمل ({o.order_year})، "
            "لأن أمر العمل الذي لا يُباشر به خلال سنته يُلغى تلقائياً.")
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
    submit = ("submit_date", "تاريخ كتاب الرفع", o.submit_date)
    response = ("response_date", "تاريخ كتاب رد الشركة العامة",
                o.response_date if o.response != "pending" else None)
    start_book = ("start_date", "تاريخ الأمر الإداري بالمباشرة", o.start_date)
    start_actual = ("actual_start_date", "تاريخ المباشرة الفعلي", o.actual_start_date)
    close = ("close_date", "تاريخ الغلق", o.close_date)
    cancel = ("cancel_date", "تاريخ الإلغاء", o.cancel_date)
    dated = [submit, response, start_book, start_actual, close, cancel]
    for fname, title, d in dated:
        if d is not None and d > today:
            add(fname, f"{title} ({fmt_date(d)}) لا يمكن أن يكون بعد تاريخ اليوم.")

    # تسلسل المراحل: الرفع ← الرد ← المباشرة (كتابها وتاريخها الفعلي بأي ترتيب بينهما) ← الغلق
    # ملاحظة: المباشرة قبل تاريخ الموافقة ليست خطأً مانعاً بل تنبيه فقط (انظر warnings)
    order_rules = [
        (response, submit),
        (close, start_book), (close, start_actual),
    ]
    for (fname, title, d), (_, prev_title, prev) in order_rules:
        if d is not None and prev is not None and d < prev:
            add(fname, f"{title} ({fmt_date(d)}) لا يمكن أن يسبق {prev_title} ({fmt_date(prev)}).")
    sequence = dated[:5]
    if o.cancel_date is not None:
        for fname, title, d in sequence:
            if d is not None and o.cancel_date < d:
                add("cancel_date", f"تاريخ الإلغاء ({fmt_date(o.cancel_date)}) لا يمكن أن يسبق {title} ({fmt_date(d)}).")
                break

    return issues


def warnings(o: WorkOrder) -> list[Issue]:
    """تنبيهات لا تمنع الحفظ، لكن يجب أن يؤكدها المستخدم."""
    result = []
    if o.started_before_approval:
        for field, title, d in (("start_date", "تاريخ الأمر الإداري بالمباشرة", o.start_date),
                                ("actual_start_date", "تاريخ المباشرة الفعلي", o.actual_start_date)):
            if d is not None and d < o.response_date:
                result.append(Issue(field, f"{title} ({fmt_date(d)}) يسبق تاريخ كتاب الموافقة "
                                           f"({fmt_date(o.response_date)})."))
    return result

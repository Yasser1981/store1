"""نموذج بيانات أمر العمل، وحساب الحالة والتدوير تلقائياً."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .constants import (
    FINISHED_STATUSES,
    ORDER_TYPES,
    STATUS_LABELS,
    TECH_CLASSES,
    VOLTAGES,
    VOLTAGES_WITH_SECTOR,
    VOLTAGES_WITH_TECH,
    WORK_TYPES,
    Status,
)


@dataclass
class LookupItem:
    """عنصر في قائمة قابلة للتعديل (قطاع، رئيس لجنة، مادة)."""

    id: int
    name: str
    active: bool = True
    unit: str | None = None  # للمواد فقط
    sort_order: int = 0


@dataclass
class WorkOrder:
    id: int | None = None

    # 1. البيانات الأساسية
    order_no: int | None = None
    order_year: int | None = None
    order_type: str | None = None
    project_name: str = ""
    work_type: str | None = None
    voltage: str | None = None
    tech_class: str | None = None
    sector_id: int | None = None

    # 2. كتاب الرفع إلى الشركة العامة
    submit_no: str | None = None
    submit_date: date | None = None

    # 3. رد الشركة العامة
    response: str = "pending"
    response_no: str | None = None
    response_date: date | None = None
    labor_alloc: int | None = None
    materials_alloc: int | None = None

    # 4. التنفيذ
    committee_head_id: int | None = None
    start_no: str | None = None
    start_date: date | None = None

    # 5. الغلق
    close_no: str | None = None
    close_date: date | None = None

    # 6. الإلغاء (ممكن في أي مرحلة قبل الغلق)
    cancel_no: str | None = None
    cancel_date: date | None = None

    notes: str = ""

    # المواد الحاكمة: رقم المادة ← الكمية
    materials: dict[int, int] = field(default_factory=dict)

    created_at: str | None = None
    updated_at: str | None = None

    # حقول للعرض فقط (تملأ من قاعدة البيانات)
    sector_name: str | None = None
    committee_head_name: str | None = None

    # ------------------------------------------------------------------
    @property
    def ref(self) -> str:
        """تعريف أمر العمل: (10 لسنة 2026)."""
        return f"{self.order_no} لسنة {self.order_year}"

    @property
    def has_submit(self) -> bool:
        return bool(self.submit_no or self.submit_date)

    @property
    def has_start(self) -> bool:
        return bool(self.start_no or self.start_date)

    @property
    def has_close(self) -> bool:
        return bool(self.close_no or self.close_date)

    @property
    def has_cancel(self) -> bool:
        return bool(self.cancel_no or self.cancel_date)

    @property
    def is_network(self) -> bool:
        return self.work_type == "network"

    @property
    def needs_tech_class(self) -> bool:
        return self.is_network and self.voltage in VOLTAGES_WITH_TECH

    @property
    def needs_sector(self) -> bool:
        return self.is_network and self.voltage in VOLTAGES_WITH_SECTOR

    # تسميات للعرض --------------------------------------------------------
    @property
    def order_type_label(self) -> str:
        return ORDER_TYPES.get(self.order_type or "", "")

    @property
    def work_type_label(self) -> str:
        return WORK_TYPES.get(self.work_type or "", "")

    @property
    def voltage_label(self) -> str:
        return VOLTAGES.get(self.voltage or "", "") if self.is_network else ""

    @property
    def tech_class_label(self) -> str:
        return TECH_CLASSES.get(self.tech_class or "", "") if self.needs_tech_class else ""

    @property
    def work_description(self) -> str:
        """وصف مختصر لنوع العمل: (شبكة كهربائية 11 ك.ف – استحداث مغذي جديد)."""
        text = self.work_type_label
        if self.voltage_label:
            text += f" {self.voltage_label}"
        if self.tech_class_label:
            text += f" – {self.tech_class_label}"
        return text

    @property
    def status(self) -> str:
        return compute_status(self)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def is_finished(self) -> bool:
        return self.status in FINISHED_STATUSES


def compute_status(o: WorkOrder) -> str:
    """تُحسب حالة أمر العمل تلقائياً من البيانات المدخلة."""
    if o.has_cancel:
        return Status.CANCELLED
    if o.response == "rejected":
        return Status.REJECTED
    if o.has_close:
        return Status.CLOSED
    if o.has_start:
        return Status.STARTED
    if o.response == "approved":
        return Status.APPROVED
    if o.has_submit:
        return Status.SUBMITTED
    return Status.DRAFT


def rolled_to_year(o: WorkOrder, today: date) -> int | None:
    """التدوير التلقائي:
    أمر العمل المباشر به الذي لم يُغلق حتى نهاية سنة المباشرة يُعتبر مدوّراً
    إلى السنة التالية، وهكذا لكل سنة لاحقة لا يُغلق فيها.
    ترجع الدالة آخر سنة دُوِّر إليها الأمر، أو None إذا لم يُدوَّر.
    """
    if not o.start_date:
        return None
    start_year = o.start_date.year
    if o.close_date:
        end_year = o.close_date.year
    elif o.cancel_date:
        end_year = o.cancel_date.year
    else:
        end_year = today.year
    return end_year if end_year > start_year else None


def rolled_text(o: WorkOrder, today: date) -> str:
    year = rolled_to_year(o, today)
    if year is None:
        return ""
    return f"مدوّر إلى {year}"

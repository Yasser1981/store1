"""شاشة إدخال وتعديل أمر العمل."""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..constants import (
    ORDER_TYPES,
    RESPONSES,
    STATUS_COLORS,
    STATUS_LABELS,
    TECH_CLASSES,
    VOLTAGES,
    VOLTAGES_WITH_SECTOR,
    VOLTAGES_WITH_TECH,
    WORK_TYPES,
)
from ..models import WorkOrder, compute_status, rolled_to_year
from ..repository import Repository
from ..textutil import clean_spaces
from ..validation import Issue, allowed_years, number_conflicts, validate
from ..validation import warnings as validation_warnings
from . import messages
from .style import set_error
from .widgets import (
    DateEdit,
    MoneyEdit,
    NumberEdit,
    StatusChip,
    combo_value,
    fill_combo,
    make_combo,
    make_head_combo,
    set_combo_value,
)

# قيمة مؤقتة لرئيس لجنة جديد لم يُحفظ بعد في القائمة
NEW_HEAD = -1

SAVE_AND_NEW = 2  # نتيجة خاصة: حفظ ثم فتح شاشة أمر جديد


class OrderDialog(QDialog):
    def __init__(self, repo: Repository, order: WorkOrder | None = None, parent=None,
                 today: date | None = None, defaults: dict | None = None):
        super().__init__(parent)
        self.repo = repo
        self.today = today or date.today()
        self.is_new = order is None or order.id is None
        self.order = order or WorkOrder(order_year=self.today.year)
        if defaults and self.is_new:
            for key, value in defaults.items():
                setattr(self.order, key, value)
        self.saved_id: int | None = None
        self._loading = True

        self.setWindowTitle("إدخال أمر عمل جديد" if self.is_new else f"تعديل أمر العمل {self.order.ref}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1040, 860)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)

        self.fields: dict[str, QWidget] = {}
        self._numbered_sections: list[tuple[QGroupBox, str]] = []
        self._build()
        self._load(self.order)
        self._loading = False
        self._refresh()
        self._initial = self._snapshot()

    # ==================================================================
    # بناء الواجهة
    # ==================================================================
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        # ---- الترويسة: العنوان والحالة
        header = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("pageTitle")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.rolled_label = QLabel()
        self.rolled_label.setStyleSheet("color:#6a1b9a; font-weight:bold;")
        header.addWidget(self.rolled_label)
        header.addWidget(QLabel("الحالة:"))
        self.status_chip = StatusChip()
        self.status_chip.setMinimumWidth(220)
        header.addWidget(self.status_chip)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.scroll = scroll
        body = QWidget()
        body.setObjectName("page")
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(4, 0, 4, 4)
        self.body_layout.setSpacing(6)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._build_basic()
        self._build_costs()
        self._build_submit()
        self._build_response()
        self._build_materials()
        self._build_execution()
        self._build_close()
        self._build_cancel()
        self._build_notes()
        self.body_layout.addStretch(1)

        # ---- الأزرار
        buttons = QHBoxLayout()
        self.save_btn = QPushButton("حفظ")
        self.save_btn.setObjectName("primary")
        self.save_btn.setMinimumWidth(140)
        self.save_new_btn = QPushButton("حفظ وإدخال أمر جديد")
        self.close_btn = QPushButton("خروج بدون حفظ")
        for b in (self.save_btn, self.save_new_btn, self.close_btn):
            b.setAutoDefault(False)
            b.setDefault(False)
        self.save_btn.clicked.connect(lambda: self._save(and_new=False))
        self.save_new_btn.clicked.connect(lambda: self._save(and_new=True))
        self.close_btn.clicked.connect(self.reject)
        hint = QLabel("الحقول المعلّمة بـ (*) إلزامية. زر Enter ينقلك إلى الحقل التالي.")
        hint.setObjectName("hint")
        buttons.addWidget(hint)
        buttons.addStretch(1)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.save_new_btn)
        buttons.addWidget(self.close_btn)
        outer.addLayout(buttons)

    def _section(self, title: str) -> tuple[QGroupBox, QGridLayout]:
        # الأقسام المرقمة يُعاد ترقيمها تلقائياً حسب الأقسام الظاهرة
        match = re.match(r"^\d+\.\s*", title)
        if match:
            title = title[match.end():]
            self._numbered_sections.append((None, title))
        box = QGroupBox(title)
        if match:
            self._numbered_sections[-1] = (box, title)
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self.body_layout.addWidget(box)
        return box, grid

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lbl

    def _disabled_hint(self, grid: QGridLayout, row: int) -> QLabel:
        lbl = QLabel()
        lbl.setObjectName("hint")
        grid.addWidget(lbl, row, 0, 1, 4)
        return lbl

    def _build_basic(self):
        box, g = self._section("1. البيانات الأساسية لأمر العمل")
        self.no_edit = NumberEdit(max_digits=6, placeholder="مثال: 10")
        self.no_edit.setMaximumWidth(160)
        self.year_combo = make_combo([(y, str(y)) for y in allowed_years(self.today)])
        self.type_combo = make_combo(ORDER_TYPES)
        self.no_check = QLabel()
        self.no_check.setWordWrap(True)
        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("مثال: استحداث مغذي 11 ك.ف ...")
        self.project_edit.setMaxLength(300)
        self.work_combo = make_combo(WORK_TYPES)
        self.work_combo.setMinimumWidth(260)
        self.voltage_combo = make_combo(VOLTAGES)
        self.tech_combo = make_combo(TECH_CLASSES)
        self.sector_combo = make_combo([])

        g.addWidget(self._label("رقم أمر العمل *"), 0, 0)
        g.addWidget(self.no_edit, 0, 1)
        g.addWidget(self._label("السنة *"), 0, 2)
        g.addWidget(self.year_combo, 0, 3)
        g.addWidget(self._label("نوع أمر العمل *"), 1, 0)
        g.addWidget(self.type_combo, 1, 1)
        g.addWidget(self.no_check, 1, 2, 1, 2)
        g.addWidget(self._label("اسم المشروع *"), 2, 0)
        g.addWidget(self.project_edit, 2, 1, 1, 3)
        g.addWidget(self._label("نوع العمل *"), 3, 0)
        g.addWidget(self.work_combo, 3, 1)
        self.voltage_lbl = self._label("مستوى الجهد *")
        g.addWidget(self.voltage_lbl, 3, 2)
        g.addWidget(self.voltage_combo, 3, 3)
        self.tech_lbl = self._label("التصنيف الفني *")
        g.addWidget(self.tech_lbl, 4, 0)
        g.addWidget(self.tech_combo, 4, 1)
        self.sector_lbl = self._label("قطاع التوزيع *")
        g.addWidget(self.sector_lbl, 4, 2)
        g.addWidget(self.sector_combo, 4, 3)

        self.fields.update(order_no=self.no_edit, order_year=self.year_combo, order_type=self.type_combo,
                           project_name=self.project_edit, work_type=self.work_combo,
                           voltage=self.voltage_combo, tech_class=self.tech_combo, sector_id=self.sector_combo)
        for w in (self.no_edit, self.project_edit):
            w.textChanged.connect(self._refresh)
        for c in (self.year_combo, self.type_combo, self.work_combo, self.voltage_combo,
                  self.tech_combo, self.sector_combo):
            c.currentIndexChanged.connect(self._refresh)

    def _build_submit(self):
        box, g = self._section("2. كتاب رفع أمر العمل إلى الشركة العامة لتوزيع كهرباء الفرات الأوسط")
        self.submit_no = NumberEdit(placeholder="رقم الكتاب")
        self.submit_date = DateEdit()
        g.addWidget(self._label("رقم الكتاب"), 0, 0)
        g.addWidget(self.submit_no, 0, 1)
        g.addWidget(self._label("تاريخ الكتاب"), 0, 2)
        g.addWidget(self.submit_date, 0, 3)
        self.fields.update(submit_no=self.submit_no, submit_date=self.submit_date.line)
        self.submit_no.textChanged.connect(self._refresh)
        self.submit_date.changed.connect(self._refresh)

    def _build_response(self):
        box, g = self._section("3. رد الشركة العامة (موافقة المدير العام)")
        self.response_box = box
        self.response_hint = self._disabled_hint(g, 0)
        self.response_combo = make_combo(RESPONSES)
        self.response_no = NumberEdit(placeholder="رقم الكتاب")
        self.response_date = DateEdit()
        g.addWidget(self._label("الرد"), 1, 0)
        g.addWidget(self.response_combo, 1, 1)
        self.response_no_lbl = self._label("رقم كتاب الموافقة")
        self.response_date_lbl = self._label("تاريخ كتاب الموافقة")
        g.addWidget(self.response_no_lbl, 2, 0)
        g.addWidget(self.response_no, 2, 1)
        g.addWidget(self.response_date_lbl, 2, 2)
        g.addWidget(self.response_date, 2, 3)
        self.approval_costs_hint = QLabel(
            "إذا تضمنت الموافقة تعديلاً في أجور العمل أو كلفة المواد غير المتوفرة، عدّل المبالغ في قسم (الكلف).")
        self.approval_costs_hint.setObjectName("hint")
        self.approval_costs_hint.setWordWrap(True)
        g.addWidget(self.approval_costs_hint, 3, 0, 1, 4)
        self.fields.update(response=self.response_combo, response_no=self.response_no,
                           response_date=self.response_date.line)
        self.response_combo.currentIndexChanged.connect(self._refresh)
        self.response_no.textChanged.connect(self._refresh)
        self.response_date.changed.connect(self._refresh)

    def _build_costs(self):
        box, g = self._section("2. الكلف (بالدينار العراقي)")
        hint = QLabel("تُدخل المبالغ المطلوبة عند إعداد أمر العمل، وتُعدَّل لاحقاً إذا جاءت الموافقة بمبالغ مختلفة.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        g.addWidget(hint, 0, 0, 1, 4)
        self.labor_edit = MoneyEdit()
        self.materials_alloc_edit = MoneyEdit()
        self.total_materials_edit = MoneyEdit()
        self.estimated_label = QLabel()
        self.estimated_label.setStyleSheet(
            "font-weight:bold; color:#0d3c61; background:#eef4fb; border:1px solid #b8c4d2; "
            "border-radius:5px; padding:6px 10px;")
        self.estimated_label.setToolTip("تُحسب تلقائياً: الكلفة الكلية للمواد + أجور العمل")
        g.addWidget(self._label("أجور العمل"), 1, 0)
        g.addWidget(self.labor_edit, 1, 1)
        g.addWidget(self._label("كلفة المواد غير المتوفرة (للشراء)"), 1, 2)
        g.addWidget(self.materials_alloc_edit, 1, 3)
        g.addWidget(self._label("الكلفة الكلية للمواد\n(المتوفرة وغير المتوفرة)"), 2, 0)
        g.addWidget(self.total_materials_edit, 2, 1)
        g.addWidget(self._label("الكلفة الكلية التخمينية\nللمشروع (تلقائياً)"), 2, 2)
        g.addWidget(self.estimated_label, 2, 3)
        self.fields.update(labor_alloc=self.labor_edit.edit, materials_alloc=self.materials_alloc_edit.edit,
                           total_materials_cost=self.total_materials_edit.edit)
        for w in (self.labor_edit, self.materials_alloc_edit, self.total_materials_edit):
            w.textChanged.connect(self._refresh)

    def _build_materials(self):
        box, g = self._section("4. المواد الحاكمة الداخلة في المشروع (اترك الحقل فارغاً إذا لم تدخل المادة)")
        self.materials_box = box  # يظهر لأوامر عمل الشبكة الكهربائية فقط
        self.material_edits: dict[int, NumberEdit] = {}
        items = self.repo.materials()
        active_ids = {m.id for m in items}
        # مادة مخفية لكنها مسجلة في هذا الأمر تبقى ظاهرة فيه
        extra = [m for m in self.repo.materials(include_inactive=True)
                 if m.id not in active_ids and m.id in self.order.materials]
        items = items + extra
        half = (len(items) + 1) // 2
        g.setColumnStretch(1, 0)
        g.setColumnStretch(3, 0)
        for i, m in enumerate(items):
            row, col = (i, 0) if i < half else (i - half, 4)
            name = QLabel(m.name)
            edit = NumberEdit(grouping=True, max_digits=9)
            edit.setFixedWidth(120)
            unit = QLabel(m.unit or "")
            unit.setObjectName("hint")
            g.addWidget(name, row, col)
            g.addWidget(edit, row, col + 1)
            g.addWidget(unit, row, col + 2)
            edit.textChanged.connect(self._refresh)
            self.material_edits[m.id] = edit
        if items:
            g.setColumnMinimumWidth(3, 30)
        self.fields["materials"] = box

    def _build_execution(self):
        box, g = self._section("5. تنفيذ أمر العمل")
        self.exec_box = box
        self.exec_hint = self._disabled_hint(g, 0)
        self.head_combo = make_head_combo()
        self._fill_heads()
        self.start_no = NumberEdit(placeholder="رقم الأمر الإداري")
        self.start_date = DateEdit()
        self.actual_start = DateEdit()
        self.actual_start.line.setToolTip("يؤخذ تلقائياً من تاريخ الأمر الإداري، ويمكن تعديله إذا اختلف تاريخ المباشرة الفعلي")
        actual_hint = QLabel("يُملأ تلقائياً من تاريخ الأمر الإداري، ويمكن تعديله")
        actual_hint.setObjectName("hint")
        g.addWidget(self._label("رئيس لجنة التنفيذ"), 1, 0)
        g.addWidget(self.head_combo, 1, 1, 1, 3)
        g.addWidget(self._label("رقم الأمر الإداري بالمباشرة"), 2, 0)
        g.addWidget(self.start_no, 2, 1)
        g.addWidget(self._label("تاريخ الأمر الإداري"), 2, 2)
        g.addWidget(self.start_date, 2, 3)
        g.addWidget(self._label("تاريخ المباشرة الفعلي"), 3, 0)
        g.addWidget(self.actual_start, 3, 1)
        g.addWidget(actual_hint, 3, 2, 1, 2)
        self.early_warning = QLabel()
        self.early_warning.setWordWrap(True)
        self.early_warning.setStyleSheet(
            "color:#8a4b00; background:#fff3e0; border:1px solid #f0b46a; border-radius:5px; padding:6px;")
        self.early_warning.hide()
        g.addWidget(self.early_warning, 4, 0, 1, 4)
        self.fields.update(committee_head=self.head_combo, start_no=self.start_no, start_date=self.start_date.line,
                           actual_start_date=self.actual_start.line)
        # تاريخ المباشرة الفعلي يتبع تاريخ الأمر الإداري ما لم يعدّله المستخدم
        self._actual_follows = True
        self._syncing_actual = False
        self.head_combo.currentTextChanged.connect(self._refresh)
        self.start_no.textChanged.connect(self._refresh)
        self.start_date.changed.connect(self._on_start_date_changed)
        self.actual_start.changed.connect(self._on_actual_changed)

    def _on_start_date_changed(self):
        if self._actual_follows and not self._loading:
            d = self.start_date.date()
            if d is not None or self.start_date.is_empty():
                self._syncing_actual = True
                self.actual_start.set_date(d)
                self._syncing_actual = False
        self._refresh()

    def _on_actual_changed(self):
        if not self._syncing_actual and not self._loading:
            actual = self.actual_start.date()
            self._actual_follows = self.actual_start.is_empty() or actual == self.start_date.date()
        self._refresh()

    def _fill_heads(self):
        heads = self.repo.committee_heads()
        ids = {h.id for h in heads}
        if self.order.committee_head_id and self.order.committee_head_id not in ids:
            heads += [h for h in self.repo.committee_heads(include_inactive=True)
                      if h.id == self.order.committee_head_id]
        fill_combo(self.head_combo, [(h.id, h.name) for h in heads])
        self.head_combo.setCurrentIndex(-1)
        self.head_combo.setEditText("")

    def _build_close(self):
        box, g = self._section("6. غلق أمر العمل (بعد إكمال الاستلام)")
        self.close_box = box
        self.close_hint = self._disabled_hint(g, 0)
        self.close_no = NumberEdit(placeholder="رقم الكتاب / الأمر")
        self.close_date = DateEdit()
        g.addWidget(self._label("رقم كتاب أو أمر الغلق"), 1, 0)
        g.addWidget(self.close_no, 1, 1)
        g.addWidget(self._label("تاريخ الغلق"), 1, 2)
        g.addWidget(self.close_date, 1, 3)
        self.fields.update(close_no=self.close_no, close_date=self.close_date.line)
        self.close_no.textChanged.connect(self._refresh)
        self.close_date.changed.connect(self._refresh)

    def _build_cancel(self):
        box, g = self._section("7. إلغاء أمر العمل")
        self.cancel_box = box
        self.cancel_hint = self._disabled_hint(g, 0)
        self.cancel_check = QCheckBox("تم إلغاء أمر العمل")
        self.cancel_no = NumberEdit(placeholder="رقم الكتاب")
        self.cancel_date = DateEdit()
        g.addWidget(self.cancel_check, 1, 0, 1, 2)
        self.cancel_no_lbl = self._label("رقم كتاب الإلغاء")
        self.cancel_date_lbl = self._label("تاريخ كتاب الإلغاء")
        g.addWidget(self.cancel_no_lbl, 2, 0)
        g.addWidget(self.cancel_no, 2, 1)
        g.addWidget(self.cancel_date_lbl, 2, 2)
        g.addWidget(self.cancel_date, 2, 3)
        self.fields.update(cancel_no=self.cancel_no, cancel_date=self.cancel_date.line)
        self.cancel_check.toggled.connect(self._refresh)
        self.cancel_no.textChanged.connect(self._refresh)
        self.cancel_date.changed.connect(self._refresh)

    def _build_notes(self):
        box, g = self._section("ملاحظات (اختياري)")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setFixedHeight(70)
        g.addWidget(self.notes_edit, 0, 0, 1, 4)
        self.notes_edit.textChanged.connect(self._refresh)

    # ==================================================================
    # تحميل وجمع البيانات
    # ==================================================================
    def _load_sectors(self, current_id):
        sectors = self.repo.sectors()
        if current_id and current_id not in {s.id for s in sectors}:
            sectors += [s for s in self.repo.sectors(include_inactive=True) if s.id == current_id]
        fill_combo(self.sector_combo, [(s.id, s.name) for s in sectors])

    def _load(self, o: WorkOrder):
        self.no_edit.set_value(o.order_no)
        set_combo_value(self.year_combo, o.order_year)
        set_combo_value(self.type_combo, o.order_type)
        self.project_edit.setText(o.project_name)
        set_combo_value(self.work_combo, o.work_type)
        set_combo_value(self.voltage_combo, o.voltage)
        set_combo_value(self.tech_combo, o.tech_class)
        self._load_sectors(o.sector_id)
        set_combo_value(self.sector_combo, o.sector_id)

        self.submit_no.set_value(o.submit_no)
        self.submit_date.set_date(o.submit_date)
        set_combo_value(self.response_combo, o.response)
        self.response_no.set_value(o.response_no)
        self.response_date.set_date(o.response_date)
        self.labor_edit.set_value(o.labor_alloc)
        self.materials_alloc_edit.set_value(o.materials_alloc)
        self.total_materials_edit.set_value(o.total_materials_cost)

        for mid, edit in self.material_edits.items():
            edit.set_value(o.materials.get(mid))

        if o.committee_head_id:
            set_combo_value(self.head_combo, o.committee_head_id)
        self.start_no.set_value(o.start_no)
        self.start_date.set_date(o.start_date)
        self.actual_start.set_date(o.actual_start_date)
        self._actual_follows = o.actual_start_date is None or o.actual_start_date == o.start_date
        self.close_no.set_value(o.close_no)
        self.close_date.set_date(o.close_date)
        self.cancel_check.setChecked(o.has_cancel)
        self.cancel_no.set_value(o.cancel_no)
        self.cancel_date.set_date(o.cancel_date)
        self.notes_edit.setPlainText(o.notes)

    def _head_selection(self) -> tuple[int | None, str]:
        """يرجع (رقم رئيس اللجنة، الاسم المكتوب). NEW_HEAD إذا كان الاسم جديداً."""
        text = clean_spaces(self.head_combo.currentText())
        if not text:
            return None, ""
        idx = self.head_combo.findText(text, Qt.MatchExactly)
        if idx >= 0:
            return self.head_combo.itemData(idx), text
        return NEW_HEAD, text

    def _collect(self) -> WorkOrder:
        o = WorkOrder(id=self.order.id)
        o.order_no = self.no_edit.value()
        o.order_year = combo_value(self.year_combo)
        o.order_type = combo_value(self.type_combo)
        o.project_name = clean_spaces(self.project_edit.text())
        o.work_type = combo_value(self.work_combo)
        if o.work_type == "network":
            o.voltage = combo_value(self.voltage_combo)
            if o.voltage in VOLTAGES_WITH_TECH:
                o.tech_class = combo_value(self.tech_combo)
            if o.voltage in VOLTAGES_WITH_SECTOR:
                o.sector_id = combo_value(self.sector_combo)

        o.submit_no = self.submit_no.text_value()
        o.submit_date = self.submit_date.date()
        o.response = combo_value(self.response_combo) or "pending"
        if o.response != "pending":
            o.response_no = self.response_no.text_value()
            o.response_date = self.response_date.date()
        o.labor_alloc = self.labor_edit.value()
        o.materials_alloc = self.materials_alloc_edit.value()
        o.total_materials_cost = self.total_materials_edit.value()

        if o.work_type == "network":  # المواد الحاكمة لأوامر عمل الشبكة الكهربائية فقط
            o.materials = {mid: e.value() for mid, e in self.material_edits.items() if e.value()}

        head_id, head_name = self._head_selection()
        o.committee_head_id = head_id
        o.committee_head_name = head_name or None
        o.start_no = self.start_no.text_value()
        o.start_date = self.start_date.date()
        o.actual_start_date = self.actual_start.date()
        o.close_no = self.close_no.text_value()
        o.close_date = self.close_date.date()
        if self.cancel_check.isChecked():
            o.cancel_no = self.cancel_no.text_value()
            o.cancel_date = self.cancel_date.date()
        o.notes = self.notes_edit.toPlainText().strip()
        # للحساب الصحيح للحالة أثناء الإدخال حتى لو كان التاريخ ناقصاً
        self._partial_flags = {
            "submit": bool(o.submit_no) or not self.submit_date.is_empty(),
            "start": bool(o.start_no) or not self.start_date.is_empty() or not self.actual_start.is_empty(),
            "close": bool(o.close_no) or not self.close_date.is_empty(),
            "cancel": self.cancel_check.isChecked(),
        }
        return o

    def _snapshot(self):
        o = self._collect()
        data = asdict(o)
        data["_head_text"] = clean_spaces(self.head_combo.currentText())
        data["_dates"] = [d.line.text() for d in (self.submit_date, self.response_date, self.start_date,
                                                    self.actual_start,
                                                    self.close_date, self.cancel_date)]
        return data

    # ==================================================================
    # التحديث الفوري للشاشة حسب البيانات المدخلة
    # ==================================================================
    def _refresh(self, *_):
        if self._loading:
            return
        o = self._collect()
        flags = self._partial_flags

        if self.is_new:
            self.title_label.setText("إدخال أمر عمل جديد")
        else:
            self.title_label.setText(f"أمر العمل {self.order.ref}")

        # ---- إظهار الحقول حسب نوع العمل والجهد
        network = o.work_type == "network"
        voltage = combo_value(self.voltage_combo)
        for w in (self.voltage_lbl, self.voltage_combo):
            w.setVisible(network)
        show_tech = network and voltage in VOLTAGES_WITH_TECH
        show_sector = network and voltage in VOLTAGES_WITH_SECTOR
        for w in (self.tech_lbl, self.tech_combo):
            w.setVisible(show_tech)
        for w in (self.sector_lbl, self.sector_combo):
            w.setVisible(show_sector)
        self.materials_box.setVisible(network)
        number = 1
        for box, title in self._numbered_sections:
            if not box.isHidden():
                box.setTitle(f"{number}. {title}")
                number += 1

        # ---- فحص رقم أمر العمل فوراً
        self._update_number_check(o)

        # ---- قسم الرد
        response = combo_value(self.response_combo) or "pending"
        submit_complete = bool(o.submit_no and o.submit_date)
        response_has_data = (response != "pending" or bool(self.response_no.text())
                             or not self.response_date.is_empty())
        self._set_section(self.response_box, self.response_hint, submit_complete or response_has_data,
                          "يُفعَّل هذا القسم بعد إدخال رقم وتاريخ كتاب الرفع.")
        show_book = response != "pending"
        for w in (self.response_no_lbl, self.response_no, self.response_date_lbl, self.response_date):
            w.setVisible(show_book)
        word = "الموافقة" if response == "approved" else "الرفض"
        self.response_no_lbl.setText(f"رقم كتاب {word}")
        self.response_date_lbl.setText(f"تاريخ كتاب {word}")
        self.approval_costs_hint.setVisible(response == "approved")
        estimate = o.estimated_total
        self.estimated_label.setText(f"{estimate:,} دينار" if estimate is not None
                                     else "— (أدخل الكلفة الكلية للمواد)")

        # ---- قسم التنفيذ
        exec_has_data = bool(clean_spaces(self.head_combo.currentText())) or flags["start"]
        self._set_section(self.exec_box, self.exec_hint, response == "approved" or exec_has_data,
                          "يُفعَّل هذا القسم بعد تسجيل موافقة الشركة العامة.")

        # ---- قسم الغلق
        start_complete = bool(o.start_no and o.start_date)
        self._set_section(self.close_box, self.close_hint, start_complete or flags["close"],
                          "يُفعَّل هذا القسم بعد إدخال رقم وتاريخ الأمر الإداري بالمباشرة.")

        # ---- قسم الإلغاء
        can_cancel = response != "rejected" and not flags["close"]
        reason = ("أمر العمل المرفوض لا يحتاج إلى إلغاء." if response == "rejected"
                  else "لا يمكن إلغاء أمر عمل مغلق.")
        self._set_section(self.cancel_box, self.cancel_hint, can_cancel or flags["cancel"], reason)
        cancel_on = self.cancel_check.isChecked()
        for w in (self.cancel_no_lbl, self.cancel_no, self.cancel_date_lbl, self.cancel_date):
            w.setVisible(cancel_on)

        # ---- الحالة والتدوير
        status_order = WorkOrder(**{**asdict(o)})
        if flags["submit"] and not status_order.has_submit:
            status_order.submit_no = "?"
        if flags["start"] and not status_order.has_start:
            status_order.start_no = "?"
        if flags["close"] and not status_order.has_close:
            status_order.close_no = "?"
        if flags["cancel"] and not status_order.has_cancel:
            status_order.cancel_no = "?"
        status = compute_status(status_order, self.today)
        fg, bg = STATUS_COLORS[status]
        self.status_chip.set_status(STATUS_LABELS[status], fg, bg)
        year = rolled_to_year(o, self.today)
        self.rolled_label.setText(f"مدوّر إلى سنة {year}" if year else "")

        # ---- تنبيه (غير مانع): المباشرة قبل تاريخ الموافقة
        early = validation_warnings(o)
        self.early_warning.setVisible(bool(early))
        if early:
            self.early_warning.setText(
                "⚠ تنبيه: " + " ".join(w.message for w in early)
                + " تأكد من صحة التاريخ. يُقبل الحفظ إذا كانت المباشرة بناءً على موافقة سابقة، "
                "ويُفضّل كتابة السبب في حقل الملاحظات.")

    def _set_section(self, box: QGroupBox, hint: QLabel, enabled: bool, reason: str):
        box.setEnabled(enabled)
        hint.setVisible(not enabled)
        hint.setText(reason)

    def _update_number_check(self, o: WorkOrder):
        if o.order_no is None or o.order_year is None:
            last = self.repo.max_order_no(o.order_year) if o.order_year else None
            self.no_check.setObjectName("hint")
            self.no_check.setText(f"آخر رقم مستخدم لسنة {o.order_year}: {last}" if last else "")
        else:
            others = [x for x in self.repo.orders_with_number(o.order_no) if x.id != o.id]
            problems = number_conflicts(o, others, self.today)
            if problems:
                self.no_check.setObjectName("errorText")
                self.no_check.setText("✖ " + problems[0])
            else:
                self.no_check.setObjectName("okText")
                self.no_check.setText(f"✔ الرقم {o.order_no} متاح لسنة {o.order_year}")
        self.no_check.style().unpolish(self.no_check)
        self.no_check.style().polish(self.no_check)

    # ==================================================================
    # الحفظ
    # ==================================================================
    def _date_issues(self) -> list[Issue]:
        issues = []
        checks = [
            (self.submit_date, "submit_date", "تاريخ كتاب الرفع", True),
            (self.response_date, "response_date", "تاريخ كتاب الرد", self.response_date.isVisible() or
             (combo_value(self.response_combo) or "pending") != "pending"),
            (self.start_date, "start_date", "تاريخ الأمر الإداري بالمباشرة", True),
            (self.actual_start, "actual_start_date", "تاريخ المباشرة الفعلي", True),
            (self.close_date, "close_date", "تاريخ الغلق", True),
            (self.cancel_date, "cancel_date", "تاريخ الإلغاء", self.cancel_check.isChecked()),
        ]
        for widget, field, title, relevant in checks:
            if relevant and widget.is_invalid():
                issues.append(Issue(field, f"{title} غير صحيح أو ناقص. اكتبه كاملاً (يوم/شهر/سنة) أو اختره من التقويم."))
        return issues

    def _show_issues(self, issues: list[Issue]):
        for w in self.fields.values():
            set_error(w, False)
        first = None
        for issue in issues:
            w = self.fields.get(issue.field)
            if w is not None:
                set_error(w, True)
                first = first or w
        if first is not None:
            self.scroll.ensureWidgetVisible(first, 50, 80)
            first.setFocus()
        unique = list(dict.fromkeys(i.message for i in issues))
        text = "\n".join(f"• {m}" for m in unique[:12])
        if len(unique) > 12:
            text += f"\n... و{len(unique) - 12} ملاحظات أخرى"
        messages.warning(self, "لا يمكن الحفظ", "يرجى تصحيح الملاحظات الآتية:\n\n" + text)

    def _resolve_head(self, o: WorkOrder) -> bool:
        """تحويل اسم رئيس لجنة جديد إلى عنصر في القائمة (مع منع التكرار)."""
        if o.committee_head_id != NEW_HEAD:
            return True
        name = o.committee_head_name or ""
        similar = self.repo.find_similar("heads", name)
        if similar:
            existing = similar[0]
            answer = messages.question(
                self, "اسم مشابه",
                f"يوجد في القائمة اسم مشابه:\n«{existing.name}»\n\nهل تقصد هذا الاسم؟\n"
                "(نعم: استخدام الاسم الموجود — لا: الرجوع لتعديل الاسم)",
            )
            if answer == QMessageBox.Yes:
                o.committee_head_id = existing.id
                if not existing.active:
                    self.repo.set_lookup_active("heads", existing.id, True)
                return True
            self.head_combo.setFocus()
            return False
        answer = messages.question(
            self, "اسم جديد",
            f"الاسم «{name}» غير موجود في قائمة رؤساء اللجان.\n\nهل تريد إضافته إلى القائمة؟ (تأكد من كتابته بشكل صحيح)",
        )
        if answer != QMessageBox.Yes:
            self.head_combo.setFocus()
            return False
        o.committee_head_id = self.repo.add_lookup("heads", name)
        return True

    def _save(self, and_new: bool):
        o = self._collect()
        issues = self._date_issues()
        others = self.repo.orders_with_number(o.order_no) if o.order_no else []
        issues += validate(o, others, self.today)  # الاسم الجديد لرئيس اللجنة يُعامل كاسم محدد
        if issues:
            self._show_issues(issues)
            return
        for w in self.fields.values():
            set_error(w, False)
        if not self._confirm_warnings(o):
            return
        if o.has_cancel and not self.order.has_cancel:
            answer = messages.question(
                self, "تأكيد الإلغاء", f"هل أنت متأكد من تسجيل إلغاء أمر العمل {o.ref}؟")
            if answer != QMessageBox.Yes:
                return
        if not self._resolve_head(o):
            return
        self.saved_id = self.repo.save_order(o)
        self._initial = self._snapshot()
        self.done(SAVE_AND_NEW if and_new else QDialog.Accepted)

    def _confirm_warnings(self, o: WorkOrder) -> bool:
        """التنبيهات لا تمنع الحفظ، لكن تُعرض على المستخدم ليؤكد أن البيانات صحيحة."""
        found = validation_warnings(o)
        if not found:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("تنبيه: المباشرة قبل الموافقة")
        box.setText("\n".join(f"• {w.message}" for w in found))
        box.setInformativeText(
            "هذه حالة استثنائية (مثل المباشرة بناءً على موافقة سابقة).\n"
            "هل التواريخ صحيحة وتريد الحفظ؟\n\n"
            "سيظهر أمر العمل بعلامة ⚠ في القائمة للمراجعة، ويُفضّل كتابة السبب في حقل الملاحظات.")
        save = box.addButton("نعم، التواريخ صحيحة – احفظ", QMessageBox.AcceptRole)
        back = box.addButton("لا، أرجع لتصحيح التاريخ", QMessageBox.RejectRole)
        box.setDefaultButton(back)
        box.exec()
        if box.clickedButton() is save:
            return True
        first = None
        for w in found:
            widget = self.fields.get(w.field)
            if widget is not None:
                set_error(widget, True)
                first = first or widget
        if first is not None:
            self.scroll.ensureWidgetVisible(first, 50, 80)
            first.setFocus()
        return False

    # ==================================================================
    def is_dirty(self) -> bool:
        return self._snapshot() != self._initial

    def reject(self):
        if self.is_dirty():
            answer = messages.question(
                self, "خروج بدون حفظ", "توجد تغييرات لم تُحفظ.\nهل تريد الخروج بدون حفظ؟",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        super().reject()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focus = self.focusWidget()
            if not isinstance(focus, (QPlainTextEdit, QPushButton)):
                self.focusNextChild()
                return
        super().keyPressEvent(event)


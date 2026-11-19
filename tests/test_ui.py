"""اختبارات تشغيل الواجهات (بدون شاشة) للتأكد من عمل الإدخال والحفظ والقواعد."""

from datetime import date

import pytest
from conftest import TODAY, make_order

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from workorders.paths import AppPaths  # noqa: E402
from workorders.ui import messages  # noqa: E402
from workorders.ui import order_dialog as od  # noqa: E402
from workorders.ui.style import apply_style  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    apply_style(a)
    return a


@pytest.fixture
def boxes(monkeypatch):
    """استبدال نوافذ الرسائل بإجابات تلقائية وتسجيل ما يظهر."""
    shown = []

    def question(parent, title, text, *args, **kw):
        shown.append(("question", title, text))
        return QMessageBox.Yes

    def warning(parent, title, text, *args, **kw):
        shown.append(("warning", title, text))
        return QMessageBox.Ok

    monkeypatch.setattr(messages, "question", question)
    monkeypatch.setattr(messages, "warning", warning)
    monkeypatch.setattr(messages, "information", warning)
    monkeypatch.setattr(messages, "critical", warning)
    return shown


def set_combo(combo, data):
    combo.setCurrentIndex(combo.findData(data))


def test_new_order_flow(app, repo, boxes):
    dlg = od.OrderDialog(repo, None, today=TODAY)
    # الحقول الشرطية مخفية في البداية
    assert dlg.voltage_combo.isHidden() and dlg.sector_combo.isHidden()
    assert not dlg.response_box.isEnabled()

    dlg.no_edit.setText("١٥")  # أرقام عربية تتحول تلقائياً
    dlg.no_edit.textEdited.emit("١٥")
    assert dlg.no_edit.value() == 15
    set_combo(dlg.type_combo, "investment")
    dlg.project_edit.setText("  استحداث   مغذي الحسينية  ")
    set_combo(dlg.work_combo, "network")
    assert not dlg.voltage_combo.isHidden()
    set_combo(dlg.voltage_combo, "11")
    assert not dlg.tech_combo.isHidden() and not dlg.sector_combo.isHidden()
    set_combo(dlg.voltage_combo, "33")
    assert not dlg.tech_combo.isHidden() and dlg.sector_combo.isHidden()
    set_combo(dlg.voltage_combo, "lv")
    assert dlg.tech_combo.isHidden() and not dlg.sector_combo.isHidden()
    set_combo(dlg.voltage_combo, "11")
    set_combo(dlg.tech_combo, "new")
    dlg.sector_combo.setCurrentIndex(5)

    dlg.submit_no.setText("1200")
    dlg.submit_date.set_date(date(2026, 3, 1))
    assert dlg.response_box.isEnabled()
    assert dlg.status_chip.text().startswith("مرفوع")
    set_combo(dlg.response_combo, "approved")
    dlg.response_no.setText("880")
    dlg.response_date.set_date(date(2026, 4, 1))
    dlg.labor_edit.edit.setText("250000000")
    dlg.labor_edit.edit.textEdited.emit("250000000")
    assert dlg.labor_edit.edit.text() == "250,000,000"
    assert dlg.exec_box.isEnabled() and not dlg.close_box.isEnabled()
    first_material = next(iter(dlg.material_edits))
    dlg.material_edits[first_material].setText("1500")

    dlg.head_combo.setEditText("م. حسن جواد")
    dlg.start_no.setText("45")
    dlg.start_date.set_date(date(2026, 5, 1))
    assert dlg.actual_start.date() == date(2026, 5, 1)  # يؤخذ تلقائياً من تاريخ الأمر الإداري
    dlg.actual_start.set_date(date(2026, 5, 4))  # المستخدم يعدّله
    dlg.start_date.set_date(date(2026, 5, 2))
    assert dlg.actual_start.date() == date(2026, 5, 4)  # لا يُستبدل بعد تعديله يدوياً
    assert dlg.close_box.isEnabled()
    assert dlg.status_chip.text().startswith("مباشر")

    dlg._save(and_new=False)
    assert dlg.result() == QDialog.Accepted, boxes
    saved = repo.get_order(dlg.saved_id)
    assert saved.project_name == "استحداث مغذي الحسينية"
    assert saved.order_no == 15 and saved.voltage == "11" and saved.tech_class == "new"
    assert saved.labor_alloc == 250_000_000
    assert saved.materials == {first_material: 1500}
    assert saved.start_date == date(2026, 5, 2) and saved.actual_start_date == date(2026, 5, 4)
    assert saved.committee_head_name == "م. حسن جواد"
    assert any(b[1] == "اسم جديد" for b in boxes)


def test_duplicate_number_blocked(app, repo, boxes):
    repo.save_order(make_order(order_no=10, order_type="operational"))
    dlg = od.OrderDialog(repo, None, today=TODAY)
    dlg.no_edit.setText("10")
    assert "مستخدم" in dlg.no_check.text()
    set_combo(dlg.type_combo, "trust")
    dlg.project_edit.setText("مشروع")
    set_combo(dlg.work_combo, "civil")
    dlg._save(and_new=False)
    assert dlg.saved_id is None
    assert boxes and boxes[-1][0] == "warning" and "10" in boxes[-1][2]


def test_invalid_date_reported(app, repo, boxes):
    dlg = od.OrderDialog(repo, None, today=TODAY)
    dlg.no_edit.setText("3")
    set_combo(dlg.type_combo, "trust")
    dlg.project_edit.setText("مشروع")
    set_combo(dlg.work_combo, "civil")
    dlg.submit_no.setText("5")
    dlg.submit_date.line.setText("31/02/2026")
    assert dlg.submit_date.is_invalid()
    dlg._save(and_new=False)
    assert dlg.saved_id is None
    assert "غير صحيح" in boxes[-1][2]


def test_edit_existing_and_similar_head(app, repo, boxes):
    head = repo.add_lookup("heads", "علي حسين")
    oid = repo.save_order(make_order(order_no=4, submit_no="1", submit_date=date(2026, 1, 1),
                                     response="approved", response_no="2", response_date=date(2026, 2, 1)))
    dlg = od.OrderDialog(repo, repo.get_order(oid), today=TODAY)
    assert not dlg.is_dirty()
    dlg.head_combo.setEditText("على حسين")  # كتابة بشكل مختلف
    assert dlg.is_dirty()
    dlg._save(and_new=False)
    assert repo.get_order(oid).committee_head_id == head  # استُخدم الاسم الموجود
    assert len(repo.committee_heads()) == 1


def test_cancel_section(app, repo, boxes):
    oid = repo.save_order(make_order(order_no=8, submit_no="1", submit_date=date(2026, 1, 1)))
    dlg = od.OrderDialog(repo, repo.get_order(oid), today=TODAY)
    assert dlg.cancel_no.isHidden()
    dlg.cancel_check.setChecked(True)
    assert not dlg.cancel_no.isHidden()
    dlg.cancel_no.setText("99")
    dlg.cancel_date.set_date(date(2026, 2, 1))
    assert dlg.status_chip.text() == "ملغى"
    dlg._save(and_new=False)
    assert repo.get_order(oid).status == "cancelled"


def test_main_window_pages(app, repo, tmp_path, boxes):
    from workorders.ui.main_window import MainWindow

    repo.save_order(make_order(order_no=1))
    win = MainWindow(repo, AppPaths(tmp_path), "DejaVu Sans", today=TODAY)
    for i in range(4):
        win.show_page(i)
    assert win.dashboard.cards["total"].number.text() == "1"
    win.show_page(1)
    assert win.orders.table.rowCount() == 1
    win.orders.filters.search.setText("999")
    win.orders.apply()
    assert win.orders.table.rowCount() == 0
    win.show_page(2)
    for row in range(win.reports.report_list.count()):
        win.reports.report_list.setCurrentRow(row)
        win.reports.generate()
        assert win.reports.report is not None
    win.repo.changed = True
    win.close()
    assert list((tmp_path / "backups").glob("auto_*.db"))


def test_auto_cancel_shown_and_start_without_head(app, repo, boxes):
    oid = repo.save_order(make_order(order_no=12, submit_no="1", submit_date=date(2026, 1, 1),
                                     response="approved", response_no="2", response_date=date(2026, 2, 1)))
    dlg = od.OrderDialog(repo, repo.get_order(oid), today=date(2027, 1, 5))
    assert dlg.status_chip.text().startswith("ملغى تلقائياً")
    dlg.close()

    dlg = od.OrderDialog(repo, repo.get_order(oid), today=TODAY)
    dlg.start_no.setText("70")
    dlg.start_date.set_date(date(2026, 3, 1))
    dlg._save(and_new=False)
    assert dlg.saved_id == oid, boxes
    assert repo.get_order(oid).committee_head_id is None


def test_materials_hidden_for_non_network(app, repo, boxes):
    dlg = od.OrderDialog(repo, None, today=TODAY)
    dlg.no_edit.setText("30")
    set_combo(dlg.type_combo, "investment")
    dlg.project_edit.setText("نصب معدات")
    set_combo(dlg.work_combo, "network")
    assert not dlg.materials_box.isHidden()
    first = next(iter(dlg.material_edits))
    dlg.material_edits[first].setText("40")
    set_combo(dlg.work_combo, "substation")
    assert dlg.materials_box.isHidden()
    dlg._save(and_new=False)
    assert repo.get_order(dlg.saved_id).materials == {}


def test_start_before_approval_warns_but_saves(app, repo, monkeypatch, boxes):
    oid = repo.save_order(make_order(order_no=40, submit_no="1", submit_date=date(2026, 1, 1),
                                     response="approved", response_no="2", response_date=date(2026, 3, 1)))
    dlg = od.OrderDialog(repo, repo.get_order(oid), today=TODAY)
    dlg.start_no.setText("5")
    dlg.start_date.set_date(date(2026, 2, 10))  # قبل الموافقة
    assert not dlg.early_warning.isHidden()  # تنبيه فوري في الشاشة

    asked = []

    def fake_exec(box):
        asked.append(box.text())
        box.clickedButton = lambda: answer[0]
        for b in box.buttons():
            if box.buttonRole(b) == (QMessageBox.RejectRole if answer[1] == "back" else QMessageBox.AcceptRole):
                answer[0] = b
        return 0

    answer = [None, "back"]
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    dlg._save(and_new=False)
    assert dlg.saved_id is None and asked  # اختار الرجوع للتصحيح: لم يُحفظ

    answer[1] = "save"
    dlg._save(and_new=False)
    saved = repo.get_order(oid)
    assert dlg.saved_id == oid and saved.start_date == date(2026, 2, 10)
    assert saved.started_before_approval

    dlg.start_date.set_date(date(2026, 3, 5))
    assert dlg.early_warning.isHidden()


def test_arabic_message_buttons(app, monkeypatch):
    captured = []

    def fake_exec(box):
        captured.append(sorted(b.text() for b in box.buttons()))
        return int(QMessageBox.Yes)

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert messages.question(None, "ع", "نص") == QMessageBox.Yes
    messages.information(None, "ع", "نص")
    assert captured == [sorted(["نعم", "لا"]), ["حسناً"]]


def test_orders_page_check_calculate_and_groups(app, repo, tmp_path, monkeypatch, boxes):
    from workorders.ui import report_actions
    from workorders.ui.orders_page import COL_CHECK, OrdersPage

    ids = [repo.save_order(make_order(order_no=n, labor_alloc=None)) for n in (1, 2, 3)]
    page = OrdersPage(repo, TODAY, tmp_path, "DejaVu Sans")
    page.refresh()
    assert not page.calc_btn.isEnabled()
    # تأشير أمرين من الجدول
    for r in range(page.table.rowCount()):
        item = page.table.item(r, COL_CHECK)
        if item.data(Qt.UserRole) in ids[:2]:
            item.setCheckState(Qt.Checked)
    assert page.checked == set(ids[:2]) and page.calc_btn.isEnabled()

    shown = []
    monkeypatch.setattr(report_actions.ReportDialog, "exec", lambda self: shown.append(self.report) or 0)
    page._calculate()
    assert shown and len(shown[0].tables[0].rows) == 2

    # حفظ كمجموعة جديدة
    monkeypatch.setattr(messages, "ask_text", lambda *a, **k: "خطة 2027")
    page._save_group()
    groups = repo.groups()
    assert [(g.name, g.count) for g in groups] == [("خطة 2027", 2)]
    assert page.current_group_id() == groups[0].id

    # تفريغ التأشير ثم فتح المجموعة من القائمة
    page._uncheck_all()
    assert page.checked == set()
    page.group_combo.setCurrentIndex(0)
    page.group_combo.setCurrentIndex(1)
    assert page.checked == set(ids[:2]) and page.show_checked.isChecked()
    assert page.table.rowCount() == 2

    # تحديث المجموعة بإضافة الأمر الثالث
    page.checked.add(ids[2])
    monkeypatch.setattr(messages, "choose", lambda *a, **k: 0)
    page._save_group()
    assert repo.groups()[0].count == 3

    # حذف المجموعة
    page._delete_group()
    assert repo.groups() == [] and repo.order_count() == 3


def test_costs_section_and_estimate(app, repo, boxes):
    dlg = od.OrderDialog(repo, None, today=TODAY)
    dlg.no_edit.setText("50")
    set_combo(dlg.type_combo, "operational")
    dlg.project_edit.setText("مشروع كلف")
    set_combo(dlg.work_combo, "civil")
    dlg.labor_edit.edit.setText("1000000")
    dlg.materials_alloc_edit.edit.setText("700000")
    dlg.total_materials_edit.edit.setText("600000")  # أقل من غير المتوفرة: يُمنع الحفظ
    assert dlg.estimated_label.text() == "1,600,000 دينار"
    dlg._save(and_new=False)
    assert dlg.saved_id is None and "الكلفة الكلية للمواد" in boxes[-1][2]
    dlg.total_materials_edit.edit.setText("900000")
    assert dlg.estimated_label.text() == "1,900,000 دينار"
    dlg._save(and_new=False)
    saved = repo.get_order(dlg.saved_id)
    assert (saved.labor_alloc, saved.materials_alloc, saved.total_materials_cost) == (1_000_000, 700_000, 900_000)
    assert saved.estimated_total == 1_900_000

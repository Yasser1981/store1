"""اختبارات تشغيل الواجهات (بدون شاشة) للتأكد من عمل الإدخال والحفظ والقواعد."""

from datetime import date

import pytest
from conftest import TODAY, make_order

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from workorders.paths import AppPaths  # noqa: E402
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

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(warning))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(warning))
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

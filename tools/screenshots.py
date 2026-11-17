"""إنشاء صور توضيحية لشاشات البرنامج ببيانات تجريبية (للمراجعة والتوثيق).

الاستخدام:  python tools/screenshots.py <مجلد_الإخراج>
"""

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from workorders.db import open_database  # noqa: E402
from workorders.models import WorkOrder, set_reference_date  # noqa: E402
from workorders.paths import AppPaths  # noqa: E402
from workorders.reports import OrderFilter, ReportContext, build_report  # noqa: E402
from workorders.repository import Repository  # noqa: E402
from workorders.ui.style import apply_style  # noqa: E402

TODAY = date(2026, 11, 17)
set_reference_date(TODAY)


def seed(repo: Repository):
    s = {x.name: x.id for x in repo.sectors()}
    m = [x.id for x in repo.materials()]
    h1 = repo.add_lookup("heads", "م. أحمد كاظم")
    h2 = repo.add_lookup("heads", "م. زينب عباس")
    rows = [
        dict(order_no=1, order_type="investment", project_name="استحداث مغذي 33 ك.ف محطة الحر – محطة الإبراهيمية",
             work_type="network", voltage="33", tech_class="new", submit_no="1101", submit_date=date(2026, 1, 12),
             response="approved", response_no="2240", response_date=date(2026, 2, 3), labor_alloc=450_000_000,
             materials_alloc=320_000_000, committee_head_id=h1, start_no="310", start_date=date(2026, 3, 1),
             materials={m[0]: 6200, m[5]: 48}),
        dict(order_no=2, order_type="operational", project_name="تأهيل مغذي 11 ك.ف المركز/5",
             work_type="network", voltage="11", tech_class="rehab", sector_id=s["المركز"], submit_no="1150",
             submit_date=date(2026, 2, 2), response="approved", response_no="2301", response_date=date(2026, 3, 8),
             labor_alloc=85_000_000, materials_alloc=0, committee_head_id=h2, start_no="402",
             start_date=date(2026, 4, 1), close_no="977", close_date=date(2026, 9, 20),
             materials={m[2]: 900, m[6]: 14, m[9]: 2}),
        dict(order_no=3, order_type="trust", project_name="شبكة ضغط واطئ حي الأسرة – الحسينية",
             work_type="network", voltage="lv", sector_id=s["الحسينية"], submit_no="1203", submit_date=date(2026, 3, 15),
             materials={m[13]: 2400, m[11]: 30}),
        dict(order_no=4, order_type="investment", project_name="نصب معدات محطة ثانوية 33/11 ك.ف عين التمر",
             work_type="substation", submit_no="1250", submit_date=date(2026, 4, 2), response="approved",
             response_no="2410", response_date=date(2026, 5, 6), labor_alloc=120_000_000, materials_alloc=60_000_000),
        dict(order_no=5, order_type="operational", project_name="أعمال مدنية لغرفة سيطرة قطاع الهندية",
             work_type="civil", submit_no="1302", submit_date=date(2026, 5, 10), response="rejected",
             response_no="2501", response_date=date(2026, 6, 1)),
        dict(order_no=6, order_type="trust", project_name="تأهيل شبكة واطئ قطاع السلام",
             work_type="network", voltage="lv", sector_id=s["السلام"], submit_no="1401",
             submit_date=date(2026, 8, 20)),
        dict(order_no=7, order_type="investment", project_name="استحداث مغذي 11 ك.ف الجدول الغربي/3",
             work_type="network", voltage="11", tech_class="new", sector_id=s["الجدول الغربي"]),
        dict(order_no=8, order_type="operational", project_name="تأهيل مغذي 11 ك.ف الشمالي/2",
             work_type="network", voltage="11", tech_class="rehab", sector_id=s["الشمالي"], submit_no="1180",
             submit_date=date(2026, 2, 20), cancel_no="2890", cancel_date=date(2026, 7, 1)),
    ]
    for r in rows:
        repo.save_order(WorkOrder(order_year=2026, **r))


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    family = apply_style(app)
    tmp = Path(tempfile.mkdtemp())
    paths = AppPaths(tmp)
    paths.ensure_writable()
    conn = open_database(paths.db_path)
    repo = Repository(conn)
    seed(repo)

    from workorders.ui.main_window import MainWindow
    from workorders.ui.order_dialog import OrderDialog
    from workorders.ui.printing import save_pdf

    win = MainWindow(repo, paths, family, today=TODAY)
    win.resize(1440, 900)
    win.show()
    for i, name in enumerate(["1_dashboard", "2_orders", "4_reports", "5_settings"]):
        win.show_page(i)
        if i == 3:
            win.settings.tabs.setCurrentIndex(2)
        app.processEvents()
        win.grab().save(str(out / f"{name}.png"))

    order = repo.get_order(1)
    dlg = OrderDialog(repo, order, win, TODAY)
    dlg.resize(1100, 1500)
    dlg.show()
    app.processEvents()
    dlg.grab().save(str(out / "3_order_dialog.png"))
    dlg.close()

    new = OrderDialog(repo, None, win, TODAY)
    new.resize(1100, 760)
    new.show()
    app.processEvents()
    new.grab().save(str(out / "3b_new_order.png"))
    new.submit_date.open_calendar()
    app.processEvents()
    new.submit_date._popup.grab().save(str(out / "3c_calendar.png"))
    new.submit_date._popup.close()
    new.close()

    ctx = ReportContext(repo.sectors(True), repo.committee_heads(True), repo.materials(True), TODAY)
    for kind in ("progress", "detail", "materials"):
        rep = build_report(kind, repo.all_orders(), ctx, OrderFilter(), "order_type")
        save_pdf(rep, out / f"report_{kind}.pdf", family)
    win.repo.changed = False
    win.close()
    conn.close()
    print("saved to", out)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots"))

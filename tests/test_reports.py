"""اختبار التقارير والفلاتر والتصدير."""

from datetime import date

from conftest import TODAY, make_order
from openpyxl import load_workbook

from workorders.export import report_to_html, report_to_xlsx
from workorders.reports import OrderFilter, ReportContext, apply_filter, build_report


def seed(repo):
    s = repo.sectors()
    head = repo.add_lookup("heads", "م. سعد كريم")
    orders = [
        make_order(order_no=1, order_type="investment", work_type="network", voltage="33", tech_class="new",
                   project_name="مغذي 33 الأول"),
        make_order(order_no=2, order_type="operational", work_type="network", voltage="11", tech_class="rehab",
                   sector_id=s[0].id, submit_no="10", submit_date=date(2026, 3, 1), project_name="تأهيل مغذي المركز"),
        make_order(order_no=3, order_type="trust", work_type="network", voltage="lv", sector_id=s[5].id,
                   submit_no="11", submit_date=date(2026, 3, 2), response="approved", response_no="20",
                   response_date=date(2026, 4, 1), labor_alloc=1_000_000, materials_alloc=500_000,
                   materials={1: 100, 14: 300}, project_name="شبكة واطئ الحسينية"),
        make_order(order_no=4, order_type="investment", work_type="substation",
                   submit_no="12", submit_date=date(2026, 3, 3), response="approved", response_no="21",
                   response_date=date(2026, 4, 2), labor_alloc=2_000_000, committee_head_id=head,
                   start_no="30", start_date=date(2026, 5, 1),
                   materials={1: 50}, project_name="محطة ثانوية"),
        make_order(order_no=5, order_type="investment", work_type="civil",
                   submit_no="13", submit_date=date(2026, 3, 4), response="rejected", response_no="22",
                   response_date=date(2026, 4, 3), project_name="أعمال مدنية مرفوضة"),
        make_order(order_no=6, order_type="operational", work_type="civil", cancel_no="40",
                   cancel_date=date(2026, 6, 1), project_name="ملغى"),
    ]
    for o in orders:
        repo.save_order(o)
    return ReportContext(repo.sectors(True), repo.committee_heads(True), repo.materials(True), TODAY)


def test_progress_report_counts(repo):
    ctx = seed(repo)
    rep = build_report("progress", repo.all_orders(), ctx, OrderFilter(), "order_type")
    total = rep.tables[0].total_row
    assert total["total"] == 6
    assert total["submitted"] == 4  # 2,3,4,5
    assert total["pending"] == 1  # 2
    assert total["approved"] == 2  # 3,4
    assert total["started"] == 1
    assert total["rejected"] == 1
    assert total["cancelled"] == 1
    assert total["draft"] == 1  # 1 (6 ملغى)
    labels = [r["group"] for r in rep.tables[0].rows]
    assert labels == ["استثماري", "تشغيلي", "تنفيذ أمانة"]


def test_status_report_sums_to_total(repo):
    ctx = seed(repo)
    rep = build_report("status", repo.all_orders(), ctx, OrderFilter(), "sector")
    for row in rep.tables[0].rows:
        assert row["total"] == sum(row[k] for k in ("draft", "submitted", "approved", "started", "closed",
                                                     "rejected", "cancelled"))


def test_money_report(repo):
    ctx = seed(repo)
    rep = build_report("money", repo.all_orders(), ctx, OrderFilter(), "order_type")
    t = rep.tables[0].total_row
    assert t["count"] == 2 and t["labor"] == 3_000_000 and t["materials"] == 500_000 and t["sum"] == 3_500_000


def test_materials_report(repo):
    ctx = seed(repo)
    rep = build_report("materials", repo.all_orders(), ctx, OrderFilter())
    summary = {r["name"]: r for r in rep.tables[0].rows}
    first = ctx.materials[0].name
    assert summary[first]["qty"] == 150 and summary[first]["orders"] == 2
    assert len(rep.tables) == 3  # الملخص + مادتان مستخدمتان


def test_overdue_report(repo):
    ctx = seed(repo)
    rep = build_report("overdue", repo.all_orders(), ctx, OrderFilter(), overdue_days=30)
    assert [r["ref"] for r in rep.tables[0].rows] == ["2/2026"]


def test_filters(repo):
    ctx = seed(repo)
    orders = repo.all_orders()
    assert len(apply_filter(orders, OrderFilter(voltage="11"), TODAY)) == 1
    assert len(apply_filter(orders, OrderFilter(sector_id=ctx.sectors[5].id), TODAY)) == 1
    assert len(apply_filter(orders, OrderFilter(status="not_void"), TODAY)) == 4
    assert len(apply_filter(orders, OrderFilter(status="open"), TODAY)) == 4
    assert [o.order_no for o in apply_filter(orders, OrderFilter(text="3"), TODAY)] == [3]
    assert [o.order_no for o in apply_filter(orders, OrderFilter(text="٣/٢٠٢٦"), TODAY)] == [3]
    assert [o.order_no for o in apply_filter(orders, OrderFilter(text="الحسينيه"), TODAY)] == [3]
    assert len(apply_filter(orders, OrderFilter(year=2027), TODAY)) == 0
    rolled_today = date(2027, 2, 1)
    assert [o.order_no for o in apply_filter(orders, OrderFilter(rolled_only=True), rolled_today)] == [4]


def test_detail_and_exports(repo, tmp_path):
    ctx = seed(repo)
    rep = build_report("detail", repo.all_orders(), ctx, OrderFilter())
    assert len(rep.tables[0].rows) == 6
    assert rep.tables[0].total_row["labor_alloc"] == 3_000_000
    html = report_to_html(rep)
    assert "قائمة تفصيلية بأوامر العمل" in html and "شبكة واطئ الحسينية" in html
    path = report_to_xlsx(rep, tmp_path / "r.xlsx")
    wb = load_workbook(path)
    ws = wb.active
    assert ws.sheet_view.rightToLeft
    values = [c.value for row in ws.iter_rows() for c in row]
    assert "شبكة واطئ الحسينية" in values
    for kind in ("progress", "status", "money", "materials", "overdue"):
        r = build_report(kind, repo.all_orders(), ctx, OrderFilter(order_type="investment"))
        report_to_xlsx(r, tmp_path / f"{kind}.xlsx")
        assert "نوع الأمر: استثماري" in report_to_html(r)


def test_auto_cancelled_in_reports(repo):
    ctx = seed(repo)
    ctx.today = date(2027, 1, 10)
    rep = build_report("progress", repo.all_orders(), ctx, OrderFilter())
    total = rep.tables[0].total_row
    assert total["auto_cancelled"] == 3  # 1 معدّ، 2 مرفوع، 3 موافق عليه ولم يُباشر به
    assert total["pending"] == 0 and total["draft"] == 0
    assert total["rolled"] == 1  # 4 مباشر به ولم يُغلق
    rep = build_report("status", repo.all_orders(), ctx, OrderFilter())
    assert rep.tables[0].total_row["auto_cancelled"] == 3
    open_now = apply_filter(repo.all_orders(), OrderFilter(status="open"), ctx.today)
    assert [o.order_no for o in open_now] == [4]
    not_void = apply_filter(repo.all_orders(), OrderFilter(status="not_void"), ctx.today)
    assert sorted(o.order_no for o in not_void) == [4]

"""اختبار قاعدة البيانات والقوائم والنسخ الاحتياطي."""

import sqlite3
from datetime import date

import pytest
from conftest import make_order

from workorders import backup
from workorders.constants import DEFAULT_MATERIALS, DEFAULT_SECTORS
from workorders.db import SCHEMA_VERSION, DatabaseTooNewError, NotOurDatabaseError, get_meta, open_database
from workorders.repository import LookupError_, Repository


def test_new_database_seeded(repo):
    assert [s.name for s in repo.sectors()] == DEFAULT_SECTORS
    assert [(m.name, m.unit) for m in repo.materials()] == DEFAULT_MATERIALS
    assert repo.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert get_meta(repo.conn, "app_id") == "karbala-workorders"


def test_reopen_keeps_data(tmp_path):
    path = tmp_path / "data" / "workorders.db"
    conn = open_database(path)
    Repository(conn).save_order(make_order(order_no=7))
    conn.close()
    conn = open_database(path)
    orders = Repository(conn).all_orders()
    assert [o.order_no for o in orders] == [7]
    assert len(Repository(conn).sectors()) == len(DEFAULT_SECTORS)  # لا تكرار للقوائم
    conn.close()


def test_database_too_new(tmp_path):
    path = tmp_path / "w.db"
    conn = open_database(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(DatabaseTooNewError):
        open_database(path)


def test_foreign_file_rejected(tmp_path):
    path = tmp_path / "other.db"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE x(a)")
    c.close()
    with pytest.raises(NotOurDatabaseError):
        open_database(path)
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database at all" * 100)
    with pytest.raises(NotOurDatabaseError):
        open_database(junk)


def test_save_load_roundtrip(repo):
    sector = repo.sectors()[2]
    head_id = repo.add_lookup("heads", "م. أحمد علي")
    o = make_order(order_no=10, work_type="network", voltage="11", tech_class="rehab", sector_id=sector.id,
                   submit_no="1234", submit_date=date(2026, 2, 1), response="approved", response_no="555",
                   response_date=date(2026, 3, 1), labor_alloc=120_000_000, materials_alloc=30_000_000,
                   committee_head_id=head_id, start_no="77", start_date=date(2026, 4, 1),
                   actual_start_date=date(2026, 3, 28),
                   materials={1: 1500, 7: 20}, notes="ملاحظة")
    oid = repo.save_order(o)
    got = repo.get_order(oid)
    assert got.sector_name == sector.name
    assert got.committee_head_name == "م. أحمد علي"
    assert got.materials == {1: 1500, 7: 20}
    assert got.labor_alloc == 120_000_000
    assert got.start_date == date(2026, 4, 1)
    assert got.actual_start_date == date(2026, 3, 28)
    got.materials = {2: 10}
    got.close_no, got.close_date = "88", date(2026, 9, 1)
    repo.save_order(got)
    again = repo.get_order(oid)
    assert again.materials == {2: 10}
    assert again.close_no == "88"
    repo.delete_order(oid)
    assert repo.get_order(oid) is None
    assert repo.conn.execute("SELECT count(*) FROM work_order_materials").fetchone()[0] == 0


def test_db_level_unique_number_year(repo):
    repo.save_order(make_order(order_no=3))
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_order(make_order(order_no=3, order_type="trust"))


def test_lookup_duplicates_normalized(repo):
    repo.add_lookup("heads", "علي حسين")
    with pytest.raises(LookupError_):
        repo.add_lookup("heads", "على  حسين")
    assert repo.find_similar("heads", "عَلي حسين")
    repo.add_lookup("heads", "فاطمة محمد")
    with pytest.raises(LookupError_):
        repo.add_lookup("heads", "فاطمه محمد")


def test_lookup_delete_used_blocked(repo):
    sector = repo.sectors()[0]
    repo.save_order(make_order(work_type="network", voltage="lv", sector_id=sector.id))
    with pytest.raises(LookupError_):
        repo.delete_lookup("sectors", sector.id)
    repo.set_lookup_active("sectors", sector.id, False)
    assert sector.id not in [s.id for s in repo.sectors()]
    assert sector.id in [s.id for s in repo.sectors(include_inactive=True)]
    new_id = repo.add_lookup("sectors", "قطاع تجريبي")
    repo.delete_lookup("sectors", new_id)


def test_lookup_rename_and_move(repo):
    first, second = repo.sectors()[:2]
    repo.move_lookup("sectors", second.id, -1)
    assert [s.id for s in repo.sectors()[:2]] == [second.id, first.id]
    repo.rename_lookup("sectors", first.id, "المركز الجديد")
    assert repo.sectors(include_inactive=True)[1].name == "المركز الجديد"
    mid = repo.add_lookup("materials", "مادة جديدة", "عدد")
    assert repo.materials()[-1].id == mid and repo.materials()[-1].unit == "عدد"


def test_backup_restore_and_prune(tmp_path, repo):
    repo.save_order(make_order(order_no=1))
    bdir = tmp_path / "backups"
    path = backup.make_backup(repo.conn, bdir, "manual")
    assert backup.inspect_backup(path) == SCHEMA_VERSION
    repo.save_order(make_order(order_no=2))
    assert repo.order_count() == 2
    backup.restore_into(repo.conn, path)
    assert repo.order_count() == 1
    for i in range(5):
        (bdir / f"auto_2026-01-0{i + 1}_10-00-00.db").write_bytes(b"x")
    backup.auto_backup(repo.conn, bdir, keep=3)
    assert len(list(bdir.glob("auto_*.db"))) == 3


def test_inspect_rejects_foreign_file(tmp_path):
    p = tmp_path / "x.db"
    p.write_bytes(b"garbage" * 50)
    with pytest.raises(NotOurDatabaseError):
        backup.inspect_backup(p)


def test_upgrade_from_schema_1_keeps_data(tmp_path):
    """محاكاة قاعدة بيانات من الإصدار 1.0.x وتحديثها تلقائياً دون فقدان البيانات."""
    from workorders import db as dbmod

    path = tmp_path / "old.db"
    conn = dbmod.connect(path)
    with dbmod.transaction(conn):
        dbmod._migration_1(conn)
        conn.execute("PRAGMA user_version = 1")
        conn.execute(
            "INSERT INTO work_orders(order_no, order_year, order_type, project_name, work_type, submit_no, "
            "submit_date, response, response_no, response_date, start_no, start_date, created_at, updated_at) "
            "VALUES (5, 2026, 'trust', 'مشروع قديم', 'civil', '1', '2026-01-02', 'approved', '2', '2026-02-01', "
            "'3', '2026-03-01', 'x', 'x')")
    conn.close()
    calls = []
    conn = open_database(path, backup_before_upgrade=calls.append)
    assert calls == [1]  # أُخذت نسخة احتياطية قبل التحديث
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    o = Repository(conn).all_orders()[0]
    assert o.project_name == "مشروع قديم"
    assert o.actual_start_date == date(2026, 3, 1)  # أخذ قيمته من تاريخ الأمر الإداري
    conn.close()

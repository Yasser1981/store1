"""قراءة وكتابة البيانات في قاعدة البيانات."""

from __future__ import annotations

import sqlite3

from .db import now_text, transaction
from .models import LookupItem, WorkOrder
from .textutil import clean_spaces, from_iso, normalize_for_compare, to_iso


class LookupError_(Exception):
    """خطأ في إدارة القوائم (اسم مكرر، أو حذف عنصر مستخدم...)."""


_ORDER_COLUMNS = [
    "order_no", "order_year", "order_type", "project_name", "work_type", "voltage",
    "tech_class", "sector_id", "submit_no", "submit_date", "response", "response_no",
    "response_date", "labor_alloc", "materials_alloc", "committee_head_id", "start_no",
    "start_date", "actual_start_date", "close_no", "close_date", "cancel_no", "cancel_date", "notes",
]
_DATE_COLUMNS = {"submit_date", "response_date", "start_date", "actual_start_date", "close_date", "cancel_date"}


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        # يصبح True عند أي تعديل، لأخذ نسخة احتياطية عند الخروج
        self.changed = False

    # ==================================================================
    # القوائم: قطاعات التوزيع / رؤساء اللجان / المواد الحاكمة
    # ==================================================================
    _LOOKUPS = {
        "sectors": ("sectors", "sector_id", "work_orders"),
        "heads": ("committee_heads", "committee_head_id", "work_orders"),
        "materials": ("materials", "material_id", "work_order_materials"),
    }

    def lookup_items(self, kind: str, include_inactive: bool = False) -> list[LookupItem]:
        table = self._LOOKUPS[kind][0]
        order = "name COLLATE NOCASE" if kind == "heads" else "sort_order, id"
        cols = "id, name, active" + (", unit, sort_order" if kind == "materials" else "")
        if kind == "sectors":
            cols += ", sort_order"
        sql = f"SELECT {cols} FROM {table}"
        if not include_inactive:
            sql += " WHERE active = 1"
        sql += f" ORDER BY {order}"
        items = []
        for r in self.conn.execute(sql):
            items.append(LookupItem(
                id=r["id"], name=r["name"], active=bool(r["active"]),
                unit=r["unit"] if kind == "materials" else None,
                sort_order=r["sort_order"] if kind != "heads" else 0,
            ))
        return items

    def sectors(self, include_inactive=False):
        return self.lookup_items("sectors", include_inactive)

    def committee_heads(self, include_inactive=False):
        return self.lookup_items("heads", include_inactive)

    def materials(self, include_inactive=False):
        return self.lookup_items("materials", include_inactive)

    def lookup_usage(self, kind: str, item_id: int) -> int:
        _, column, table = self._LOOKUPS[kind]
        return self.conn.execute(f"SELECT count(*) FROM {table} WHERE {column}=?", (item_id,)).fetchone()[0]

    def find_similar(self, kind: str, name: str, exclude_id: int | None = None) -> list[LookupItem]:
        """البحث عن أسماء متشابهة (مثل: علي/على، فاطمة/فاطمه) لمنع التكرار."""
        key = normalize_for_compare(name)
        return [
            item for item in self.lookup_items(kind, include_inactive=True)
            if normalize_for_compare(item.name) == key and item.id != exclude_id
        ]

    def add_lookup(self, kind: str, name: str, unit: str | None = None) -> int:
        table = self._LOOKUPS[kind][0]
        name = clean_spaces(name)
        if not name:
            raise LookupError_("الاسم فارغ.")
        if self.find_similar(kind, name):
            raise LookupError_(f"الاسم «{name}» موجود مسبقاً في القائمة (أو اسم مشابه له).")
        with transaction(self.conn):
            if kind == "heads":
                cur = self.conn.execute("INSERT INTO committee_heads(name) VALUES (?)", (name,))
            else:
                next_order = self.conn.execute(f"SELECT coalesce(max(sort_order), 0) + 1 FROM {table}").fetchone()[0]
                if kind == "materials":
                    cur = self.conn.execute(
                        "INSERT INTO materials(name, unit, sort_order) VALUES (?, ?, ?)", (name, unit, next_order))
                else:
                    cur = self.conn.execute(
                        "INSERT INTO sectors(name, sort_order) VALUES (?, ?)", (name, next_order))
        self.changed = True
        return cur.lastrowid

    def rename_lookup(self, kind: str, item_id: int, name: str, unit: str | None = None) -> None:
        table = self._LOOKUPS[kind][0]
        name = clean_spaces(name)
        if not name:
            raise LookupError_("الاسم فارغ.")
        if self.find_similar(kind, name, exclude_id=item_id):
            raise LookupError_(f"الاسم «{name}» موجود مسبقاً في القائمة (أو اسم مشابه له).")
        with transaction(self.conn):
            if kind == "materials" and unit:
                self.conn.execute("UPDATE materials SET name=?, unit=? WHERE id=?", (name, unit, item_id))
            else:
                self.conn.execute(f"UPDATE {table} SET name=? WHERE id=?", (name, item_id))
        self.changed = True

    def set_lookup_active(self, kind: str, item_id: int, active: bool) -> None:
        table = self._LOOKUPS[kind][0]
        with transaction(self.conn):
            self.conn.execute(f"UPDATE {table} SET active=? WHERE id=?", (1 if active else 0, item_id))
        self.changed = True

    def delete_lookup(self, kind: str, item_id: int) -> None:
        table = self._LOOKUPS[kind][0]
        used = self.lookup_usage(kind, item_id)
        if used:
            raise LookupError_(
                f"لا يمكن الحذف لأن هذا العنصر مستخدم في {used} أمر عمل. يمكنك إخفاؤه بدلاً من حذفه.")
        with transaction(self.conn):
            self.conn.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
        self.changed = True

    def move_lookup(self, kind: str, item_id: int, direction: int) -> None:
        """تحريك عنصر للأعلى (-1) أو للأسفل (+1) في ترتيب العرض."""
        if kind == "heads":
            return
        items = self.lookup_items(kind, include_inactive=True)
        ids = [i.id for i in items]
        pos = ids.index(item_id)
        new_pos = pos + direction
        if not 0 <= new_pos < len(ids):
            return
        ids[pos], ids[new_pos] = ids[new_pos], ids[pos]
        table = self._LOOKUPS[kind][0]
        with transaction(self.conn):
            for order, iid in enumerate(ids, start=1):
                self.conn.execute(f"UPDATE {table} SET sort_order=? WHERE id=?", (order, iid))
        self.changed = True

    # ==================================================================
    # أوامر العمل
    # ==================================================================
    _SELECT = """
        SELECT w.*, s.name AS sector_name, h.name AS committee_head_name
        FROM work_orders w
        LEFT JOIN sectors s ON s.id = w.sector_id
        LEFT JOIN committee_heads h ON h.id = w.committee_head_id
    """

    def _row_to_order(self, r: sqlite3.Row) -> WorkOrder:
        o = WorkOrder(id=r["id"])
        for col in _ORDER_COLUMNS:
            value = r[col]
            if col in _DATE_COLUMNS:
                value = from_iso(value)
            setattr(o, col, value)
        o.notes = o.notes or ""
        o.created_at = r["created_at"]
        o.updated_at = r["updated_at"]
        o.sector_name = r["sector_name"]
        o.committee_head_name = r["committee_head_name"]
        return o

    def _attach_materials(self, orders: list[WorkOrder]) -> None:
        by_id = {o.id: o for o in orders}
        if not by_id:
            return
        if len(by_id) == 1:
            rows = self.conn.execute(
                "SELECT work_order_id, material_id, quantity FROM work_order_materials WHERE work_order_id=?",
                (next(iter(by_id)),))
        else:
            rows = self.conn.execute("SELECT work_order_id, material_id, quantity FROM work_order_materials")
        for r in rows:
            o = by_id.get(r["work_order_id"])
            if o is not None:
                o.materials[r["material_id"]] = r["quantity"]

    def get_order(self, order_id: int) -> WorkOrder | None:
        r = self.conn.execute(self._SELECT + " WHERE w.id=?", (order_id,)).fetchone()
        if r is None:
            return None
        o = self._row_to_order(r)
        self._attach_materials([o])
        return o

    def all_orders(self) -> list[WorkOrder]:
        rows = self.conn.execute(self._SELECT + " ORDER BY w.order_year DESC, w.order_no DESC").fetchall()
        orders = [self._row_to_order(r) for r in rows]
        self._attach_materials(orders)
        return orders

    def orders_with_number(self, order_no: int) -> list[WorkOrder]:
        rows = self.conn.execute(self._SELECT + " WHERE w.order_no=? ORDER BY w.order_year", (order_no,)).fetchall()
        return [self._row_to_order(r) for r in rows]

    def max_order_no(self, year: int) -> int | None:
        return self.conn.execute("SELECT max(order_no) FROM work_orders WHERE order_year=?", (year,)).fetchone()[0]

    def order_count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM work_orders").fetchone()[0]

    def save_order(self, o: WorkOrder) -> int:
        """حفظ أمر العمل (إضافة أو تعديل). يجب التحقق منه قبل الحفظ."""
        values = []
        for col in _ORDER_COLUMNS:
            value = getattr(o, col)
            if col in _DATE_COLUMNS:
                value = to_iso(value)
            values.append(value)
        stamp = now_text()
        with transaction(self.conn):
            if o.id is None:
                cols = ", ".join(_ORDER_COLUMNS + ["created_at", "updated_at"])
                marks = ", ".join("?" * (len(_ORDER_COLUMNS) + 2))
                cur = self.conn.execute(f"INSERT INTO work_orders({cols}) VALUES ({marks})", values + [stamp, stamp])
                order_id = cur.lastrowid
            else:
                sets = ", ".join(f"{c}=?" for c in _ORDER_COLUMNS)
                self.conn.execute(f"UPDATE work_orders SET {sets}, updated_at=? WHERE id=?", values + [stamp, o.id])
                order_id = o.id
            self.conn.execute("DELETE FROM work_order_materials WHERE work_order_id=?", (order_id,))
            for material_id, qty in sorted(o.materials.items()):
                self.conn.execute(
                    "INSERT INTO work_order_materials(work_order_id, material_id, quantity) VALUES (?, ?, ?)",
                    (order_id, material_id, qty))
        self.changed = True
        return order_id

    def delete_order(self, order_id: int) -> None:
        with transaction(self.conn):
            self.conn.execute("DELETE FROM work_orders WHERE id=?", (order_id,))
        self.changed = True

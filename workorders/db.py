"""قاعدة البيانات: الإنشاء والتحديث التلقائي لهيكلها بين إصدارات البرنامج.

قاعدة البيانات ملف SQLite منفصل عن البرنامج (data/workorders.db).
كل تغيير في هيكلها مستقبلاً يُضاف كخطوة جديدة في MIGRATIONS ويُرفع
SCHEMA_VERSION، فيقوم البرنامج الأحدث بتحديث القاعدة القديمة تلقائياً بعد
أخذ نسخة احتياطية منها، دون فقدان أي بيانات.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import __version__
from .constants import APP_ID, DEFAULT_MATERIALS, DEFAULT_SECTORS

SCHEMA_VERSION = 4


class DatabaseError(Exception):
    pass


class DatabaseTooNewError(DatabaseError):
    """قاعدة البيانات أُنشئت أو حُدّثت بإصدار أحدث من هذا البرنامج."""

    def __init__(self, db_version: int):
        super().__init__(db_version)
        self.db_version = db_version


class NotOurDatabaseError(DatabaseError):
    """الملف ليس قاعدة بيانات أرشيف أوامر العمل."""


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None)  # المعاملات تُدار يدوياً
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _has_table(conn, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def check_identity(conn: sqlite3.Connection) -> None:
    """التأكد من أن الملف قاعدة بيانات هذا البرنامج."""
    try:
        if schema_version(conn) == 0:
            tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            if tables:
                raise NotOurDatabaseError()
            return
        if not _has_table(conn, "meta"):
            raise NotOurDatabaseError()
        row = conn.execute("SELECT value FROM meta WHERE key='app_id'").fetchone()
        if row is None or row[0] != APP_ID:
            raise NotOurDatabaseError()
    except sqlite3.DatabaseError as exc:  # ملف تالف أو ليس SQLite
        raise NotOurDatabaseError() from exc


# ----------------------------------------------------------------------
# خطوات إنشاء وتحديث الهيكل
# ----------------------------------------------------------------------
def _migration_1(conn: sqlite3.Connection) -> None:
    # تُنفّذ كل جملة بـ execute (وليس executescript) حتى تبقى داخل نفس المعاملة
    statements = [
        """CREATE TABLE meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""",
        """CREATE TABLE sectors (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active     INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE committee_heads (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name   TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE materials (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            unit       TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active     INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE work_orders (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no          INTEGER NOT NULL CHECK (order_no > 0),
            order_year        INTEGER NOT NULL,
            order_type        TEXT NOT NULL CHECK (order_type IN ('investment','operational','trust')),
            project_name      TEXT NOT NULL,
            work_type         TEXT NOT NULL CHECK (work_type IN ('network','substation','civil')),
            voltage           TEXT CHECK (voltage IS NULL OR voltage IN ('33','11','lv')),
            tech_class        TEXT CHECK (tech_class IS NULL OR tech_class IN ('new','rehab')),
            sector_id         INTEGER REFERENCES sectors(id),
            submit_no         TEXT,
            submit_date       TEXT,
            response          TEXT NOT NULL DEFAULT 'pending'
                              CHECK (response IN ('pending','approved','rejected')),
            response_no       TEXT,
            response_date     TEXT,
            labor_alloc       INTEGER,
            materials_alloc   INTEGER,
            committee_head_id INTEGER REFERENCES committee_heads(id),
            start_no          TEXT,
            start_date        TEXT,
            close_no          TEXT,
            close_date        TEXT,
            cancel_no         TEXT,
            cancel_date       TEXT,
            notes             TEXT NOT NULL DEFAULT '',
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            UNIQUE (order_no, order_year)
        )""",
        "CREATE INDEX ix_work_orders_no ON work_orders(order_no)",
        """CREATE TABLE work_order_materials (
            work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
            material_id   INTEGER NOT NULL REFERENCES materials(id),
            quantity      INTEGER NOT NULL CHECK (quantity > 0),
            PRIMARY KEY (work_order_id, material_id)
        )""",
    ]
    for sql in statements:
        conn.execute(sql)

    conn.execute("INSERT INTO meta(key, value) VALUES ('app_id', ?)", (APP_ID,))
    conn.execute("INSERT INTO meta(key, value) VALUES ('created_at', ?)", (now_text(),))
    for i, name in enumerate(DEFAULT_SECTORS, start=1):
        conn.execute("INSERT INTO sectors(name, sort_order) VALUES (?, ?)", (name, i))
    for i, (name, unit) in enumerate(DEFAULT_MATERIALS, start=1):
        conn.execute("INSERT INTO materials(name, unit, sort_order) VALUES (?, ?, ?)", (name, unit, i))


def _migration_2(conn: sqlite3.Connection) -> None:
    """الإصدار 1.1.0: إضافة تاريخ المباشرة الفعلي، ويأخذ قيمته من تاريخ الأمر الإداري للأوامر الموجودة."""
    conn.execute("ALTER TABLE work_orders ADD COLUMN actual_start_date TEXT")
    conn.execute("UPDATE work_orders SET actual_start_date = start_date WHERE start_date IS NOT NULL")


def _migration_3(conn: sqlite3.Connection) -> None:
    """الإصدار 1.2.0: مجموعات أوامر العمل المختارة المحفوظة بأسماء."""
    conn.execute("""CREATE TABLE order_groups (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE order_group_items (
        group_id      INTEGER NOT NULL REFERENCES order_groups(id) ON DELETE CASCADE,
        work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
        PRIMARY KEY (group_id, work_order_id)
    )""")


def _migration_4(conn: sqlite3.Connection) -> None:
    """الإصدار 1.3.0: الكلفة الكلية للمواد (المتوفرة وغير المتوفرة)."""
    conn.execute("ALTER TABLE work_orders ADD COLUMN total_materials_cost INTEGER")


MIGRATIONS = {
    1: _migration_1,
    2: _migration_2,
    3: _migration_3,
    4: _migration_4,
}


def migrate(conn: sqlite3.Connection) -> None:
    current = schema_version(conn)
    for version in range(current + 1, SCHEMA_VERSION + 1):
        with transaction(conn):
            MIGRATIONS[version](conn)
            conn.execute(f"PRAGMA user_version = {version}")


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return None if row is None else row[0]


def open_database(db_path: Path, backup_before_upgrade=None) -> sqlite3.Connection:
    """فتح قاعدة البيانات (أو إنشاؤها إذا لم تكن موجودة) وتحديث هيكلها.

    backup_before_upgrade: دالة تُستدعى بـ (رقم الهيكل القديم) قبل تحديث
    قاعدة بيانات موجودة، لأخذ نسخة احتياطية منها.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        check_identity(conn)
        version = schema_version(conn)
        if version > SCHEMA_VERSION:
            raise DatabaseTooNewError(version)
        if version < SCHEMA_VERSION:
            if version > 0 and backup_before_upgrade is not None:
                backup_before_upgrade(version)
            migrate(conn)
        with transaction(conn):
            set_meta(conn, "last_app_version", __version__)
            set_meta(conn, "last_opened_at", now_text())
    except BaseException:
        conn.close()
        raise
    return conn

"""النسخ الاحتياطي والاسترجاع لقاعدة البيانات."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .constants import AUTO_BACKUP_KEEP
from .db import DatabaseTooNewError, NotOurDatabaseError, SCHEMA_VERSION, check_identity, schema_version

AUTO_PREFIX = "auto_"


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _readonly_uri(path: Path) -> str:
    """رابط فتح الملف للقراءة فقط (يعمل مع المسارات العربية والمسافات في الويندوز)."""
    return Path(path).resolve().as_uri() + "?mode=ro"


def copy_database(src_conn: sqlite3.Connection, dest_path: Path) -> Path:
    """نسخ قاعدة البيانات بشكل آمن (حتى أثناء فتحها) باستخدام آلية SQLite."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_path.with_suffix(dest_path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    dest = sqlite3.connect(str(tmp))
    try:
        src_conn.backup(dest)
    finally:
        dest.close()
    tmp.replace(dest_path)
    return dest_path


def make_backup(conn: sqlite3.Connection, backups_dir: Path, tag: str) -> Path:
    name = f"{tag}{_stamp()}.db" if tag == AUTO_PREFIX else f"{tag}_{_stamp()}.db"
    target = backups_dir / name
    counter = 1
    while target.exists():
        target = backups_dir / f"{target.stem}_{counter}.db"
        counter += 1
    return copy_database(conn, target)


def auto_backup(conn: sqlite3.Connection, backups_dir: Path, keep: int = AUTO_BACKUP_KEEP) -> Path:
    """نسخة تلقائية (عند الخروج) مع الاحتفاظ بآخر (keep) نسخة فقط."""
    path = make_backup(conn, backups_dir, AUTO_PREFIX)
    prune_auto_backups(backups_dir, keep)
    return path


def prune_auto_backups(backups_dir: Path, keep: int) -> None:
    prune_backups(backups_dir, AUTO_PREFIX, keep)


def prune_backups(backups_dir: Path, prefix: str, keep: int) -> None:
    """حذف النسخ القديمة التي تبدأ بالبادئة المحددة والإبقاء على أحدث (keep) نسخة."""
    files = sorted(backups_dir.glob(f"{prefix}*.db"), key=lambda p: p.name, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def backup_file_before_upgrade(db_path: Path, backups_dir: Path, old_version: int) -> Path:
    src = sqlite3.connect(str(db_path))
    try:
        return make_backup(src, backups_dir, f"before_upgrade_v{old_version}")
    finally:
        src.close()


def inspect_backup(path: Path) -> int:
    """التحقق من أن الملف نسخة احتياطية صالحة لهذا البرنامج. يرجع رقم هيكلها."""
    try:
        conn = sqlite3.connect(_readonly_uri(path), uri=True)
    except sqlite3.Error as exc:
        raise NotOurDatabaseError() from exc
    try:
        check_identity(conn)
        version = schema_version(conn)
        if version == 0:
            raise NotOurDatabaseError()
        if version > SCHEMA_VERSION:
            raise DatabaseTooNewError(version)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise NotOurDatabaseError() from exc
        if result != "ok":
            raise NotOurDatabaseError()
        return version
    finally:
        conn.close()


def restore_into(conn: sqlite3.Connection, backup_path: Path) -> None:
    """استبدال محتوى قاعدة البيانات الحالية بمحتوى النسخة الاحتياطية."""
    src = sqlite3.connect(_readonly_uri(backup_path), uri=True)
    try:
        src.backup(conn)
    finally:
        src.close()

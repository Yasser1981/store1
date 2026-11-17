"""مواقع الملفات: قاعدة البيانات والنسخ الاحتياطية بجانب ملف البرنامج.

هيكل المجلد المحمول:
    WorkOrders.exe        البرنامج
    data/workorders.db    قاعدة البيانات (لا تُمس عند تحديث البرنامج)
    backups/              النسخ الاحتياطية
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def base_dir() -> Path:
    override = os.environ.get("WORKORDERS_HOME")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):  # ملف exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class AppPaths:
    base: Path

    @property
    def data_dir(self) -> Path:
        return self.base / "data"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "workorders.db"

    @property
    def backups_dir(self) -> Path:
        return self.base / "backups"

    @property
    def lock_path(self) -> Path:
        return self.data_dir / "workorders.lock"

    def ensure_writable(self) -> None:
        """إنشاء المجلدات والتأكد من إمكانية الكتابة فيها."""
        for folder in (self.data_dir, self.backups_dir):
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()


def default_paths() -> AppPaths:
    return AppPaths(base_dir())

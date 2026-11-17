"""نقطة تشغيل البرنامج."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .backup import backup_file_before_upgrade
from .constants import APP_NAME
from .db import DatabaseTooNewError, NotOurDatabaseError, open_database
from .paths import AppPaths, default_paths
from .repository import Repository


def _error(title: str, text: str) -> None:
    box = QMessageBox(QMessageBox.Critical, title, text)
    box.setLayoutDirection(Qt.RightToLeft)
    box.exec()


def selftest(app: QApplication, font_family: str, out_file: Path) -> int:
    """فحص ذاتي يُستخدم بعد بناء ملف exe للتأكد من أنه يعمل:
    ينشئ قاعدة بيانات مؤقتة، يحفظ أمر عمل، يفتح الشاشات، ويصدّر تقريراً بصيغتي PDF و Excel."""
    from datetime import date

    from .export import report_to_xlsx
    from .models import WorkOrder
    from .reports import OrderFilter, ReportContext, build_report
    from .ui.main_window import MainWindow
    from .ui.order_dialog import OrderDialog
    from .ui.printing import save_pdf

    lines = []
    with tempfile.TemporaryDirectory() as tmp:
        paths = AppPaths(Path(tmp))
        paths.ensure_writable()
        conn = open_database(paths.db_path)
        repo = Repository(conn)
        repo.save_order(WorkOrder(order_no=1, order_year=date.today().year, order_type="investment",
                                  project_name="فحص ذاتي", work_type="civil"))
        window = MainWindow(repo, paths, font_family)
        window.show()
        for i in range(4):
            window.show_page(i)
            app.processEvents()
        dlg = OrderDialog(repo, repo.get_order(1), window)
        dlg.show()
        app.processEvents()
        dlg.close()
        ctx = ReportContext(repo.sectors(True), repo.committee_heads(True), repo.materials(True), date.today())
        report = build_report("detail", repo.all_orders(), ctx, OrderFilter())
        pdf = save_pdf(report, Path(tmp) / "r.pdf", font_family)
        xlsx = report_to_xlsx(report, Path(tmp) / "r.xlsx")
        lines.append(f"version={__version__}")
        lines.append(f"font={font_family}")
        lines.append(f"orders={repo.order_count()}")
        lines.append(f"pdf_bytes={pdf.stat().st_size}")
        lines.append(f"xlsx_bytes={xlsx.stat().st_size}")
        repo.changed = False
        window.close()
        conn.close()
    lines.append("OK")
    out_file.write_text("\n".join(lines), encoding="utf-8")
    return 0


def main(argv=None, paths: AppPaths | None = None) -> int:
    from .ui.icon import app_icon
    from .ui.main_window import MainWindow
    from .ui.style import apply_style

    argv = list(argv if argv is not None else sys.argv)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    font_family = apply_style(app)
    if "--selftest" in argv:
        out = Path(argv[argv.index("--selftest") + 1]) if len(argv) > argv.index("--selftest") + 1 \
            else Path("selftest.txt")
        return selftest(app, font_family, out)
    paths = paths or default_paths()

    try:
        paths.ensure_writable()
    except OSError as exc:
        _error("تعذر تشغيل البرنامج",
               "لا يمكن الكتابة في مجلد البرنامج:\n"
               f"{paths.base}\n\n"
               "انقل مجلد البرنامج إلى مكان آخر (مثل القرص D أو سطح المكتب) ثم شغّله من جديد.\n"
               "لا تضع البرنامج داخل مجلد Program Files.\n\n"
               f"({exc})")
        return 1

    lock = QLockFile(str(paths.lock_path))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        _error("البرنامج مفتوح مسبقاً",
               "برنامج أرشيف أوامر العمل مفتوح حالياً في نافذة أخرى.\nاستخدم النافذة المفتوحة.")
        return 1

    try:
        conn = open_database(
            paths.db_path,
            backup_before_upgrade=lambda v: backup_file_before_upgrade(paths.db_path, paths.backups_dir, v),
        )
    except DatabaseTooNewError:
        _error("إصدار البرنامج قديم",
               "قاعدة البيانات الموجودة حُدّثت بإصدار أحدث من هذا البرنامج.\n"
               "استخدم الإصدار الأحدث من البرنامج حتى لا تتضرر البيانات.")
        lock.unlock()
        return 1
    except NotOurDatabaseError:
        _error("قاعدة البيانات غير صالحة",
               f"الملف التالي ليس قاعدة بيانات صالحة لهذا البرنامج أو أنه تالف:\n{paths.db_path}\n\n"
               "يمكنك استبداله بآخر نسخة احتياطية من مجلد backups (بعد إعادة تسميتها إلى workorders.db).")
        lock.unlock()
        return 1

    repo = Repository(conn)
    window = MainWindow(repo, paths, font_family)
    window.showMaximized()
    try:
        return app.exec()
    finally:
        conn.close()
        lock.unlock()


if __name__ == "__main__":
    sys.exit(main())

"""شاشة الإعدادات: القوائم، النسخ الاحتياطي، معلومات البرنامج."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..backup import (
    AUTO_PREFIX,
    copy_database,
    inspect_backup,
    make_backup,
    restore_into,
)
from ..constants import APP_NAME, EDITION_NAME, ORG_LINE, UNITS
from ..db import SCHEMA_VERSION, DatabaseTooNewError, NotOurDatabaseError, migrate
from ..paths import AppPaths
from ..repository import LookupError_, Repository
from .widgets import combo_value, make_combo, set_combo_value


class LookupItemDialog(QDialog):
    def __init__(self, title: str, name: str = "", unit: str | None = None, with_unit=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        self.name_edit.setMaxLength(150)
        form.addRow("الاسم:", self.name_edit)
        self.unit_combo = None
        if with_unit:
            self.unit_combo = make_combo([(u, u) for u in UNITS])
            set_combo_value(self.unit_combo, unit or UNITS[0])
            form.addRow("الوحدة:", self.unit_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("حفظ")
        buttons.button(QDialogButtonBox.Cancel).setText("إلغاء الأمر")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self):
        unit = combo_value(self.unit_combo) if self.unit_combo else None
        return self.name_edit.text(), unit


class LookupEditor(QWidget):
    changed = Signal()

    def __init__(self, repo: Repository, kind: str, item_word: str, help_text: str, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.kind = kind
        self.item_word = item_word
        self.with_unit = kind == "materials"
        self.items = []

        lay = QVBoxLayout(self)
        info = QLabel(help_text)
        info.setObjectName("hint")
        info.setWordWrap(True)
        lay.addWidget(info)

        bar = QHBoxLayout()
        self.add_btn = QPushButton(f"إضافة {item_word}")
        self.add_btn.setObjectName("primary")
        self.edit_btn = QPushButton("تعديل")
        self.toggle_btn = QPushButton("إخفاء / إظهار")
        self.delete_btn = QPushButton("حذف")
        self.delete_btn.setObjectName("danger")
        self.up_btn = QPushButton("▲ للأعلى")
        self.down_btn = QPushButton("▼ للأسفل")
        for b in (self.add_btn, self.edit_btn, self.toggle_btn, self.delete_btn):
            bar.addWidget(b)
        if kind != "heads":
            bar.addWidget(self.up_btn)
            bar.addWidget(self.down_btn)
        bar.addStretch(1)
        lay.addLayout(bar)

        headers = ["ت", "الاسم"] + (["الوحدة"] if self.with_unit else []) + ["الحالة", "عدد أوامر العمل"]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)

        self.add_btn.clicked.connect(self._add)
        self.edit_btn.clicked.connect(self._edit)
        self.toggle_btn.clicked.connect(self._toggle)
        self.delete_btn.clicked.connect(self._delete)
        self.up_btn.clicked.connect(lambda: self._move(-1))
        self.down_btn.clicked.connect(lambda: self._move(1))
        self.table.cellDoubleClicked.connect(lambda *_: self._edit())
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.refresh()

    def refresh(self, select_id=None):
        current = select_id if select_id is not None else self._selected_id()
        self.items = self.repo.lookup_items(self.kind, include_inactive=True)
        self.table.setRowCount(len(self.items))
        for r, item in enumerate(self.items):
            values = [str(r + 1), item.name]
            if self.with_unit:
                values.append(item.unit or "")
            values += ["ظاهر في القوائم" if item.active else "مخفي", str(self.repo.lookup_usage(self.kind, item.id))]
            for c, v in enumerate(values):
                cell = QTableWidgetItem(v)
                cell.setData(Qt.UserRole, item.id)
                if c != 1:
                    cell.setTextAlignment(Qt.AlignCenter)
                if not item.active:
                    cell.setForeground(QColor("#8a96a3"))
                self.table.setItem(r, c, cell)
        if current is not None:
            for r, item in enumerate(self.items):
                if item.id == current:
                    self.table.selectRow(r)
        self._update_buttons()

    def _selected_id(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    def _selected(self):
        sid = self._selected_id()
        return next((i for i in self.items if i.id == sid), None)

    def _update_buttons(self):
        has = self._selected_id() is not None
        for b in (self.edit_btn, self.toggle_btn, self.delete_btn, self.up_btn, self.down_btn):
            b.setEnabled(has)

    def _add(self):
        dlg = LookupItemDialog(f"إضافة {self.item_word}", with_unit=self.with_unit, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, unit = dlg.values()
        try:
            new_id = self.repo.add_lookup(self.kind, name, unit)
        except LookupError_ as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return
        self.refresh(select_id=new_id)
        self.changed.emit()

    def _edit(self):
        item = self._selected()
        if item is None:
            return
        dlg = LookupItemDialog(f"تعديل {self.item_word}", item.name, item.unit, self.with_unit, self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, unit = dlg.values()
        used = self.repo.lookup_usage(self.kind, item.id)
        if used and name.strip() != item.name:
            answer = QMessageBox.question(
                self, "تأكيد التعديل",
                f"هذا الاسم مستخدم في {used} أمر عمل، وسيتغير فيها جميعاً إلى «{name.strip()}».\nهل تريد المتابعة؟")
            if answer != QMessageBox.Yes:
                return
        try:
            self.repo.rename_lookup(self.kind, item.id, name, unit)
        except LookupError_ as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return
        self.refresh()
        self.changed.emit()

    def _toggle(self):
        item = self._selected()
        if item is None:
            return
        self.repo.set_lookup_active(self.kind, item.id, not item.active)
        self.refresh()
        self.changed.emit()

    def _delete(self):
        item = self._selected()
        if item is None:
            return
        answer = QMessageBox.question(self, "حذف", f"هل تريد حذف «{item.name}» من القائمة؟")
        if answer != QMessageBox.Yes:
            return
        try:
            self.repo.delete_lookup(self.kind, item.id)
        except LookupError_ as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return
        self.refresh()
        self.changed.emit()

    def _move(self, direction):
        item = self._selected()
        if item is None:
            return
        self.repo.move_lookup(self.kind, item.id, direction)
        self.refresh(select_id=item.id)
        self.changed.emit()


class BackupPanel(QWidget):
    restored = Signal()

    def __init__(self, repo: Repository, paths: AppPaths, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.paths = paths
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        info = QLabel(
            "• يأخذ البرنامج نسخة احتياطية تلقائياً عند كل خروج منه إذا حصل أي تعديل على البيانات، "
            "ويحتفظ بآخر 30 نسخة في مجلد (backups) بجانب البرنامج.\n"
            "• يُنصح بحفظ نسخة احتياطية دورياً على فلاشة أو حاسبة أخرى لحماية البيانات من عطل الحاسبة.\n"
            "• لنقل البرنامج إلى حاسبة أخرى: انسخ مجلد البرنامج بالكامل (ومعه مجلد data).")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.paths_label = QLabel()
        self.paths_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.paths_label.setWordWrap(True)
        lay.addWidget(self.paths_label)

        row = QHBoxLayout()
        self.save_btn = QPushButton("حفظ نسخة احتياطية في مكان آخر (فلاشة مثلاً)...")
        self.save_btn.setObjectName("primary")
        self.restore_btn = QPushButton("استرجاع البيانات من نسخة احتياطية...")
        self.restore_btn.setObjectName("danger")
        self.open_btn = QPushButton("فتح مجلد النسخ الاحتياطية")
        row.addWidget(self.save_btn)
        row.addWidget(self.restore_btn)
        row.addWidget(self.open_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.save_btn.clicked.connect(self._save)
        self.restore_btn.clicked.connect(self._restore)
        self.open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.backups_dir))))
        self.refresh()

    def refresh(self):
        autos = sorted(self.paths.backups_dir.glob(f"{AUTO_PREFIX}*.db"), reverse=True)
        last = autos[0].stem.replace(AUTO_PREFIX, "") if autos else "لا توجد بعد"
        size_kb = self.paths.db_path.stat().st_size / 1024 if self.paths.db_path.exists() else 0
        self.paths_label.setText(
            f"قاعدة البيانات: {self.paths.db_path}  ({size_kb:,.0f} كيلوبايت)\n"
            f"مجلد النسخ الاحتياطية: {self.paths.backups_dir}\n"
            f"عدد النسخ التلقائية: {len(autos)} — آخر نسخة تلقائية: {last}")

    def _save(self):
        default = str(Path.home() / f"workorders_backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.db")
        path, _ = QFileDialog.getSaveFileName(self, "حفظ نسخة احتياطية", default, "قاعدة بيانات (*.db)")
        if not path:
            return
        if not path.lower().endswith(".db"):
            path += ".db"
        if Path(path).resolve() == self.paths.db_path.resolve():
            QMessageBox.warning(self, "تنبيه", "لا يمكن الحفظ فوق قاعدة البيانات الحالية. اختر مكاناً آخر.")
            return
        try:
            copy_database(self.repo.conn, Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ النسخة الاحتياطية.\n\n{exc}")
            return
        QMessageBox.information(self, "تم", f"تم حفظ النسخة الاحتياطية في:\n{path}")

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر ملف النسخة الاحتياطية", str(self.paths.backups_dir), "قاعدة بيانات (*.db)")
        if not path:
            return
        src = Path(path)
        if src.resolve() == self.paths.db_path.resolve():
            QMessageBox.warning(self, "تنبيه", "هذا الملف هو قاعدة البيانات الحالية نفسها.")
            return
        try:
            inspect_backup(src)
        except DatabaseTooNewError:
            QMessageBox.critical(self, "لا يمكن الاسترجاع",
                                 "هذه النسخة الاحتياطية من إصدار أحدث للبرنامج. استخدم الإصدار الأحدث لاسترجاعها.")
            return
        except NotOurDatabaseError:
            QMessageBox.critical(self, "لا يمكن الاسترجاع",
                                 "الملف المختار ليس نسخة احتياطية صالحة لبرنامج أرشيف أوامر العمل، أو أنه تالف.")
            return
        answer = QMessageBox.warning(
            self, "تأكيد الاسترجاع",
            "سيتم استبدال جميع البيانات الحالية ببيانات النسخة الاحتياطية المختارة:\n"
            f"{src.name}\n\n(سيأخذ البرنامج نسخة احتياطية من البيانات الحالية قبل الاستبدال)\n\nهل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            make_backup(self.repo.conn, self.paths.backups_dir, "before_restore")
            restore_into(self.repo.conn, src)
            migrate(self.repo.conn)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "خطأ", f"تعذر الاسترجاع.\n\n{exc}")
            return
        self.repo.changed = True
        self.refresh()
        self.restored.emit()
        QMessageBox.information(self, "تم", "تم استرجاع البيانات بنجاح.")


class AboutPanel(QWidget):
    def __init__(self, repo: Repository, paths: AppPaths, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.paths = paths
        lay = QVBoxLayout(self)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setAlignment(Qt.AlignTop | Qt.AlignRight)
        lay.addWidget(self.label)
        lay.addStretch(1)
        self.refresh()

    def refresh(self):
        self.label.setText(
            f"<h2 style='color:#0d3c61'>{APP_NAME}</h2>"
            f"<p><b>{ORG_LINE}</b></p>"
            f"<p>{EDITION_NAME}</p>"
            f"<p>رقم الإصدار: <b>{__version__}</b><br/>"
            f"رقم هيكل قاعدة البيانات: {SCHEMA_VERSION}<br/>"
            f"عدد أوامر العمل المسجلة: {self.repo.order_count()}</p>"
            f"<p>مجلد البرنامج: {self.paths.base}</p>"
            "<p style='color:#5f6b7a'>يعمل البرنامج بدون إنترنت. قاعدة البيانات ملف منفصل في مجلد data، "
            "ولا تتأثر عند تحديث البرنامج إلى إصدار أحدث.</p>")


class SettingsPage(QWidget):
    lookups_changed = Signal()
    restored = Signal()

    def __init__(self, repo: Repository, paths: AppPaths, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        title = QLabel("الإعدادات")
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        self.sectors = LookupEditor(
            repo, "sectors", "قطاع",
            "قائمة قطاعات التوزيع التي تظهر عند اختيار جهد 11 ك.ف أو الضغط الواطئ. "
            "القطاع المستخدم في أوامر عمل لا يمكن حذفه، لكن يمكن إخفاؤه من القوائم.")
        self.heads = LookupEditor(
            repo, "heads", "اسم",
            "أسماء رؤساء لجان التنفيذ. تُضاف الأسماء الجديدة تلقائياً عند كتابتها في شاشة أمر العمل. "
            "تعديل الاسم هنا يغيّره في جميع أوامر العمل المرتبطة به.")
        self.materials = LookupEditor(
            repo, "materials", "مادة",
            "المواد الحاكمة التي تظهر في شاشة أمر العمل. يمكن إضافة مادة جديدة مستقبلاً وتحديد وحدتها (متر أو عدد).")
        self.backup = BackupPanel(repo, paths)
        self.about = AboutPanel(repo, paths)
        self.tabs.addTab(self.sectors, "قطاعات التوزيع")
        self.tabs.addTab(self.heads, "رؤساء لجان التنفيذ")
        self.tabs.addTab(self.materials, "المواد الحاكمة")
        self.tabs.addTab(self.backup, "النسخ الاحتياطي")
        self.tabs.addTab(self.about, "حول البرنامج")
        for editor in (self.sectors, self.heads, self.materials):
            editor.changed.connect(self.lookups_changed)
        self.backup.restored.connect(self.restored)

    def refresh(self):
        for editor in (self.sectors, self.heads, self.materials):
            editor.refresh()
        self.backup.refresh()
        self.about.refresh()

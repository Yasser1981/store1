"""النافذة الرئيسية للبرنامج."""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..backup import auto_backup
from ..constants import APP_NAME, EDITION_NAME
from ..paths import AppPaths
from ..reports import OrderFilter
from ..repository import Repository
from . import messages
from .dashboard import DashboardPage
from .order_dialog import SAVE_AND_NEW, OrderDialog
from .orders_page import OrdersPage
from .reports_page import ReportsPage
from .settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, repo: Repository, paths: AppPaths, font_family: str, today: date | None = None):
        super().__init__()
        self.repo = repo
        self.paths = paths
        self.today = today or date.today()
        self.setWindowTitle(f"{APP_NAME} – فرع توزيع كهرباء كربلاء المقدسة – {EDITION_NAME} – الإصدار {__version__}")
        self.resize(1366, 860)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------------- القائمة الجانبية
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 18, 12, 14)
        side.setSpacing(6)
        t = QLabel(APP_NAME)
        t.setObjectName("appTitle")
        t.setWordWrap(True)
        s = QLabel(f"فرع توزيع كهرباء كربلاء المقدسة\n{EDITION_NAME}")
        s.setObjectName("appSubtitle")
        s.setWordWrap(True)
        side.addWidget(t)
        side.addWidget(s)
        side.addSpacing(14)
        self.new_btn = QPushButton("+  أمر عمل جديد")
        self.new_btn.setObjectName("newOrder")
        side.addWidget(self.new_btn)
        side.addSpacing(10)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(repo, self.today)
        self.orders = OrdersPage(repo, self.today, paths.backups_dir)
        self.reports = ReportsPage(repo, self.today, font_family)
        self.settings = SettingsPage(repo, paths)
        pages = [
            ("الرئيسية", self.dashboard),
            ("أوامر العمل", self.orders),
            ("التقارير", self.reports),
            ("الإعدادات", self.settings),
        ]
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons = []
        for i, (label, page) in enumerate(pages):
            b = QPushButton(label)
            b.setObjectName("navButton")
            b.setCheckable(True)
            self.nav.addButton(b, i)
            side.addWidget(b)
            self.stack.addWidget(page)
            self.nav_buttons.append(b)
        side.addStretch(1)
        version = QLabel(f"الإصدار {__version__}")
        version.setObjectName("appSubtitle")
        side.addWidget(version)

        root.addWidget(sidebar)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.nav.idClicked.connect(self.show_page)
        self.new_btn.clicked.connect(self.new_order)
        self.orders.request_new.connect(self.new_order)
        self.orders.request_open.connect(self.open_order)
        self.orders.data_changed.connect(self.refresh_all)
        self.dashboard.open_list.connect(self.show_filtered_list)
        self.settings.lookups_changed.connect(self.refresh_all)
        self.settings.restored.connect(self.refresh_all)

        self.show_page(0)

    # ------------------------------------------------------------------
    def show_page(self, index: int):
        self.nav_buttons[index].setChecked(True)
        self.stack.setCurrentIndex(index)
        page = self.stack.currentWidget()
        page.refresh()

    def refresh_all(self):
        self.stack.currentWidget().refresh()

    def show_filtered_list(self, f: OrderFilter):
        self.show_page(1)
        self.orders.filters.set_filter(f)

    def new_order(self):
        defaults = None
        while True:
            dlg = OrderDialog(self.repo, None, self, self.today, defaults)
            result = dlg.exec()
            if dlg.saved_id is not None:
                self._after_save(dlg.saved_id)
            if result != SAVE_AND_NEW:
                break
            saved = self.repo.get_order(dlg.saved_id)
            defaults = {"order_year": saved.order_year, "order_type": saved.order_type}

    def open_order(self, order_id: int):
        order = self.repo.get_order(order_id)
        if order is None:
            return
        dlg = OrderDialog(self.repo, order, self, self.today)
        result = dlg.exec()
        if dlg.saved_id is not None:
            self._after_save(dlg.saved_id)
        if result == SAVE_AND_NEW:
            self.new_order()

    def _after_save(self, order_id: int):
        if self.stack.currentWidget() is not self.orders:
            self.refresh_all()
        else:
            self.orders.refresh()
            self.orders.select_order(order_id)

    def closeEvent(self, event):  # noqa: N802
        if self.repo.changed:
            try:
                auto_backup(self.repo.conn, self.paths.backups_dir)
            except Exception as exc:  # noqa: BLE001
                messages.warning(self, "تنبيه", f"تعذر أخذ النسخة الاحتياطية التلقائية:\n{exc}")
        super().closeEvent(event)


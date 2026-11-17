"""حقول إدخال مخصصة تمنع الأخطاء: أرقام فقط، مبالغ بفواصل الآلاف، تواريخ من تقويم."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QLocale, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..textutil import normalize_digits, only_digits

IRAQ_LOCALE = QLocale(QLocale.Arabic, QLocale.Iraq)


# ----------------------------------------------------------------------
# أيقونات بسيطة مرسومة برمجياً (بدون ملفات خارجية)
# ----------------------------------------------------------------------
def calendar_icon(size: int = 20) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#0d3c61"), 1.4))
    p.setBrush(QColor("#ffffff"))
    body = QRect(2, 4, size - 4, size - 6)
    p.drawRoundedRect(body, 2, 2)
    p.fillRect(QRect(3, 5, size - 6, 4), QColor("#1565c0"))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0d3c61"))
    step = (size - 8) / 3
    for row in range(2):
        for col in range(3):
            p.drawRect(int(5 + col * step), int(11 + row * 4), 2, 2)
    p.end()
    return QIcon(pm)


class NoWheelComboBox(QComboBox):
    """قائمة منسدلة لا تتغير قيمتها بعجلة الفأرة عن طريق الخطأ أثناء تمرير الشاشة."""

    def wheelEvent(self, event):  # noqa: N802
        event.ignore()


def make_combo(options, placeholder: str = "— اختر —", editable: bool = False) -> NoWheelComboBox:
    """options: قاموس {القيمة: التسمية} أو قائمة أزواج (القيمة، التسمية)."""
    combo = NoWheelComboBox()
    combo.setEditable(editable)
    fill_combo(combo, options)
    combo.setPlaceholderText(placeholder)
    combo.setCurrentIndex(-1)
    combo.setMinimumWidth(150)
    return combo


def fill_combo(combo: QComboBox, options) -> None:
    items = options.items() if isinstance(options, dict) else options
    combo.blockSignals(True)
    combo.clear()
    for value, label in items:
        combo.addItem(label, value)
    combo.blockSignals(False)


def combo_value(combo: QComboBox):
    if combo.currentIndex() < 0:
        return None
    return combo.currentData()


def set_combo_value(combo: QComboBox, value) -> None:
    if value is None:
        combo.setCurrentIndex(-1)
        return
    idx = combo.findData(value)
    combo.setCurrentIndex(idx)


# ----------------------------------------------------------------------
class NumberEdit(QLineEdit):
    """حقل أرقام فقط. يحوّل الأرقام العربية (١٢٣) تلقائياً إلى (123).
    grouping=True: يعرض فواصل الآلاف (للمبالغ والكميات)."""

    def __init__(self, grouping: bool = False, max_digits: int = 9, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.grouping = grouping
        self.max_digits = max_digits
        self.setLayoutDirection(Qt.LeftToRight)
        self.setAlignment(Qt.AlignCenter)
        self.setPlaceholderText(placeholder)
        self.textEdited.connect(self._reformat)

    def _reformat(self, text: str) -> None:
        cursor = self.cursorPosition()
        digits_before_cursor = len(only_digits(text[:cursor]))
        digits = only_digits(text)[: self.max_digits]
        if self.grouping and digits:
            digits = digits.lstrip("0") or "0"
            new_text = f"{int(digits):,}"
        else:
            new_text = digits
        if new_text != text:
            self.setText(new_text)
            # إعادة المؤشر إلى موضعه الصحيح بعد إضافة الفواصل
            count = 0
            pos = 0
            for i, ch in enumerate(new_text):
                if count >= digits_before_cursor:
                    break
                if ch.isdigit():
                    count += 1
                pos = i + 1
            self.setCursorPosition(pos)

    def value(self) -> int | None:
        digits = only_digits(self.text())
        return int(digits) if digits else None

    def text_value(self) -> str | None:
        """للأرقام النصية (أرقام الكتب): يُرجع النص بدون تحويل."""
        digits = only_digits(self.text())
        return digits or None

    def set_value(self, value) -> None:
        if value is None or value == "":
            self.setText("")
        elif self.grouping:
            self.setText(f"{int(value):,}")
        else:
            self.setText(str(value))

    def keyPressEvent(self, event):  # noqa: N802
        text = normalize_digits(event.text())
        if text and len(text) == 1 and not text.isdigit() and text.isprintable() and not event.modifiers() & (
                Qt.ControlModifier | Qt.AltModifier):
            event.ignore()  # منع الحروف والرموز
            return
        super().keyPressEvent(event)


# ----------------------------------------------------------------------
class LatinDigitsCalendar(QCalendarWidget):
    """تقويم بأسماء الأشهر العراقية (كانون الثاني...) وأرقام إنكليزية."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(IRAQ_LOCALE)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setGridVisible(False)
        self.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        self.setFirstDayOfWeek(Qt.Saturday)
        # العطلة الرسمية في العراق: الجمعة والسبت
        normal = QTextCharFormat()
        normal.setForeground(QColor("#1f2933"))
        weekend = QTextCharFormat()
        weekend.setForeground(QColor("#c62828"))
        for day in (Qt.Monday, Qt.Tuesday, Qt.Wednesday, Qt.Thursday, Qt.Sunday):
            self.setWeekdayTextFormat(day, normal)
        for day in (Qt.Friday, Qt.Saturday):
            self.setWeekdayTextFormat(day, weekend)
        font = self.font()
        font.setPointSize(10)
        self.setFont(font)
        year_edit = self.findChild(QSpinBox, "qt_calendar_yearedit")
        if year_edit is not None:
            year_edit.setLocale(QLocale.c())
        self.currentPageChanged.connect(lambda *_: QTimer.singleShot(0, self._fix_year_button))
        QTimer.singleShot(0, self._fix_year_button)

    def _fix_year_button(self) -> None:
        button = self.findChild(QToolButton, "qt_calendar_yearbutton")
        if button is not None:
            button.setText(str(self.yearShown()))
        month = self.findChild(QToolButton, "qt_calendar_monthbutton")
        if month is not None:
            month.setText(f"{IRAQ_LOCALE.standaloneMonthName(self.monthShown())} ({self.monthShown()})")

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._fix_year_button()

    def paintCell(self, painter: QPainter, rect: QRect, d: QDate):  # noqa: N802
        painter.save()
        in_month = d.month() == self.monthShown()
        enabled = self.minimumDate() <= d <= self.maximumDate()
        selected = d == self.selectedDate()
        if selected:
            painter.fillRect(rect.adjusted(2, 2, -2, -2), QColor("#1565c0"))
            painter.setPen(QColor("#ffffff"))
        else:
            if d == QDate.currentDate():
                painter.setPen(QPen(QColor("#1565c0"), 1.5))
                painter.drawRect(rect.adjusted(3, 3, -3, -3))
            if not enabled:
                painter.setPen(QColor("#c4c9cf"))
            elif not in_month:
                painter.setPen(QColor("#9aa5b1"))
            elif d.dayOfWeek() in (5, 6):  # الجمعة والسبت
                painter.setPen(QColor("#c62828"))
            else:
                painter.setPen(QColor("#1f2933"))
        painter.drawText(rect, Qt.AlignCenter, str(d.day()))
        painter.restore()


class DateEdit(QWidget):
    """حقل تاريخ (يوم/شهر/سنة): يُكتب مباشرة أو يُختار من التقويم، ويمكن تركه فارغاً."""

    changed = Signal()

    MIN_DATE = date(2000, 1, 1)

    def __init__(self, parent=None, max_today: bool = True):
        super().__init__(parent)
        self.max_today = max_today
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.line = QLineEdit()
        self.line.setLayoutDirection(Qt.LeftToRight)
        self.line.setInputMask("00/00/0000;_")
        self.line.setAlignment(Qt.AlignCenter)
        self.line.setFixedWidth(130)
        self.line.setToolTip("اكتب التاريخ (يوم/شهر/سنة) أو اضغط زر التقويم")
        self.line.textChanged.connect(self._on_text)

        self.cal_btn = QToolButton()
        self.cal_btn.setIcon(calendar_icon())
        self.cal_btn.setIconSize(QSize(20, 20))
        self.cal_btn.setToolTip("اختيار التاريخ من التقويم")
        self.cal_btn.setCursor(Qt.PointingHandCursor)
        self.cal_btn.clicked.connect(self.open_calendar)

        self.clear_btn = QToolButton()
        self.clear_btn.setText("×")
        self.clear_btn.setToolTip("مسح التاريخ")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear)

        layout.addWidget(self.line)
        layout.addWidget(self.cal_btn)
        layout.addWidget(self.clear_btn)
        layout.addStretch(1)
        self._popup = None

    # ------------------------------------------------------------------
    def _on_text(self, _text):
        self.changed.emit()

    def setFocus(self, *args):  # noqa: N802
        self.line.setFocus(*args)

    def is_empty(self) -> bool:
        return only_digits(self.line.text()) == ""

    def is_invalid(self) -> bool:
        """تاريخ ناقص أو غير صحيح (مثل 31/02/2026)."""
        return not self.is_empty() and self.date() is None

    def date(self) -> date | None:
        digits = only_digits(self.line.text())
        if len(digits) != 8:
            return None
        try:
            d = date(int(digits[4:]), int(digits[2:4]), int(digits[:2]))
        except ValueError:
            return None
        if d < self.MIN_DATE:
            return None
        return d

    def set_date(self, d: date | None) -> None:
        self.line.setText(d.strftime("%d/%m/%Y") if d else "")

    def clear(self) -> None:
        self.line.setText("")
        self.line.setFocus()

    def open_calendar(self) -> None:
        popup = QFrame(self, Qt.Popup)
        popup.setFrameShape(QFrame.Box)
        popup.setStyleSheet("QFrame { background: white; border: 1px solid #8fa3b8; }")
        lay = QVBoxLayout(popup)
        lay.setContentsMargins(4, 4, 4, 4)
        cal = LatinDigitsCalendar(popup)
        cal.setMinimumDate(QDate(self.MIN_DATE.year, 1, 1))
        if self.max_today:
            cal.setMaximumDate(QDate.currentDate())
        current = self.date()
        cal.setSelectedDate(QDate(current.year, current.month, current.day) if current else QDate.currentDate())
        lay.addWidget(cal)
        hint = QLabel("انقر على اليوم المطلوب")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("border: none; color: #5f6b7a;")
        lay.addWidget(hint)

        def chosen(qd: QDate):
            self.set_date(date(qd.year(), qd.month(), qd.day()))
            popup.close()
            self.line.setFocus()

        cal.clicked.connect(chosen)
        cal.activated.connect(chosen)
        popup.adjustSize()
        anchor = self.mapToGlobal(QPoint(0, self.height()))
        x = anchor.x() + self.width() - popup.width() if self.layoutDirection() == Qt.RightToLeft else anchor.x()
        screen = self.screen().availableGeometry() if self.screen() else None
        y = anchor.y()
        if screen is not None:
            x = max(screen.left(), min(x, screen.right() - popup.width()))
            if y + popup.height() > screen.bottom():
                y = self.mapToGlobal(QPoint(0, 0)).y() - popup.height()
        popup.move(x, y)
        self._popup = popup
        popup.show()
        cal.setFocus()


class MoneyEdit(QWidget):
    """حقل مبلغ بالدينار العراقي (أرقام صحيحة بفواصل الآلاف)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.edit = NumberEdit(grouping=True, max_digits=15)
        self.edit.setMinimumWidth(170)
        lay.addWidget(self.edit)
        lay.addWidget(QLabel("دينار"))
        lay.addStretch(1)
        self.textChanged = self.edit.textChanged

    def value(self):
        return self.edit.value()

    def set_value(self, v):
        self.edit.set_value(v)

    def setFocus(self, *args):  # noqa: N802
        self.edit.setFocus(*args)


def make_head_combo() -> NoWheelComboBox:
    """قائمة رؤساء اللجان: اختيار من القائمة أو كتابة اسم جديد (يُضاف للقائمة عند الحفظ)."""
    combo = NoWheelComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.lineEdit().setPlaceholderText("اختر من القائمة أو اكتب اسماً جديداً")
    completer = QCompleter(combo.model(), combo)
    completer.setFilterMode(Qt.MatchContains)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setCompletionMode(QCompleter.PopupCompletion)
    combo.setCompleter(completer)
    combo.setMinimumWidth(320)
    return combo


class StatusChip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusChip")
        self.setAlignment(Qt.AlignCenter)

    def set_status(self, label: str, fg: str, bg: str) -> None:
        self.setText(label)
        self.setStyleSheet(f"QLabel#statusChip {{ color: {fg}; background: {bg}; border: 1px solid {fg}; }}")

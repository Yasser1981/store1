"""رسائل التنبيه والتأكيد بأزرار عربية (نعم / لا / حسناً).

نفس طريقة استدعاء رسائل Qt القياسية، لكن نصوص الأزرار بالعربي والاتجاه من اليمين لليسار.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

_BUTTON_TEXTS = {
    QMessageBox.Yes: "نعم",
    QMessageBox.No: "لا",
    QMessageBox.Ok: "حسناً",
    QMessageBox.Cancel: "إلغاء الأمر",
}


def _show(icon, parent, title, text, buttons, default):
    box = QMessageBox(icon, title, text, buttons, parent)
    box.setLayoutDirection(Qt.RightToLeft)
    for standard, label in _BUTTON_TEXTS.items():
        button = box.button(standard)
        if button is not None:
            button.setText(label)
            button.setMinimumWidth(90)
    if default is not None:
        box.setDefaultButton(default)
    return QMessageBox.StandardButton(box.exec())


def question(parent, title, text, buttons=QMessageBox.Yes | QMessageBox.No, default=None):
    return _show(QMessageBox.Question, parent, title, text, buttons, default)


def warning(parent, title, text, buttons=QMessageBox.Ok, default=None):
    return _show(QMessageBox.Warning, parent, title, text, buttons, default)


def information(parent, title, text, buttons=QMessageBox.Ok, default=None):
    return _show(QMessageBox.Information, parent, title, text, buttons, default)


def critical(parent, title, text, buttons=QMessageBox.Ok, default=None):
    return _show(QMessageBox.Critical, parent, title, text, buttons, default)

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


def ask_text(parent, title: str, label: str, text: str = "") -> str | None:
    """طلب نص من المستخدم (مثل اسم مجموعة) بأزرار عربية. يرجع None عند الإلغاء."""
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLayoutDirection(Qt.RightToLeft)
    dialog.setMinimumWidth(460)
    lay = QVBoxLayout(dialog)
    lay.addWidget(QLabel(label))
    edit = QLineEdit(text)
    edit.setMaxLength(150)
    lay.addWidget(edit)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("حفظ")
    buttons.button(QDialogButtonBox.Cancel).setText("إلغاء الأمر")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    lay.addWidget(buttons)
    if dialog.exec() != QDialog.Accepted:
        return None
    return edit.text()


def choose(parent, title: str, text: str, options: list[str]) -> int | None:
    """رسالة بعدة أزرار مخصصة. يرجع رقم الزر المختار أو None عند الإلغاء."""
    box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.NoButton, parent)
    box.setLayoutDirection(Qt.RightToLeft)
    buttons = [box.addButton(label, QMessageBox.AcceptRole) for label in options]
    cancel = box.addButton("إلغاء الأمر", QMessageBox.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    return buttons.index(clicked) if clicked in buttons else None

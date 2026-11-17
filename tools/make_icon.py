"""إنشاء ملف الأيقونة assets/app.ico (بعدة أحجام) المستخدم في ملف exe.

يحتاج: PySide6 و Pillow (لأداة المطور فقط، وليس للبرنامج نفسه).
"""

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from workorders.ui.icon import draw_icon  # noqa: E402

if __name__ == "__main__":
    app = QGuiApplication([])
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    draw_icon(256).save(buf, "PNG")
    img = Image.open(io.BytesIO(bytes(buf.data())))
    out = Path(__file__).resolve().parent.parent / "assets" / "app.ico"
    out.parent.mkdir(exist_ok=True)
    img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("saved", out)

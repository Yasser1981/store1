"""تشغيل برنامج أرشيف أوامر العمل (يُستخدم أيضاً لبناء ملف exe)."""

import sys

from workorders.app import main

if __name__ == "__main__":
    sys.exit(main())

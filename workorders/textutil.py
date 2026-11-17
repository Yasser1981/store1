"""أدوات مساعدة للنصوص والأرقام والتواريخ."""

from __future__ import annotations

import re
from datetime import date

# تحويل الأرقام العربية (١٢٣) والفارسية (۱۲۳) إلى أرقام إنكليزية (123)
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})

# التشكيل والتطويل
_DIACRITICS = re.compile("[ً-ْٰـ]")
_LETTER_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي",
    "ة": "ه",
    "ؤ": "و",
})


def normalize_digits(text: str) -> str:
    return (text or "").translate(_DIGIT_MAP)


def clean_spaces(text: str) -> str:
    """إزالة الفراغات الزائدة في البداية والنهاية وبين الكلمات."""
    return " ".join((text or "").split())


def normalize_for_compare(text: str) -> str:
    """صيغة موحدة للمقارنة والبحث، بحيث يُعتبر (علي/على) و(فاطمة/فاطمه)
    و(أحمد/احمد) متشابهة، لكشف تكرار الأسماء بأشكال مختلفة."""
    s = clean_spaces(normalize_digits(text))
    s = _DIACRITICS.sub("", s)
    s = s.translate(_LETTER_MAP)
    return s.lower()


def only_digits(text: str) -> str:
    return "".join(ch for ch in normalize_digits(text) if ch.isdigit() and ch.isascii())


def fmt_int(value: int | None) -> str:
    return "" if value is None else f"{value:,}"


def fmt_date(value: date | None) -> str:
    return "" if value is None else value.strftime("%d/%m/%Y")


def to_iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def from_iso(value: str | None) -> date | None:
    return None if not value else date.fromisoformat(value)


def book_text(number: str | None, when: date | None) -> str:
    """نص مختصر لكتاب رسمي: (رقم 123 في 15/03/2026)."""
    if not number and not when:
        return ""
    parts = []
    if number:
        parts.append(f"رقم {number}")
    if when:
        parts.append(f"في {fmt_date(when)}")
    return " ".join(parts)

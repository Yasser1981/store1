"""الثوابت والقوائم الثابتة المستخدمة في البرنامج.

تُخزَّن القيم في قاعدة البيانات برموز إنكليزية ثابتة (مثل "investment")
وتُعرض للمستخدم بالتسميات العربية أدناه، حتى لا يتأثر الأرشيف لو عُدّلت
صياغة أي تسمية مستقبلاً.
"""

APP_ID = "karbala-workorders"
APP_NAME = "أرشيف أوامر العمل"
EDITION_NAME = "نسخة قسم التخطيط"
ORG_LINE = "الشركة العامة لتوزيع كهرباء الفرات الأوسط – فرع توزيع كهرباء كربلاء المقدسة"

# أول سنة في قائمة السنوات (حسب طلب قسم التخطيط)
FIRST_YEAR = 2026

# الحد الأقصى لعدد النسخ الاحتياطية التلقائية المحفوظة
AUTO_BACKUP_KEEP = 30

ORDER_TYPES = {
    "investment": "استثماري",
    "operational": "تشغيلي",
    "trust": "تنفيذ أمانة",
}

WORK_TYPES = {
    "network": "شبكة كهربائية",
    "substation": "نصب معدات محطة ثانوية",
    "civil": "أعمال مدنية",
}

VOLTAGES = {
    "33": "33 ك.ف",
    "11": "11 ك.ف",
    "lv": "ضغط واطئ",
}

# التصنيف الفني يخص 33 و 11 ك.ف فقط (لا يوجد في الضغط الواطئ)
VOLTAGES_WITH_TECH = ("33", "11")
# قطاع التوزيع يُذكر في حالة 11 ك.ف والضغط الواطئ فقط
VOLTAGES_WITH_SECTOR = ("11", "lv")

TECH_CLASSES = {
    "new": "استحداث مغذي جديد",
    "rehab": "تأهيل مغذي موجود",
}

# رد الشركة العامة على كتاب الرفع
RESPONSES = {
    "pending": "لم ترد الموافقة",
    "approved": "تمت الموافقة",
    "rejected": "مرفوض",
}


class Status:
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    STARTED = "started"
    CLOSED = "closed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


STATUS_LABELS = {
    Status.DRAFT: "معدّ – لم يُرفع",
    Status.SUBMITTED: "مرفوع – لم ترد الموافقة",
    Status.APPROVED: "موافق عليه – لم يُباشر به",
    Status.STARTED: "مباشر به – قيد التنفيذ",
    Status.CLOSED: "مغلق",
    Status.REJECTED: "مرفوض",
    Status.CANCELLED: "ملغى",
}

# الحالات التي ينتهي عندها أمر العمل ويتحرر رقمه
FINISHED_STATUSES = (Status.CLOSED, Status.REJECTED, Status.CANCELLED)

# ألوان الحالات في الشاشات والتقارير (لون النص، لون الخلفية)
STATUS_COLORS = {
    Status.DRAFT: ("#455a64", "#eceff1"),
    Status.SUBMITTED: ("#8a5300", "#fff3e0"),
    Status.APPROVED: ("#0d47a1", "#e3f2fd"),
    Status.STARTED: ("#4a148c", "#f3e5f5"),
    Status.CLOSED: ("#1b5e20", "#e8f5e9"),
    Status.REJECTED: ("#b71c1c", "#ffebee"),
    Status.CANCELLED: ("#424242", "#e0e0e0"),
}

UNIT_METER = "متر"
UNIT_COUNT = "عدد"
UNITS = (UNIT_METER, UNIT_COUNT)

DEFAULT_SECTORS = [
    "المركز",
    "السلام",
    "الجنوبي",
    "الشمالي",
    "الحر",
    "الحسينية",
    "الهندية",
    "الجدول الغربي",
    "عين التمر",
]

# المواد الحاكمة بنفس الترتيب والصياغة المرسلة من قسم التخطيط
DEFAULT_MATERIALS = [
    ("قابلو 1×400 ملم2 جهد 33 ك.ف", UNIT_METER),
    ("قابلو 3×150 ملم2 جهد 33 ك.ف", UNIT_METER),
    ("قابلو 3×150 ملم2 جهد 11 ك.ف", UNIT_METER),
    ("سلك ألمنيوم 210/35 ملم2", UNIT_METER),
    ("سلك ألمنيوم 120/20 ملم2", UNIT_METER),
    ("عمود مشبك 14م", UNIT_COUNT),
    ("عمود مشبك 11م", UNIT_COUNT),
    ("عمود مدور 11م", UNIT_COUNT),
    ("محولة 33/0.4 ك.ف", UNIT_COUNT),
    ("محولة 11/0.4 ك.ف", UNIT_COUNT),
    ("عمود مشبك 9م", UNIT_COUNT),
    ("عمود مدور 9م", UNIT_COUNT),
    ("سلك ألمنيوم 95 ملم2", UNIT_METER),
    ("قابلو معلق مبروم", UNIT_METER),
]

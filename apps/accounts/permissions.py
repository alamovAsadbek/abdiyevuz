"""Bo'lim × amal ruxsatlari.

Har bir bo'lim uchun amallar: view (ko'rish), add (qo'shish), edit (tahrirlash), delete (o'chirish), use (foydalanish).
 - Asosiy o'qituvchi — hammasi.
 - Yordamchi o'qituvchi / talaba — faqat berilgan amallar. «Ko'rish» berilmagan bo'lim umuman ko'rinmaydi;
   faqat «Ko'rish» berilgan bo'lim — faqat o'qish uchun (read-only).
Ruxsatlar faqat serverda tekshiriladi (apps.core.middleware.SectionAccessMiddleware + view'lar).
"""

VIEW, ADD, EDIT, DELETE, USE = "view", "add", "edit", "delete", "use"
CRUD = [VIEW, ADD, EDIT, DELETE]
ACTION_LABELS = {VIEW: "Ko‘rish", ADD: "Qo‘shish", EDIT: "Tahrirlash", DELETE: "O‘chirish", USE: "Ruxsat"}
ACTION_ICONS = {VIEW: "eye", ADD: "plus", EDIT: "edit-2", DELETE: "trash-2", USE: "check"}

# code, nomi, ikonka, mavjud amallar, qaysi rollarga tegishli (a — yordamchi, s — talaba), izoh
SECTIONS = [
    ("articles", "Maqolalar", "file-text", CRUD, "as", "Maqolalar lentasi, maqola yozish va tahrirlash"),
    ("courses", "Kurslar va darslar", "play-circle", CRUD, "as", "Kurs, modul, video dars va qo‘llanma fayllari"),
    ("tests", "Testlar", "check-square", CRUD, "as", "Test yaratish, vaqtini boshqarish, natijalar"),
    ("tasks", "Vazifalar", "clipboard", CRUD, "as", "Uyga vazifalar; «Tahrirlash» — topshiriqlarni tekshirish va baholash"),
    ("groups", "Guruhlar", "layers", CRUD, "as", "Guruhlar, guruh videodarslari va a’zolari"),
    ("guides", "Qo‘llanmalar", "book-open", CRUD, "as", "Jadval, formula va boshqa qo‘llanmalar"),
    ("meetings", "Uchrashuvlar (meeting)", "video", [VIEW, ADD], "as", "Video uchrashuvlar; «Qo‘shish» — meeting tashkil qilish"),
    ("stats", "Statistika", "bar-chart-2", [VIEW], "as", "Rolga mos statistika sahifasi"),
    ("users", "Foydalanuvchilar", "users", CRUD, "a", "Talabalarni qo‘shish, tahrirlash, bloklash, o‘chirish"),
    ("gift", "Kurs berish / olib tashlash", "gift", [USE], "a", "Talabalarga kurs yoki modulni ochib berish"),
    ("notify", "Xabarnomalar", "send", CRUD, "a", "Talabalarga xabarnoma (ilova / SMS) yuborish"),
    ("reports", "Test xato xabarlari", "flag", [VIEW, EDIT, DELETE], "a", "Talabalar yuborgan test xatoliklari"),
    ("activity", "Kirish tarixi (faollik)", "activity", [VIEW], "a", "Foydalanuvchi qachon, qaysi qurilmadan kirgani"),
    ("security", "Xavfsizlik hodisalari", "shield", [VIEW, EDIT], "a", "Skrinshot / ekran yozish urinishlari; «Tahrirlash» — ko‘rib chiqish"),
    ("logs", "Tizim jurnali (log)", "terminal", [VIEW], "a", "Kim, qachon, qanday amal bajargani"),
]
SECTION_MAP = {s[0]: s for s in SECTIONS}
SECTION_CODES = [s[0] for s in SECTIONS]

_STUDENT_VIEW = ["articles", "courses", "tests", "tasks", "groups", "guides", "meetings", "stats"]
CODE_DEFAULTS = {
    "assistant": {c: [VIEW] for c in _STUDENT_VIEW},
    "student": {c: [VIEW] for c in _STUDENT_VIEW},
}

# Eski (ro'yxat ko'rinishidagi) ruxsatlar -> yangi tuzilma
_LEGACY_EXTRA = {"tests": ["reports"], "courses": ["tasks"]}


def role_letter(role):
    return {"assistant": "a", "student": "s"}.get(role, "")


def sections_for(role):
    """Rolga tegishli bo'limlar (talabaga faqat «Ko'rish» amali)."""
    L = role_letter(role)
    out = []
    for code, label, icon, acts, roles, desc in SECTIONS:
        if L and L in roles:
            out.append({"code": code, "label": label, "icon": icon, "desc": desc,
                        "actions": [VIEW] if role == "student" else list(acts)})
    return out


def clean(role, data):
    """Formadan/JSON dan kelgan ruxsatlarni tozalaydi: faqat mavjud bo'lim/amallar; yozish amali bo'lsa ko'rish ham qo'shiladi."""
    allowed = {s["code"]: s["actions"] for s in sections_for(role)}
    out = {}
    for code, acts in (data or {}).items():
        if code not in allowed:
            continue
        acts = [a for a in allowed[code] if a in set(acts or [])]
        if acts and VIEW in allowed[code] and VIEW not in acts:
            acts.insert(0, VIEW)
        if acts:
            out[code] = acts
    return out


def from_post(role, post, prefix="p"):
    """<input name="p.tests" value="add"> ko'rinishidagi checkboxlardan dict yasaydi."""
    data = {}
    for key in post.keys():
        if key.startswith(prefix + "."):
            data[key[len(prefix) + 1:]] = post.getlist(key)
    return clean(role, data)


def role_defaults(role):
    try:
        from apps.core.models import SiteSettingsModel
        stored = (SiteSettingsModel.get().role_perms or {}).get(role)
    except Exception:
        stored = None
    if isinstance(stored, dict):
        return clean(role, stored)
    return clean(role, CODE_DEFAULTS.get(role, {}))


def legacy_to_dict(role, codes):
    g = {k: list(v) for k, v in role_defaults(role).items()}
    if role != "assistant":
        return g
    for c in codes or []:
        for code in [c] + _LEGACY_EXTRA.get(c, []):
            if code in SECTION_MAP:
                g[code] = list(SECTION_MAP[code][3])
    return clean(role, g)


def matrix(role, grants):
    """Shablon uchun: [{code,label,icon,desc,cells:[{a,label,icon,on}]}]"""
    rows = []
    for s in sections_for(role):
        have = set(grants.get(s["code"], []))
        rows.append({**s, "cells": [{"a": a, "label": ACTION_LABELS[a], "icon": ACTION_ICONS[a], "on": a in have} for a in s["actions"]],
                     "level": ("hidden" if not have else "full" if have >= set(s["actions"]) else "read" if have == {VIEW} else "part")})
    return rows


LEVEL_LABELS = {"hidden": ("Ko‘rinmaydi", "x"), "read": ("Faqat ko‘rish", ""), "part": ("Qisman", ""), "full": ("To‘liq", "f")}


# url_name -> (bo'lim, amal). SectionAccessMiddleware har bir so'rovda shu jadval bo'yicha tekshiradi.
ROUTES = {
    "home": ("articles", VIEW), "article_detail": ("articles", VIEW), "article_cover": ("articles", VIEW),
    "article_new": ("articles", ADD), "article_edit": ("articles", EDIT), "article_toggle": ("articles", EDIT), "article_delete": ("articles", DELETE),

    "courses": ("courses", VIEW), "course_detail": ("courses", VIEW), "module_detail": ("courses", VIEW),
    "course_new": ("courses", ADD), "course_settings": ("courses", EDIT), "course_toggle": ("courses", EDIT), "course_delete": ("courses", DELETE),
    "module_new": ("courses", ADD), "module_edit": ("courses", EDIT), "module_toggle": ("courses", EDIT), "module_delete": ("courses", DELETE),

    "tests": ("tests", VIEW), "test_detail": ("tests", VIEW), "test_run": ("tests", VIEW), "attempt_detail": ("tests", VIEW),
    "report_new": ("tests", VIEW), "buy_test": ("tests", VIEW),
    "test_new": ("tests", ADD), "test_edit": ("tests", EDIT), "test_toggle": ("tests", EDIT), "test_time": ("tests", EDIT),
    "retake": ("tests", EDIT), "test_access": ("tests", EDIT), "test_delete": ("tests", DELETE),

    "reports": ("reports", VIEW), "report_detail": ("reports", VIEW), "report_done": ("reports", EDIT), "report_delete": ("reports", DELETE),

    "tasks": ("tasks", VIEW), "task_detail": ("tasks", VIEW), "submission_upload": ("tasks", VIEW),
    "task_new": ("tasks", ADD), "task_new_global": ("tasks", ADD),
    "task_edit": ("tasks", EDIT), "task_toggle": ("tasks", EDIT), "submission_review": ("tasks", EDIT),
    "submission_upload_for": ("tasks", EDIT), "task_remind": ("tasks", EDIT), "task_delete": ("tasks", DELETE),

    "groups": ("groups", VIEW), "group_detail": ("groups", VIEW), "group_new": ("groups", ADD),
    "group_edit": ("groups", EDIT), "group_toggle": ("groups", EDIT), "group_members": ("groups", EDIT),
    "user_groups": ("groups", EDIT), "group_delete": ("groups", DELETE),

    "guides": ("guides", VIEW), "guide_detail": ("guides", VIEW), "guide_new": ("guides", ADD),
    "guide_toggle": ("guides", EDIT), "guide_delete": ("guides", DELETE),

    "meetings": ("meetings", VIEW), "meeting_detail": ("meetings", VIEW), "meeting_room": ("meetings", VIEW),
    "meeting_code": ("meetings", VIEW), "meeting_new": ("meetings", ADD),

    "stats": ("stats", VIEW),

    "users": ("users", VIEW), "user_detail": ("users", VIEW), "user_new": ("users", ADD), "user_bulk": ("users", ADD),
    "user_edit": ("users", EDIT), "user_block": ("users", EDIT), "user_delete": ("users", DELETE),

    "gift_data": ("gift", USE), "gift_do": ("gift", USE), "revoke": ("gift", USE),

    "messages": ("notify", VIEW), "message_detail": ("notify", VIEW), "recipients_count": ("notify", VIEW),
    "message_new": ("notify", ADD), "message_edit": ("notify", EDIT), "message_resend": ("notify", EDIT), "message_delete": ("notify", DELETE),

    "security": ("security", VIEW), "security_detail": ("security", VIEW), "security_review": ("security", EDIT),
    "logs": ("logs", VIEW), "log_detail": ("logs", VIEW),
}
# GET so'rovda faqat ko'rish yetarli bo'lgan "aralash" sahifalar (GET forma, POST saqlash)
GET_AS_VIEW = {"submission_review"}

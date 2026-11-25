"""Bo'lim × amal ruxsatlari.

Har bir bo'lim uchun amallar: view (ko'rish), add (qo'shish), edit (tahrirlash), delete (o'chirish), use (foydalanish).
 - Asosiy o'qituvchi — hammasi (tekshirilmaydi).
 - Yordamchi o'qituvchi — bo'limlar bo'yicha to'liq CRUD berilishi mumkin.
 - Talaba — faqat «Ko'rish»: qaysi bo'limlar unga ko'rinishini belgilaydi.
«Ko'rish» berilmagan bo'lim menyuda ham chiqmaydi va unga kirish serverda bloklanadi.
Yozish amali (qo'shish/tahrirlash/o'chirish) berilsa, «Ko'rish» avtomatik qo'shiladi.
Saqlanish: UserModel.perms = {"courses": ["view", "add"], ...}. Eski ro'yxat ko'rinishi (["courses", ...]) ham o'qiladi.
"""

VIEW, ADD, EDIT, DELETE, USE = "view", "add", "edit", "delete", "use"
CRUD = [VIEW, ADD, EDIT, DELETE]
WRITE = {ADD, EDIT, DELETE, USE}
ACTION_LABELS = {VIEW: "Ko‘rish", ADD: "Qo‘shish", EDIT: "Tahrirlash", DELETE: "O‘chirish", USE: "Ruxsat"}
ACTION_HINTS = {VIEW: "Bo‘lim menyuda ko‘rinadi va ma’lumotlarni o‘qish mumkin",
                ADD: "Yangi yozuv yaratish mumkin", EDIT: "Mavjud yozuvlarni o‘zgartirish mumkin",
                DELETE: "Yozuvlarni o‘chirish mumkin", USE: "Bu amalni bajarish mumkin"}

# code, nomi, ikonka, mavjud amallar, qaysi rollarga tegishli (a — yordamchi, s — talaba), izoh
SECTIONS = [
    ("articles", "Maqolalar", "file-text", CRUD, "as", "Maqolalar lentasi; yordamchi uchun — maqola yozish, tahrirlash, o‘chirish"),
    ("courses", "Kurslar va darslar", "play-circle", CRUD, "as", "Kurs, modul, video dars va dars qo‘llanmalari"),
    ("tests", "Testlar", "check-square", CRUD, "as", "Test yaratish, vaqtini boshqarish, qayta topshirishga ruxsat"),
    ("reports", "Test xato xabarlari", "flag", [VIEW, EDIT, DELETE], "a", "Talabalar yuborgan test xatoliklari; «Tahrirlash» — hal qilindi deb belgilash"),
    ("tasks", "Vazifalar", "clipboard", CRUD, "as", "Uyga vazifalar; «Tahrirlash» — topshiriqlarni tekshirish va baholash"),
    ("groups", "Guruhlar", "layers", CRUD, "as", "Guruhlar, guruh videodarslari va a’zolari"),
    ("guides", "Qo‘llanmalar", "book-open", CRUD, "as", "Jadval, formula va boshqa qo‘llanmalar"),
    ("meetings", "Uchrashuvlar (meeting)", "video", CRUD, "as", "Video uchrashuvlar; «Qo‘shish» — uchrashuv tashkil qilish"),
    ("stats", "Statistika", "bar-chart-2", [VIEW], "as", "Rolga mos statistika sahifasi"),
    ("users", "Foydalanuvchilar", "users", CRUD, "a", "O‘z guruhidagi talabalarni qo‘shish, tahrirlash, bloklash, o‘chirish"),
    ("gift", "Kurs berish / olib tashlash", "gift", [USE], "a", "Talabalarga kurs yoki modulni to‘lovsiz ochib berish"),
    ("notify", "Xabarnomalar", "send", CRUD, "a", "Talabalarga xabarnoma yuborish"),
    ("activity", "Kirish tarixi (faollik)", "activity", [VIEW], "a", "Foydalanuvchi qachon, qaysi qurilmadan kirgani"),
]
SECTION_MAP = {s[0]: s for s in SECTIONS}
SECTION_CODES = [s[0] for s in SECTIONS]

_DEFAULT_VIEW = ["articles", "courses", "tests", "tasks", "groups", "guides", "meetings", "stats"]
CODE_DEFAULTS = {
    "assistant": {c: [VIEW] for c in _DEFAULT_VIEW},
    "student": {c: [VIEW] for c in _DEFAULT_VIEW},
}

# Eski (ro'yxat ko'rinishidagi) ruxsatlar -> yangi tuzilma
_LEGACY_EXTRA = {"tests": ["reports"], "courses": ["tasks"]}


def role_letter(role):
    return {"assistant": "a", "student": "s"}.get(role, "")


def sections_for(role):
    """Rolga tegishli bo'limlar. Talabaga faqat «Ko'rish» amali."""
    L = role_letter(role)
    out = []
    for code, label, icon, acts, roles, desc in SECTIONS:
        if L and L in roles:
            out.append({"code": code, "label": label, "icon": icon, "desc": desc,
                        "actions": [VIEW] if role == "student" else list(acts)})
    return out


def clean(role, data):
    """Faqat mavjud bo'lim/amallar qoladi; yozish amali bo'lsa «Ko'rish» ham qo'shiladi."""
    allowed = {s["code"]: s["actions"] for s in sections_for(role)}
    out = {}
    for code, acts in (data or {}).items():
        if code not in allowed:
            continue
        have = set(acts or [])
        acts = [a for a in allowed[code] if a in have]
        if acts and VIEW in allowed[code] and VIEW not in acts:
            acts.insert(0, VIEW)
        if acts:
            out[code] = acts
    return out


def from_post(role, post, prefix="p"):
    """<input type=checkbox name="p.tests" value="add"> ko'rinishidagi maydonlardan dict yasaydi."""
    data = {}
    for key in post.keys():
        if key.startswith(prefix + "."):
            data[key[len(prefix) + 1:]] = post.getlist(key)
    return clean(role, data)


def role_defaults(role):
    """Rol standarti: Sozlamalarda saqlangan bo'lsa o'sha, aks holda koddagi standart."""
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


def grants_of(user):
    if user.is_main:
        return {s[0]: list(s[3]) for s in SECTIONS}
    if isinstance(user.perms, dict) and user.perms.get("_custom"):
        return clean(user.role, user.perms)
    if isinstance(user.perms, list) and user.perms:
        return legacy_to_dict(user.role, user.perms)
    return role_defaults(user.role)


LEVEL_LABELS = {"hidden": ("Ko‘rinmaydi", "x"), "read": ("Faqat ko‘rish", ""), "part": ("Qisman", ""), "full": ("To‘liq", "f")}


def matrix(role, grants):
    """Shablon uchun: [{code,label,icon,desc,cells:[{a,label,hint,on}],level,level_label,level_cls}]"""
    rows = []
    for s in sections_for(role):
        have = set(grants.get(s["code"], []))
        level = "hidden" if not have else "full" if have >= set(s["actions"]) else "read" if have == {VIEW} else "part"
        rows.append({**s, "level": level, "level_label": LEVEL_LABELS[level][0], "level_cls": LEVEL_LABELS[level][1],
                     "cells": [{"a": a, "label": ACTION_LABELS[a], "hint": ACTION_HINTS[a], "on": a in have} for a in s["actions"]]})
    return rows


# url_name -> (bo'lim, amal). SectionAccessMiddleware va perm_required shu jadval bo'yicha tekshiradi.
# Bo'lim None — tekshiruv view ichida (masalan dars: kurs yoki guruhga tegishli bo'lishi mumkin).
ROUTES = {
    "home": ("articles", VIEW), "article_detail": ("articles", VIEW), "article_cover": ("articles", VIEW),
    "article_new": ("articles", ADD), "article_edit": ("articles", EDIT), "article_toggle": ("articles", EDIT),
    "article_delete": ("articles", DELETE),

    "courses": ("courses", VIEW), "course_detail": ("courses", VIEW), "module_detail": ("courses", VIEW),
    "course_new": ("courses", ADD), "course_settings": ("courses", EDIT), "course_toggle": ("courses", EDIT),
    "course_delete": ("courses", DELETE),
    "module_new": ("courses", ADD), "module_edit": ("courses", EDIT), "module_toggle": ("courses", EDIT),
    "module_delete": ("courses", DELETE),

    "tests": ("tests", VIEW), "test_detail": ("tests", VIEW), "test_run": ("tests", VIEW), "attempt_detail": ("tests", VIEW),
    "report_new": ("tests", VIEW), "buy_test": ("tests", VIEW),
    "test_new": ("tests", ADD), "test_edit": ("tests", EDIT), "test_toggle": ("tests", EDIT), "test_time": ("tests", EDIT),
    "retake": ("tests", EDIT), "test_access": ("tests", EDIT), "test_delete": ("tests", DELETE),

    "reports": ("reports", VIEW), "report_detail": ("reports", VIEW), "report_done": ("reports", EDIT),
    "report_delete": ("reports", DELETE),

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
    "meeting_code": ("meetings", VIEW), "meeting_new": ("meetings", ADD), "meeting_edit": ("meetings", EDIT),
    "meeting_delete": ("meetings", DELETE),

    "stats": ("stats", VIEW),

    "users": ("users", VIEW), "user_detail": ("users", VIEW), "user_new": ("users", ADD), "user_bulk": ("users", ADD),
    "user_edit": ("users", EDIT), "user_block": ("users", EDIT), "user_delete": ("users", DELETE),

    "gift_data": ("gift", USE), "gift_do": ("gift", USE), "revoke": ("gift", USE),

    "messages": ("notify", VIEW), "message_detail": ("notify", VIEW), "recipients_count": ("notify", VIEW),
    "message_new": ("notify", ADD), "message_edit": ("notify", EDIT), "message_resend": ("notify", EDIT),
    "message_delete": ("notify", DELETE),
}
# GET so'rovda faqat ko'rish yetarli bo'lgan "aralash" sahifalar (GET — ko'rish, POST — saqlash)
GET_AS_VIEW = {"submission_review"}


def route_need(url_name, method="GET"):
    """(bo'lim, amal) yoki None."""
    r = ROUTES.get(url_name)
    if not r:
        return None
    if url_name in GET_AS_VIEW and method == "GET":
        return (r[0], VIEW)
    return r

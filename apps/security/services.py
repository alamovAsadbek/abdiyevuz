"""Tizim jurnali (audit) va xavfsizlik hodisalari bilan ishlash."""
import logging
import time
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from .models import HIGH, AuditLogModel, SecurityIncidentModel, kind_info

audit_log = logging.getLogger("km.audit")
sec_log = logging.getLogger("km.security")

# url_name -> (amal nomi, kategoriya)
ACTIONS = {
    "login": ("Tizimga kirdi", "auth"), "login_fail": ("Kirish muvaffaqiyatsiz", "auth"), "logout": ("Tizimdan chiqdi", "auth"),
    "register": ("Ro‘yxatdan o‘tdi", "auth"), "profile": ("Profilni yangiladi", "users"),
    "user_new": ("Foydalanuvchi qo‘shdi", "users"), "user_bulk": ("Ko‘plab talaba qo‘shdi", "users"),
    "user_edit": ("Foydalanuvchini tahrirladi", "users"), "user_block": ("Bloklash / blokdan chiqarish", "users"),
    "user_delete": ("Foydalanuvchini o‘chirdi", "users"), "user_perm": ("Ruxsatlarni o‘zgartirdi", "perms"),
    "user_perms_save": ("Ruxsatlar matritsasini saqladi", "perms"), "role_perms": ("Rol standart ruxsatlarini o‘zgartirdi", "perms"),
    "user_groups": ("Foydalanuvchi guruhlarini o‘zgartirdi", "groups"),
    "course_new": ("Kurs yaratdi", "courses"), "course_settings": ("Kurs sozlamalarini o‘zgartirdi", "courses"),
    "course_toggle": ("Kurs holatini o‘zgartirdi", "courses"), "course_delete": ("Kursni o‘chirdi", "courses"),
    "module_new": ("Modul qo‘shdi", "courses"), "module_edit": ("Modulni tahrirladi", "courses"),
    "module_toggle": ("Modul holatini o‘zgartirdi", "courses"), "module_delete": ("Modulni o‘chirdi", "courses"),
    "lesson_new": ("Dars qo‘shdi", "courses"), "lesson_edit": ("Darsni tahrirladi", "courses"), "lesson_delete": ("Darsni o‘chirdi", "courses"),
    "material_new": ("Darsga qo‘llanma fayl qo‘shdi", "courses"), "material_delete": ("Dars qo‘llanmasini o‘chirdi", "courses"),
    "gift_do": ("Kurs ochib berdi", "courses"), "revoke": ("Kursdan chiqardi", "courses"), "buy_request": ("Sotib olish so‘rovi", "courses"),
    "test_new": ("Test yaratdi", "tests"), "test_edit": ("Testni tahrirladi", "tests"), "test_toggle": ("Test holatini o‘zgartirdi", "tests"),
    "test_delete": ("Testni o‘chirdi", "tests"), "test_time": ("Test vaqtini boshqardi", "tests"), "retake": ("Qayta ishlash ruxsati", "tests"),
    "test_access": ("Pullik testni ochib berdi", "tests"), "test_run": ("Test ishladi", "tests"), "buy_test": ("Testni sotib olish so‘rovi", "tests"),
    "report_new": ("Test xatoligi haqida xabar yubordi", "tests"), "report_done": ("Xato xabarini ko‘rib chiqdi", "tests"),
    "report_delete": ("Xato xabarini o‘chirdi", "tests"),
    "task_new": ("Vazifa qo‘shdi", "tasks"), "task_new_global": ("Vazifa qo‘shdi", "tasks"), "task_edit": ("Vazifani tahrirladi", "tasks"),
    "task_toggle": ("Vazifa holatini o‘zgartirdi", "tasks"), "task_delete": ("Vazifani o‘chirdi", "tasks"),
    "submission_upload": ("Vazifa topshirdi", "tasks"), "submission_upload_for": ("Talaba nomidan vazifa yukladi", "tasks"),
    "submission_review": ("Vazifani baholadi", "tasks"), "task_remind": ("Vazifa eslatmasini yubordi", "tasks"),
    "group_new": ("Guruh yaratdi", "groups"), "group_edit": ("Guruhni tahrirladi", "groups"), "group_toggle": ("Guruh holatini o‘zgartirdi", "groups"),
    "group_delete": ("Guruhni o‘chirdi", "groups"), "group_members": ("Guruh a’zolarini o‘zgartirdi", "groups"),
    "group_assistants": ("Guruh o‘qituvchilarini o‘zgartirdi", "groups"),
    "article_new": ("Maqola yozdi", "articles"), "article_edit": ("Maqolani tahrirladi", "articles"),
    "article_toggle": ("Maqola holatini o‘zgartirdi", "articles"), "article_delete": ("Maqolani o‘chirdi", "articles"),
    "guide_new": ("Qo‘llanma qo‘shdi", "guides"), "guide_toggle": ("Qo‘llanma holatini o‘zgartirdi", "guides"), "guide_delete": ("Qo‘llanmani o‘chirdi", "guides"),
    "message_new": ("Xabarnoma yubordi", "notify"), "message_edit": ("Xabarnomani tahrirladi", "notify"),
    "message_resend": ("Xabarnomani qayta yubordi", "notify"), "message_delete": ("Xabarnomani o‘chirdi", "notify"),
    "meeting_new": ("Uchrashuv yaratdi", "meetings"), "meeting_edit": ("Uchrashuvni tahrirladi", "meetings"),
    "meeting_delete": ("Uchrashuvni o‘chirdi", "meetings"), "meeting_start": ("Uchrashuvni boshladi", "meetings"),
    "meeting_end": ("Uchrashuvni yakunladi", "meetings"), "meeting_invite": ("Uchrashuvga taklif qildi", "meetings"),
    "meeting_cohost_add": ("Uchrashuvga yordamchi biriktirdi", "meetings"), "meeting_member": ("Uchrashuv qatnashchisini boshqardi", "meetings"),
    "meeting_rec_start": ("Uchrashuvni yozib olishni boshladi", "meetings"), "meeting_rec_stop": ("Uchrashuv yozuvini to‘xtatdi", "meetings"),
    "meeting_rec_file": ("Uchrashuv yozuvini ochdi / yuklab oldi", "files"),
    "file_download": ("Faylni yuklab oldi", "files"), "editor_upload": ("Muharrirga rasm yukladi", "files"),
    "site_settings": ("Umumiy sozlamalarni o‘zgartirdi", "settings"), "protect_settings": ("Himoya sozlamalarini o‘zgartirdi", "settings"),
    "security_review": ("Xavfsizlik hodisasini ko‘rib chiqdi", "security"), "security_action": ("Xavfsizlik hodisasi bo‘yicha amal", "security"),
    "denied": ("Ruxsatsiz bo‘limga kirishga urindi", "security"),
}
# Bu amallar jurnalga yozilmaydi (shovqin)
SKIP = {"ping", "user_perm", "read_all", "notification_open", "security_incident", "pref_save", "meeting_rec_chunk", "recipients_count", "gift_data"}
# GET bo'lsa ham yoziladigan amallar
LOG_GET = {"file_download", "meeting_rec_file"}
SENSITIVE = ("password", "pw", "p0", "p1", "p2", "csrfmiddlewaretoken", "token", "secret", "key")

# url_name prefiksi -> (model yo'li, obyekt turi)
OBJ = [("user_", "accounts.UserModel", "Foydalanuvchi"), ("group_", "accounts.GroupModel", "Guruh"),
       ("course_", "courses.CourseModel", "Kurs"), ("module_", "courses.ModuleModel", "Modul"),
       ("lesson_", "courses.LessonModel", "Dars"), ("material_", "courses.LessonMaterialModel", "Qo‘llanma fayl"),
       ("task_", "courses.TaskModel", "Vazifa"), ("submission_", "courses.SubmissionModel", "Topshiriq"),
       ("guide_", "courses.GuideModel", "Qo‘llanma"), ("test_", "exams.TestModel", "Test"), ("retake", "exams.TestModel", "Test"),
       ("report_", "exams.ErrorReportModel", "Xato xabari"), ("article_", "core.ArticleModel", "Maqola"),
       ("message_", "notifications.MessageModel", "Xabarnoma"), ("meeting_", "meetings.MeetingModel", "Uchrashuv"),
       ("security_", "security.SecurityIncidentModel", "Xavfsizlik hodisasi")]


def device_of(ua):
    from apps.accounts.utils import device_of as d
    return d(ua or "")


def client_ip(request):
    from apps.core.jwt_auth import client_ip as c
    return c(request)


def resolve_obj(url_name, kwargs):
    """O'chirishdan OLDIN obyekt nomini olish uchun (middleware process_view da chaqiriladi)."""
    from django.apps import apps
    pk = kwargs.get("pk") or kwargs.get("tid") or kwargs.get("lid") or kwargs.get("cid") or kwargs.get("mid")
    if not pk:
        return "", "", ""
    for pref, model, typ in OBJ:
        if url_name.startswith(pref):
            if kwargs.get("tid") and not kwargs.get("pk"):
                model, typ = "courses.TaskModel", "Vazifa"
            elif kwargs.get("lid") and not kwargs.get("pk"):
                model, typ = "courses.LessonModel", "Dars"
            elif kwargs.get("mid") and not kwargs.get("pk"):
                model, typ = "courses.ModuleModel", "Modul"
            elif kwargs.get("cid") and not kwargs.get("pk"):
                model, typ = "courses.CourseModel", "Kurs"
            try:
                o = apps.get_model(model).objects.filter(pk=pk).first()
            except Exception:
                o = None
            return typ, str(pk), (str(o)[:200] if o else "")
    return "", str(pk), ""


def safe_data(post):
    out = {}
    for k in list(post.keys())[:40]:
        if any(s in k.lower() for s in SENSITIVE):
            out[k] = "•••"
            continue
        vs = post.getlist(k)
        v = vs if len(vs) > 1 else vs[0] if vs else ""
        if isinstance(v, str) and len(v) > 160:
            v = v[:160] + "…"
        if isinstance(v, list):
            v = [x[:80] for x in v[:20]]
        out[k] = v
    return out


def audit(request, action, label=None, category=None, result="ok", actor=None, obj=("", "", ""), target=None,
          data=None, message="", status=0, duration_ms=0):
    """Jurnalga bitta yozuv. Xato bo'lsa asosiy jarayon to'xtamaydi."""
    try:
        a = actor if actor is not None else (request.user if request and request.user.is_authenticated else None)
        lb, cat = ACTIONS.get(action, (action, "other"))
        ua = request.META.get("HTTP_USER_AGENT", "")[:300] if request else ""
        rec = AuditLogModel.objects.create(
            actor=a, actor_name=(a.full_name or a.username) if a else "Mehmon", actor_role=a.role if a else "",
            action=action[:60], label=(label or lb)[:160], category=category or cat, result=result,
            method=request.method if request else "", path=request.get_full_path()[:400] if request else "", status=status,
            obj_type=obj[0], obj_id=obj[1], obj_label=obj[2], target_user=target, data=data or {}, message=message[:300],
            ip=client_ip(request) if request else None, user_agent=ua, device=device_of(ua), duration_ms=duration_ms)
        audit_log.info("%s | %s(%s) | %s | %s | %s %s | %s", result.upper(), rec.actor_name, rec.actor_role or "-", rec.label,
                       rec.obj_label or rec.obj_id or "-", rec.method, rec.path, rec.ip or "-")
        return rec
    except Exception:
        audit_log.exception("audit yozilmadi")
        return None


def target_from(url_name, kwargs, post):
    """Amal qaysi foydalanuvchiga tegishli (jurnalda «kim haqida» ustuni)."""
    from apps.accounts.models import UserModel
    uid = None
    if url_name.startswith("user_"):
        uid = kwargs.get("pk")
    uid = uid or kwargs.get("uid") or (post.get("uid") if post else None)
    try:
        return UserModel.objects.filter(pk=int(uid)).first() if uid else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- xavfsizlik hodisalari
def main_teachers():
    from apps.accounts.models import UserModel
    return list(UserModel.objects.filter(role="main", is_active=True, is_blocked=False))


def watchers_for(student):
    """Hodisa xabarini oladiganlar: barcha asosiy o'qituvchilar + talabaning guruhidagi «xavfsizlik» ruxsatli yordamchilar."""
    ids = {u.pk for u in main_teachers()}
    if student.is_student:
        for g in student.member_groups.all():
            for a in g.assistants.all():
                if a.can_view("security"):
                    ids.add(a.pk)
    ids.discard(student.pk)
    return ids


def record_incident(request, kind, url="", title="", content="", screen="", meta=None):
    """Bir xil hodisa (user + tur + sahifa) 2 daqiqa ichida takrorlansa — yangi yozuv emas, takror soni oshadi."""
    from apps.notifications.services import notify
    u = request.user
    label, sev, _, _ = kind_info(kind)
    now = timezone.now()
    url, title, content = url[:400], title[:200], content[:200]
    rec = SecurityIncidentModel.objects.filter(user=u, kind=kind, url=url, last_at__gte=now - timedelta(minutes=2)).first()
    if rec:
        rec.count += 1
        rec.save(update_fields=["count", "last_at"])
        return rec, False
    ua = request.META.get("HTTP_USER_AGENT", "")[:300]
    rec = SecurityIncidentModel.objects.create(user=u, kind=kind, severity=sev, url=url, page_title=title, content=content,
                                               ip=client_ip(request), user_agent=ua, device=device_of(ua), screen=screen[:20],
                                               meta=meta or {})
    sec_log.warning("%s | %s (%s, %s) | %s | %s | %s", sev.upper(), u.full_name, u.uid, u.role, label, url, rec.ip or "-")
    # Yuqori darajali hodisa — o'qituvchilarga darhol xabar (bitta foydalanuvchi uchun 1 daqiqada ko'pi bilan 1 ta)
    if sev == HIGH and cache.add(f"incn:{u.pk}", 1, 60):
        where = f" · {content or title}" if (content or title) else ""
        notify(list(watchers_for(u)), f"⚠ {u.full_name} ({u.uid}): {label}{where}", f"/security/{rec.pk}/")
    return rec, True


def rate_ok(user_id):
    """Bitta foydalanuvchidan soatiga 120 tadan ortiq hodisa qabul qilinmaydi (spamga qarshi)."""
    k = f"incr:{user_id}:{int(time.time() // 3600)}"
    n = cache.get(k, 0)
    if n >= 120:
        return False
    cache.set(k, n + 1, 3700)
    return True
